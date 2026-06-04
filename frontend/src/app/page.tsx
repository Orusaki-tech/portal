"use client"

import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import MapView from "@/components/Map/MapView"
import AdminSearch from "@/components/Map/AdminSearch"
import LayersPanel from "@/components/Map/LayersPanel"
import ImageryUpload from "@/components/Upload/ImageryUpload"
import DatasetUploader from "@/components/Upload/DatasetUploader"
import ImageryModal from "@/components/Imagery/ImageryModal"
import { IMAGERY_SOURCES } from "@/types/polygon"
import type { ImagerySource, AdminLevel, VectorOverlay } from "@/types/polygon"
import { fetchImagery, fetchPolygon, correctBoundary } from "@/lib/api"
import type { PolygonDetail } from "@/lib/api"
import { wktToCoords } from "@/lib/wkt"

interface AdminFeature {
  id: string
  name: string
  level: AdminLevel
  pcode: string
  parentName?: string
}

function getProp(feature: GeoJSON.Feature, key: string): string {
  const v = feature.properties?.[key]
  return v != null ? String(v) : ""
}

function getPcode(level: AdminLevel, feature: GeoJSON.Feature): string {
  if (level === "admin0") return getProp(feature, "adm0_pcode")
  if (level === "admin1") return getProp(feature, "adm1_pcode")
  return getProp(feature, "adm2_pcode")
}

function getName(level: AdminLevel, feature: GeoJSON.Feature): string {
  if (level === "admin0") return getProp(feature, "adm0_name")
  if (level === "admin1") return getProp(feature, "adm1_name")
  return getProp(feature, "adm2_name")
}

function indexFeatures(
  data: { level: AdminLevel; data: GeoJSON.FeatureCollection }[]
): AdminFeature[] {
  const result: AdminFeature[] = []
  for (const { level, data: fc } of data) {
    for (const feature of fc.features) {
      const pcode = getPcode(level, feature)
      const name = getName(level, feature)
      if (!pcode || !name) continue
      const parentName =
        level === "admin1"
          ? getProp(feature, "adm0_name")
          : level === "admin2"
            ? getProp(feature, "adm1_name")
            : undefined
      result.push({
        id: `${level}:${pcode}`,
        name,
        level,
        pcode,
        parentName,
      })
    }
  }
  return result
}

function HomePageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const reviewId = searchParams.get("review")

  const [drawnGeometry, setDrawnGeometry] = useState<number[][][] | null>(null)
  const [selectedSource, setSelectedSource] = useState<ImagerySource>(IMAGERY_SOURCES[1])
  const [userSources, setUserSources] = useState<ImagerySource[]>([])
  const [status, setStatus] = useState<string>("")
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const [reviewPolygon, setReviewPolygon] = useState<PolygonDetail | null>(null)
  const [reviewCoords, setReviewCoords] = useState<number[][][] | null>(null)
  const [correctionDrawn, setCorrectionDrawn] = useState<number[][][] | null>(null)

  // Admin boundaries
  const [adminData, setAdminData] = useState<
    { level: AdminLevel; data: GeoJSON.FeatureCollection }[]
  >([])
  const [adminLoading, setAdminLoading] = useState(true)
  const [selectedAdmin, setSelectedAdmin] = useState<string | null>(null)
  const [hoveredAdmin, setHoveredAdmin] = useState<string | null>(null)

  // Vector overlays
  const [overlays, setOverlays] = useState<VectorOverlay[]>([])

  // Handle getting imagery for selected admin area
  const [queryArea, setQueryArea] = useState<{
    name: string
    level: AdminLevel
    bounds: [number, number, number, number]
  } | null>(null)

  // Imagery modal
  const [imageryModal, setImageryModal] = useState<{
    feature: GeoJSON.Feature
    name: string
    level: AdminLevel
  } | null>(null)

  const allSources = [...IMAGERY_SOURCES, ...userSources]

  // Load admin boundaries
  useEffect(() => {
    async function load() {
      try {
        const entries = [
          { level: "admin0" as const, url: "/admin-data/kenya/admin0" },
          { level: "admin1" as const, url: "/admin-data/kenya/admin1" },
          { level: "admin2" as const, url: "/admin-data/kenya/admin2" },
        ]
        const results = await Promise.allSettled(
          entries.map(async (e) => {
            const res = await fetch(e.url)
            if (!res.ok) throw new Error(`Failed to load ${e.level}: ${res.status}`)
            const data: GeoJSON.FeatureCollection = await res.json()
            return { level: e.level, data }
          })
        )
        const loaded = results
          .filter((r) => r.status === "fulfilled")
          .map((r) => (r as PromiseFulfilledResult<{ level: "admin0" | "admin1" | "admin2"; data: GeoJSON.FeatureCollection }>).value)
        if (loaded.length > 0) {
          setAdminData(loaded)
          const layerMap: Record<string, { name: string; color: string; opacity: number }> = {
            admin0: { name: "Kenya (Country)", color: "#2e7d32", opacity: 0.08 },
            admin1: { name: "Counties", color: "#475569", opacity: 0.12 },
            admin2: { name: "Sub-Counties", color: "#94a3b8", opacity: 0.08 },
          }
          setOverlays(
            loaded.map((l) => ({
              id: `layer-${l.level}`,
              name: layerMap[l.level].name,
              visible: true,
              color: layerMap[l.level].color,
              opacity: layerMap[l.level].opacity,
              type: "admin" as const,
              level: l.level,
            }))
          )
        }
      } catch (err) {
        console.error("Failed to load admin boundaries", err)
      } finally {
        setAdminLoading(false)
      }
    }
    load()
  }, [])

  // Feature index for search
  const adminFeatures = useMemo(() => indexFeatures(adminData), [adminData])

  const loadUserImagery = useCallback(async () => {
    try {
      const data = await fetchImagery()
      const sources: ImagerySource[] = data.items
        .filter((i) => i.status === "ready" && i.tile_url)
        .map((i) => ({
          id: i.imagery_id,
          label: i.filename,
          tileUrl: i.tile_url!,
          attribution: "User upload",
          type: "cog" as const,
          resolution: "Varies",
          coverage: "User-defined",
        }))
      setUserSources(sources)
    } catch {
      // not logged in or no imagery
    }
  }, [])

  useEffect(() => {
    loadUserImagery()
  }, [loadUserImagery])

  useEffect(() => {
    if (!reviewId) return
    setStatus("Loading polygon for review...")
    fetchPolygon(reviewId)
      .then((polygon) => {
        setReviewPolygon(polygon)
        const coords = wktToCoords(polygon.original_geometry)
        setReviewCoords(coords)
        setCorrectionDrawn(null)
        setDrawnGeometry(null)
        setResult(null)
        setStatus(`Reviewing polygon ${reviewId.slice(0, 8)}...`)
      })
      .catch((err) => {
        setStatus(`Error loading polygon: ${err instanceof Error ? err.message : "Unknown error"}`)
      })
  }, [reviewId])

  // Admin selection handler (from map click or search)
  const handleAdminSelect = useCallback(
    (id: string, _level: AdminLevel, feature?: GeoJSON.Feature) => {
      setSelectedAdmin(id)
      // Calculate bounds for the selected area
      if (feature?.geometry?.type === "Polygon" || feature?.geometry?.type === "MultiPolygon") {
        const coords = feature.geometry.coordinates
        const all: number[] = []
        function extract(c: unknown) {
          if (Array.isArray(c)) {
            if (typeof c[0] === "number" && c.length >= 2) {
              all.push(c[0], c[1])
            } else {
              ;(c as unknown[]).forEach(extract)
            }
          }
        }
        extract(coords)
        if (all.length >= 4) {
          let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
          for (let i = 0; i < all.length; i += 2) {
            if (all[i] < minX) minX = all[i]
            if (all[i + 1] < minY) minY = all[i + 1]
            if (all[i] > maxX) maxX = all[i]
            if (all[i + 1] > maxY) maxY = all[i + 1]
          }
          const feat = adminFeatures.find((f) => f.id === id)
          setQueryArea({
            name: feat?.name || id,
            level: _level,
            bounds: [minX, minY, maxX, maxY],
          })
        }
      } else {
        // From search - find the feature in the data
        const feat = adminFeatures.find((f) => f.id === id)
        if (feat) {
          const adm = adminData.find((a) => a.level === feat.level)
          if (adm) {
            const match = adm.data.features.find((f) => getPcode(feat.level, f) === feat.pcode)
            if (match) {
              handleAdminSelect(id, feat.level, match)
              return
            }
          }
        }
        setSelectedAdmin(id)
      }
    },
    [adminData, adminFeatures]
  )

  const handleAdminSearchSelect = useCallback(
    (id: string, level: AdminLevel) => {
      handleAdminSelect(id, level)
    },
    [handleAdminSelect]
  )

  const handleAdminHover = useCallback(
    (id: string | null, _level: AdminLevel | null) => {
      setHoveredAdmin(id)
    },
    []
  )

  const handleRequestImagery = useCallback(
    (_id: string, level: AdminLevel, feature: GeoJSON.Feature) => {
      if (!feature?.geometry) return
      let name = _id
      try {
        const pcode = getPcode(level, feature)
        const feat = adminFeatures.find((f) => f.id === `${level}:${pcode}`)
        if (feat?.name) name = feat.name
      } catch {}
      setImageryModal({ feature, name, level })
    },
    [adminFeatures]
  )

  // Overlay management
  const handleOverlayToggle = useCallback((id: string) => {
    setOverlays((prev) =>
      prev.map((o) => (o.id === id ? { ...o, visible: !o.visible } : o))
    )
  }, [])

  const handleAddCustomOverlay = useCallback(
    (name: string, data: GeoJSON.FeatureCollection, color: string, opacity: number) => {
      const id = `custom-${Date.now()}`
      setOverlays((prev) => [
        ...prev,
        { id, name, visible: true, color, opacity, data, type: "custom" },
      ])
      setStatus(`Overlay "${name}" added`)
    },
    []
  )

  const handleRemoveOverlay = useCallback((id: string) => {
    setOverlays((prev) => prev.filter((o) => o.id !== id))
  }, [])

  const handleUploadComplete = useCallback(
    (_assetId: string, tileUrl?: string | null) => {
      if (tileUrl) {
        setSelectedSource({
          id: _assetId,
          label: "Uploaded Imagery",
          tileUrl,
          attribution: "User upload",
          type: "cog" as const,
          resolution: "Varies",
          coverage: "User-defined",
        })
      }
    },
    [],
  )

  const handlePolygonDraw = (geometry: number[][][]) => {
    if (reviewPolygon) {
      setCorrectionDrawn(geometry)
      setStatus("Correction drawn. Submit correction.")
    } else {
      setDrawnGeometry(geometry)
      setResult(null)
      setStatus("Polygon drawn. Submit to validate.")
    }
  }

  const handleSubmit = async () => {
    if (reviewPolygon && correctionDrawn) {
      const userId = JSON.parse(localStorage.getItem("realitysync_user") || "{}").user_id || ""
      if (!userId) {
        setStatus("Error: not logged in")
        return
      }
      const wkt = `POLYGON((${correctionDrawn[0]
        .map(([lng, lat]) => `${lng} ${lat}`)
        .join(", ")}))`
      setStatus("Submitting correction...")
      try {
        await correctBoundary(
          reviewPolygon.task_grid_id || reviewPolygon.polygon_id,
          reviewPolygon.polygon_id,
          userId,
          wkt,
        )
        setStatus("Correction submitted successfully!")
        setCorrectionDrawn(null)
        setReviewPolygon(null)
        setReviewCoords(null)
      } catch (err) {
        setStatus(`Error: ${err instanceof Error ? err.message : "Unknown error"}`)
      }
      return
    }

    if (!drawnGeometry) return
    setStatus("Submitting...")
    setResult(null)

    try {
      const wkt = `POLYGON((${drawnGeometry[0]
        .map(([lng, lat]) => `${lng} ${lat}`)
        .join(", ")}))`

      const res = await fetch("/api/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          geometry: wkt,
          imagery_source: selectedSource.id,
          user_id: JSON.parse(localStorage.getItem("realitysync_user") || "{}").user_id || "",
        }),
      })

      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResult(data)
      setStatus("Validation complete")
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Unknown error"}`)
    }
  }

  const handleCancelReview = () => {
    setReviewPolygon(null)
    setReviewCoords(null)
    setCorrectionDrawn(null)
    setStatus("")
    router.replace("/")
  }

  const handleClearCorrection = () => {
    setCorrectionDrawn(null)
    setStatus("Draw a new boundary to correct.")
  }

  const edgeColor = (score: number) => {
    if (score >= 0.7) return "text-green-600"
    if (score >= 0.4) return "text-yellow-600"
    return "text-red-600"
  }

  return (
    <div className="flex h-[calc(100vh-60px)]">
      <div className="flex-1">
        {adminLoading ? (
          <div className="flex h-full items-center justify-center text-gray-500">
            Loading boundaries...
          </div>
        ) : (
          <MapView
            onPolygonDraw={handlePolygonDraw}
            imagerySource={selectedSource}
            highlightPolygon={reviewCoords || (drawnGeometry ? drawnGeometry : null)}
            className="h-full"
            adminData={adminData}
            selectedAdminId={selectedAdmin}
            hoveredAdminId={hoveredAdmin}
            onAdminSelect={handleAdminSelect}
            onAdminHover={handleAdminHover}
            onRequestImagery={handleRequestImagery}
            overlays={overlays.filter((o) => o.visible && (o.type === "custom" ? !!o.data : true))}
          />
        )}
      </div>

      <div className="w-80 border-l border-gray-200 bg-white p-4 overflow-y-auto space-y-4">
        {/* Admin Search */}
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase text-gray-500">
            Kenya Admin Boundaries
          </h3>
          <AdminSearch features={adminFeatures} onSelect={handleAdminSearchSelect} />
        </div>

        {/* Query Area Status */}
        {queryArea && (
          <div className="rounded border border-blue-200 bg-blue-50 p-3">
            <p className="text-xs font-medium text-blue-800">
              Selected: {queryArea.name}
            </p>
            <p className="text-xs text-blue-600">
              {queryArea.level.toUpperCase()} — bounds: {queryArea.bounds.map((b) => b.toFixed(2)).join(", ")}
            </p>
          </div>
        )}

        {/* Layers Panel */}
        <LayersPanel
          overlays={overlays}
          onToggle={handleOverlayToggle}
          onAddCustom={handleAddCustomOverlay}
          onRemove={handleRemoveOverlay}
        />

        {reviewPolygon ? (
          <>
            <h2 className="mb-4 text-lg font-semibold">Correction Review</h2>

            <div className="mb-3 rounded bg-blue-50 p-3 text-sm">
              <p className="font-medium text-blue-800">
                Polygon {reviewPolygon.polygon_id.slice(0, 8)}
              </p>
              <p className="mt-1 text-blue-600">
                Status: {reviewPolygon.qa_status}
              </p>
              {reviewPolygon.confidence_avg !== null && (
                <p className="text-blue-600">
                  Confidence: {(reviewPolygon.confidence_avg * 100).toFixed(0)}%
                </p>
              )}
            </div>

            {reviewPolygon.edge_metrics.length > 0 && (
              <div className="mb-3">
                <h3 className="mb-1 text-xs font-semibold text-gray-500 uppercase">
                  Per-Vertex Confidence
                </h3>
                <div className="space-y-1">
                  {reviewPolygon.edge_metrics.map((m) => (
                    <div
                      key={m.vertex_index}
                      className="flex justify-between rounded bg-gray-50 px-2 py-1 text-xs"
                    >
                      <span className="text-gray-500">v{m.vertex_index}</span>
                      <span className={edgeColor(m.confidence_score)}>
                        {(m.confidence_score * 100).toFixed(0)}%
                      </span>
                      <span className="text-gray-400">
                        {m.deviation_meters.toFixed(2)}m
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-3 rounded bg-yellow-50 p-3 text-sm">
              <p className="font-medium text-yellow-800">Draw a Correction</p>
              <p className="mt-1 text-yellow-600">
                Use the Draw Polygon button on the map to draw the corrected boundary over the original.
              </p>
            </div>

            {correctionDrawn && (
              <div className="mb-3 rounded bg-green-50 p-3 text-sm">
                <p className="font-medium text-green-800">
                  Correction drawn ({correctionDrawn[0].length} vertices)
                </p>
                <button
                  onClick={handleClearCorrection}
                  className="mt-1 text-xs text-red-600 hover:underline"
                >
                  Clear
                </button>
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!correctionDrawn}
              className="w-full rounded bg-green-600 px-4 py-2 text-white disabled:opacity-50 hover:bg-green-700"
            >
              Submit Correction
            </button>

            <button
              onClick={handleCancelReview}
              className="mt-2 w-full rounded border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Cancel Review
            </button>
          </>
        ) : (
          <>
            <h2 className="mb-2 text-lg font-semibold">Validation</h2>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Imagery Source
              </label>
              <select
                value={selectedSource.id}
                onChange={(e) => {
                  const source = allSources.find(
                    (s) => s.id === e.target.value
                  )
                  if (source) setSelectedSource(source)
                }}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {allSources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            <details className="mb-4">
              <summary className="cursor-pointer text-xs font-medium text-gray-500">
                Upload Imagery
              </summary>
              <div className="mt-2">
                <ImageryUpload onUploadComplete={handleUploadComplete} />
              </div>
            </details>

            <details className="mb-4">
              <summary className="cursor-pointer text-xs font-medium text-gray-500">
                Upload Dataset
              </summary>
              <div className="mt-2">
                <DatasetUploader
                  onGeometriesParsed={(geometries, warnings, errors) => {
                    if (errors.length > 0) {
                      setStatus(`Upload errors: ${errors.join("; ")}`)
                    } else {
                      setStatus(`Uploaded ${geometries.length} polygon(s) from dataset`)
                    }
                  }}
                />
              </div>
            </details>

            {drawnGeometry && (
              <div className="mb-4 rounded bg-blue-50 p-3 text-sm">
                <p className="font-medium text-blue-800">Polygon ready</p>
                <p className="mt-1 text-blue-600">
                  {drawnGeometry[0].length} vertices
                </p>
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!drawnGeometry}
              className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50 hover:bg-blue-700"
            >
              Validate using {selectedSource.label}
            </button>
          </>
        )}

        {status && (
          <p className="text-sm text-gray-600">{status}</p>
        )}

        <ImageryModal
          open={imageryModal !== null}
          feature={imageryModal?.feature as GeoJSON.Feature}
          name={imageryModal?.name || ""}
          level={imageryModal?.level || "admin0"}
          selectedSource={selectedSource}
          userSources={userSources}
          onClose={() => setImageryModal(null)}
        />

        {result && !reviewPolygon && (
          <div className="rounded border border-gray-200 p-3">
            <h3 className="mb-2 text-sm font-semibold">Result</h3>
            <pre className="text-xs text-gray-700 overflow-x-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

export default function HomePage() {
  return (
    <Suspense fallback={<div className="flex h-[calc(100vh-60px)] items-center justify-center"><p className="text-gray-500">Loading...</p></div>}>
      <HomePageInner />
    </Suspense>
  )
}

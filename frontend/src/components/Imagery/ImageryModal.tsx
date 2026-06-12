"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import * as turf from "@turf/turf"
import type { ImagerySource, AdminLevel, FetchStatus, ImageryFetchResponse, ImageryCoverageResponse, PreprocessingOptions } from "@/types/polygon"

interface ImageryModalProps {
  open: boolean
  feature: GeoJSON.Feature
  name: string
  level: AdminLevel
  selectedSource: ImagerySource
  userSources: ImagerySource[]
  onClose: () => void
}

const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
const GUEST_API_KEY = "92cbb94d69272601c680040452c109036fdba9b469aaee005fdf386bb67b9677"

function computeBbox(feature?: GeoJSON.Feature): [number, number, number, number] {
  if (!feature?.geometry) return [37, -4, 38, 4]
  const coords = feature.geometry.type === "Polygon"
    ? feature.geometry.coordinates[0]
    : feature.geometry.type === "MultiPolygon"
      ? feature.geometry.coordinates.flatMap((p) => p[0])
      : []
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const [x, y] of coords) {
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  }
  return [minX, minY, maxX, maxY]
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function threeMonthsAgo(): string {
  const d = new Date()
  d.setMonth(d.getMonth() - 3)
  return d.toISOString().slice(0, 10)
}

async function fetchApi<T>(path: string, body: unknown): Promise<T> {
  let apiKey: string | null = null
  if (typeof window !== "undefined") {
    apiKey = localStorage.getItem("realitysync_api_key")
    if (!apiKey) {
      try {
        const user = JSON.parse(localStorage.getItem("realitysync_user") || "{}")
        apiKey = user.api_key || null
      } catch {}
    }
  }
  if (!apiKey) apiKey = GUEST_API_KEY

  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || "Request failed")
  }
  return res.json()
}

export default function ImageryModal({
  open,
  feature,
  name,
  level,
  selectedSource,
  userSources,
  onClose,
}: ImageryModalProps) {
  // Form controls
  const [buffer, setBuffer] = useState(0)
  const [activeSourceId, setActiveSourceId] = useState(selectedSource.id)
  const [dateFrom, setDateFrom] = useState(threeMonthsAgo())
  const [dateTo, setDateTo] = useState(todayISO())
  const [maxCloudCover, setMaxCloudCover] = useState(0)

  // Preprocessing options
  const [preprocEnabled, setPreprocEnabled] = useState(true)
  const [cloudMaskMethod, setCloudMaskMethod] = useState<"scl" | "qa_pixel" | "s2cloudless">("scl")
  const [speckleFilter, setSpeckleFilter] = useState(true)
  const [pansharpenAlgo, setPansharpenAlgo] = useState<false | "brovey" | "pca" | "ihs">(false)

  const prepOptions: PreprocessingOptions = {
    cloud_mask: preprocEnabled,
    cloud_mask_method: cloudMaskMethod,
    speckle_filter: speckleFilter,
    pansharpen: pansharpenAlgo,
  }

  // Coverage estimate (separate from fetch — no COG generation)
  const [coverage, setCoverage] = useState<ImageryCoverageResponse | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(false)

  // Two-phase pipeline state
  const [fetchStatus, setFetchStatus] = useState<FetchStatus>("idle")
  const [fetchResult, setFetchResult] = useState<ImageryFetchResponse | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const coverageDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Map state
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const mapReady = useRef(false)

  const allSources = [selectedSource, ...userSources.filter((s) => s.id !== selectedSource.id)]
  const activeSource = allSources.find((s) => s.id === activeSourceId) || selectedSource
  const isCommercial = ["planet", "maxar", "airbus", "blacksky"].includes(activeSource.id)

  const baseTileUrl = OSM_TILES

  const buffered = useMemo(() => {
    if (!open || buffer <= 0 || !feature?.geometry) return null
    try {
      return turf.buffer(feature, buffer, { units: "meters" })
    } catch {
      return null
    }
  }, [feature, buffer, open])

  const region = useMemo(() => {
    if (!open || !feature?.geometry) return null
    if (buffer > 0 && buffered) return buffered
    return feature
  }, [feature, buffer, buffered, open])

  const regionBbox = useMemo(() => {
    return region ? computeBbox(region) : [37, -4, 38, 4]
  }, [region])

  // TiTiler tile URLs — avoid geojson clip in URL; use MapLibre source.mask instead
  const previewTileUrl = useMemo(() => {
    if (fetchStatus !== "previewing" || !fetchResult?.preview_url || !region?.geometry) return null
    const coverageOk = coverage && coverage.coverage_pct !== null && coverage.coverage_pct >= 80
    const areaOk = coverage && coverage.area_km2 !== null && coverage.area_km2 <= 1000
    if (!coverageOk && !areaOk) return null
    return `/cog/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?url=${encodeURIComponent(fetchResult.preview_url)}`
  }, [fetchStatus, fetchResult, region, coverage])

  const cogTileUrl = useMemo(() => {
    if (fetchStatus !== "ready" || !fetchResult?.cog_url) return null
    return `/cog/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?url=${encodeURIComponent(fetchResult.cog_url)}`
  }, [fetchStatus, fetchResult])

  const activeTileUrl = cogTileUrl || previewTileUrl

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // Check coverage (no COG generation — pure query)
  const handleCheckCoverage = useCallback(async () => {
    if (!feature?.geometry) return
    setCoverageLoading(true)
    try {
      const res = await fetchApi<ImageryCoverageResponse>("/api/imagery/coverage", {
        source_id: activeSourceId,
        geojson: feature.geometry,
        buffer_meters: buffer,
        date_from: dateFrom,
        date_to: dateTo,
        max_cloud_cover: maxCloudCover,
      })
      setCoverage(res)
      setFetchError(null)
    } catch {
      setCoverage(null)
    } finally {
      setCoverageLoading(false)
    }
  }, [feature, activeSourceId, buffer, dateFrom, dateTo, maxCloudCover])

  // Auto-check coverage on modal open (immediate) and filter changes (debounced)
  useEffect(() => {
    if (!open) return
    if (coverageDebounceRef.current) clearTimeout(coverageDebounceRef.current)
    coverageDebounceRef.current = setTimeout(() => {
      handleCheckCoverage()
    }, coverage ? 600 : 0)
    return () => {
      if (coverageDebounceRef.current) clearTimeout(coverageDebounceRef.current)
    }
    // Only re-run when filters change or modal opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeSourceId, buffer, dateFrom, dateTo, maxCloudCover])

  // Submit fetch request
  const handleFetch = useCallback(async () => {
    if (!feature?.geometry) return
    setFetchStatus("previewing")
    setFetchError(null)
    setFetchResult(null)

    try {
      const pp: Record<string, unknown> | null = preprocEnabled ? {} : null
      if (preprocEnabled) {
        pp!["cloud_mask"] = { method: cloudMaskMethod }
        if (speckleFilter) pp!["speckle_filter"] = {}
        if (pansharpenAlgo) pp!["pansharpen"] = { algorithm: pansharpenAlgo }
      }

      const res = await fetchApi<ImageryFetchResponse>("/api/imagery/fetch", {
        source_id: activeSourceId,
        geojson: feature.geometry,
        buffer_meters: buffer,
        date_from: dateFrom,
        date_to: dateTo,
        max_cloud_cover: maxCloudCover,
        preprocessing: pp,
      })

      if (res.status === "preview") {
        setFetchResult(res)

        if (res.job_hash) {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = setInterval(async () => {
            try {
              const resp = await fetch(`/api/imagery/fetch/status/${res.job_hash}`)
              if (!resp.ok) {
                if (resp.status === 404) return
                throw new Error(resp.statusText)
              }
              const status = await resp.json()
              if (status.status === "ready" && status.result) {
                setFetchResult((prev) => ({ ...prev, ...status.result, status: "ready" }))
                setFetchStatus("ready")
                if (pollRef.current) clearInterval(pollRef.current)
                pollRef.current = null
              } else if (status.status === "error") {
                setFetchError(status.error || "Background processing failed")
                setFetchStatus("error")
                if (pollRef.current) clearInterval(pollRef.current)
                pollRef.current = null
              }
            } catch {
              // poll continues silently
            }
          }, 5000)
        }
      } else if (res.status === "processing") {
        setFetchResult(res)
        setFetchStatus("processing")

        if (res.job_hash) {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = setInterval(async () => {
            try {
              const resp = await fetch(`/api/imagery/fetch/status/${res.job_hash}`)
              if (!resp.ok) {
                if (resp.status === 404) return
                throw new Error(resp.statusText)
              }
              const status = await resp.json()
              if (status.status === "ready" && status.result) {
                setFetchResult((prev) => ({ ...prev, ...status.result, status: "ready" }))
                setFetchStatus("ready")
                if (pollRef.current) clearInterval(pollRef.current)
                pollRef.current = null
              } else if (status.status === "error") {
                setFetchError(status.error || "Background processing failed")
                setFetchStatus("error")
                if (pollRef.current) clearInterval(pollRef.current)
                pollRef.current = null
              }
            } catch {
              // poll continues silently
            }
          }, 5000)
        }
      } else {
        throw new Error("Unexpected response status")
      }
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Unknown error")
      setFetchStatus("error")
    }
  }, [feature, activeSourceId, buffer, dateFrom, dateTo, maxCloudCover, preprocEnabled, cloudMaskMethod, speckleFilter, pansharpenAlgo])

  // Cancel polling and reset (preserves filter values across open/close)
  const resetState = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    setCoverage(null)
    setCoverageLoading(false)
    setFetchStatus("idle")
    setFetchResult(null)
    setFetchError(null)
    setDownloading(null)
  }, [])

  // Map management
  const syncBaseLayer = useCallback((m: maplibregl.Map, url: string) => {
    if (m.getLayer("base-tiles-layer")) {
      m.removeLayer("base-tiles-layer")
      m.removeSource("base-tiles")
    }
    m.addSource("base-tiles", { type: "raster", tiles: [url], tileSize: 256 })
    m.addLayer({ id: "base-tiles-layer", type: "raster", source: "base-tiles" })
  }, [])

  const resetMap = useCallback(() => {
    if (mapRef.current) {
      mapRef.current.remove()
      mapRef.current = null
    }
    mapReady.current = false
  }, [])

  useEffect(() => {
    if (!open) {
      resetMap()
      resetState()
      return
    }
    resetState()
  }, [open, resetMap, resetState])

  const syncLayer = useCallback((m: maplibregl.Map, tileUrl: string | null, geometry: GeoJSON.Geometry | null) => {
    const layerId = "imagery-tiles-layer"
    const sourceId = "imagery-tiles"
    if (m.getLayer(layerId)) {
      m.removeLayer(layerId)
      m.removeSource(sourceId)
    }
    if (tileUrl) {
      m.addSource(sourceId, { type: "raster", tiles: [tileUrl], tileSize: 256, mask: geometry ?? undefined } as any)
      m.addLayer({ id: layerId, type: "raster", source: sourceId })
    }
  }, [])

  // Initialize map
  useEffect(() => {
    if (!open || !mapContainer.current || mapReady.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: { version: 8, sources: {}, layers: [] },
      center: [(regionBbox[0] + regionBbox[2]) / 2, (regionBbox[1] + regionBbox[3]) / 2],
      zoom: 6,
      attributionControl: false,
    })

    m.on("load", () => {
      m.addSource("base-tiles", { type: "raster", tiles: [baseTileUrl], tileSize: 256 })
      m.addLayer({ id: "base-tiles-layer", type: "raster", source: "base-tiles" })

      m.addSource("selected-polygon", { type: "geojson", data: feature })
      m.addLayer({
        id: "selected-polygon-fill",
        type: "fill",
        source: "selected-polygon",
        paint: { "fill-color": "#3b82f6", "fill-opacity": 0.15, "fill-outline-color": "#2563eb" },
      })
      m.addLayer({
        id: "selected-polygon-line",
        type: "line",
        source: "selected-polygon",
        paint: { "line-color": "#2563eb", "line-width": 2, "line-opacity": 0.9 },
      })

      if (buffer > 0 && buffered) {
        m.addSource("buffer-polygon", { type: "geojson", data: buffered })
        m.addLayer({
          id: "buffer-polygon-line",
          type: "line",
          source: "buffer-polygon",
          paint: { "line-color": "#f59e0b", "line-width": 2, "line-opacity": 0.8, "line-dasharray": [5, 5] },
        })
      }

      if (activeTileUrl) {
        syncLayer(m, activeTileUrl, region?.geometry ?? null)
      }

      m.fitBounds([[regionBbox[0], regionBbox[1]], [regionBbox[2], regionBbox[3]]], { padding: 40 })
      mapReady.current = true
    })

    mapRef.current = m

    return () => {
      m.remove()
      mapRef.current = null
      mapReady.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Sync base satellite layer when source changes
  useEffect(() => {
    const m = mapRef.current
    if (!m || !mapReady.current) return
    syncBaseLayer(m, baseTileUrl)
  }, [baseTileUrl, syncBaseLayer])

  // Sync processed tile layer when preview/COG URL changes
  useEffect(() => {
    const m = mapRef.current
    if (!m || !mapReady.current) return
    syncLayer(m, activeTileUrl, region?.geometry ?? null)
  }, [activeTileUrl, syncLayer, region?.geometry])

  // Resize map when layout changes (coverage loads/unloads, fetch status changes)
  useEffect(() => {
    const m = mapRef.current
    if (!m || !mapReady.current) return
    requestAnimationFrame(() => m.resize())
  }, [coverage, fetchStatus])

  // Update buffer outline
  useEffect(() => {
    const m = mapRef.current
    if (!m || !mapReady.current) return

    if (m.getLayer("buffer-polygon-line")) {
      m.removeLayer("buffer-polygon-line")
      m.removeSource("buffer-polygon")
    }
    if (buffer > 0 && buffered) {
      m.addSource("buffer-polygon", { type: "geojson", data: buffered })
      m.addLayer({
        id: "buffer-polygon-line",
        type: "line",
        source: "buffer-polygon",
        paint: { "line-color": "#f59e0b", "line-width": 2, "line-opacity": 0.8, "line-dasharray": [5, 5] },
      })
    }

    m.fitBounds([[regionBbox[0], regionBbox[1]], [regionBbox[2], regionBbox[3]]], { padding: 40 })
  }, [buffer, buffered, regionBbox])

  // Export handlers
  const downloadGeoTiff = useCallback(async () => {
    if (!fetchResult?.cog_url) return
    setDownloading("tif")
    const a = document.createElement("a")
    a.href = fetchResult.cog_url
    a.download = `${name.replace(/\s+/g, "_")}_${level}_buffer_${buffer}m.tif`
    a.click()
    setDownloading(null)
  }, [fetchResult, name, level, buffer])

  const exportFromMap = useCallback((format: "png" | "jpg") => {
    const m = mapRef.current
    if (!m) return
    const canvas = m.getCanvas()
    const link = document.createElement("a")
    link.download = `${name.replace(/\s+/g, "_")}_${level}_buffer_${buffer}m.${format}`
    if (format === "jpg") {
      link.href = canvas.toDataURL("image/jpeg", 0.92)
    } else {
      link.href = canvas.toDataURL("image/png")
    }
    link.click()
  }, [name, level, buffer])

  // Source change resets fetch
  const handleSourceChange = useCallback((newId: string) => {
    setActiveSourceId(newId)
    setCoverage(null)
    setCoverageLoading(false)
    setFetchStatus("idle")
    setFetchResult(null)
    setFetchError(null)
  }, [])

  if (!open) return null

  const btnDisabled = fetchStatus === "previewing" || fetchStatus === "processing"
  const fetchLabel = fetchStatus === "previewing" || fetchStatus === "processing" ? "Fetching..." : "Fetch Satellite Data"

  const coverPct = coverage?.coverage_pct ?? null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 flex h-[90vh] w-full max-w-5xl flex-col rounded-lg bg-white shadow-xl">
        {/* Header row: title + coverage + action */}
        <div className="flex shrink-0 items-center justify-between border-b px-6 py-3">
          <div className="flex items-center gap-4 min-w-0">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">{name}</h2>
              <p className="text-[11px] text-gray-400">{level.toUpperCase()} &middot; {activeSource.label}</p>
            </div>
            {coverage && (
              <div className="flex shrink-0 items-center gap-2 rounded-full bg-gray-50 px-3 py-1 text-xs">
                <span className={coverPct !== null ? (coverPct >= 80 ? "text-green-600" : coverPct >= 50 ? "text-amber-600" : "text-red-600") : "text-gray-400"}>
                  {coverPct !== null ? `${coverPct}%` : "—"}
                </span>
                <span className="text-gray-400">&middot; {coverage.scene_count} scene{coverage.scene_count !== 1 ? "s" : ""}</span>
                {coverage.cloud_cover_avg !== null && <span className="text-gray-400">&middot; {coverage.cloud_cover_avg}% cloud</span>}
                {coverage.area_km2 !== null && coverage.area_km2 > 0 && <span className="text-gray-400">&middot; {coverage.area_km2.toFixed(1)} km²</span>}
                <button
                  onClick={handleCheckCoverage}
                  disabled={coverageLoading}
                  className="ml-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                  title="Refresh"
                >
                  {coverageLoading ? "..." : "↻"}
                </button>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <details className="group relative">
              <summary className="cursor-pointer rounded border border-gray-200 px-2.5 py-1 text-[11px] text-gray-500 hover:bg-gray-50">
                Filters
              </summary>
              <div className="absolute right-0 z-10 mt-1 w-72 rounded border bg-white p-3 shadow-lg">
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <label className="w-12 text-[11px] text-gray-500">Buffer</label>
                    <input type="range" min={0} max={5000} step={100} value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} className="flex-1" />
                    <span className="w-12 text-right text-[11px] text-gray-400">{buffer}m</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="w-12 text-[11px] text-gray-500">From</label>
                    <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="flex-1 rounded border border-gray-300 px-2 py-1 text-[11px]" />
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="w-12 text-[11px] text-gray-500">To</label>
                    <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="flex-1 rounded border border-gray-300 px-2 py-1 text-[11px]" />
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="w-12 text-[11px] text-gray-500">Cloud</label>
                    <input type="range" min={0} max={100} step={1} value={maxCloudCover} onChange={(e) => setMaxCloudCover(Number(e.target.value))} className="flex-1" />
                    <span className="w-10 text-right text-[11px] text-gray-400">{maxCloudCover}%</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="w-12 text-[11px] text-gray-500">Source</label>
                    <select value={activeSourceId} onChange={(e) => handleSourceChange(e.target.value)} className="flex-1 rounded border border-gray-300 px-2 py-1 text-[11px]">
                      {allSources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                    </select>
                  </div>
                  <details className="group">
                    <summary className="cursor-pointer text-[11px] text-gray-500 hover:text-gray-700">
                      Preprocessing {preprocEnabled ? "🟢" : "⚪"}
                    </summary>
                    <div className="mt-1.5 space-y-1.5 pl-2">
                      <label className="flex items-center gap-1.5 text-[11px]">
                        <input type="checkbox" checked={preprocEnabled} onChange={(e) => setPreprocEnabled(e.target.checked)} />
                        Enable
                      </label>
                      {preprocEnabled && <>
                        <div className="flex items-center gap-1.5">
                          <label className="text-[11px] text-gray-500">Cloud mask:</label>
                          <select value={cloudMaskMethod} onChange={(e) => setCloudMaskMethod(e.target.value as typeof cloudMaskMethod)} className="flex-1 rounded border border-gray-300 px-2 py-0.5 text-[11px]">
                            <option value="scl">SCL</option>
                            <option value="qa_pixel">QA_PIXEL</option>
                            <option value="s2cloudless">s2cloudless</option>
                          </select>
                        </div>
                        <label className="flex items-center gap-1.5 text-[11px]">
                          <input type="checkbox" checked={speckleFilter} onChange={(e) => setSpeckleFilter(e.target.checked)} />
                          SAR speckle filter
                        </label>
                        <div className="flex items-center gap-1.5">
                          <label className="text-[11px] text-gray-500">Pan-sharpen:</label>
                          <select value={typeof pansharpenAlgo === "string" ? pansharpenAlgo : "off"} onChange={(e) => setPansharpenAlgo(e.target.value === "off" ? false : e.target.value as "brovey" | "pca" | "ihs")} className="flex-1 rounded border border-gray-300 px-2 py-0.5 text-[11px]">
                            <option value="off">Off</option>
                            <option value="brovey">Brovey</option>
                            <option value="pca">PCA</option>
                            <option value="ihs">IHS</option>
                          </select>
                        </div>
                      </>}
                    </div>
                  </details>
                </div>
              </div>
            </details>
            <button
              onClick={handleFetch}
              disabled={btnDisabled}
              className="rounded bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {fetchLabel}
            </button>
            <button onClick={onClose} className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Map area (flex-grow) with status overlay */}
        <div className="relative flex-1 min-h-0">
          <div ref={mapContainer} className="h-full w-full" />

          {/* Status overlay (top-left of map) */}
          <div className="pointer-events-none absolute left-3 top-3 z-10">
            {fetchStatus === "previewing" && (
              <span className="inline-block rounded bg-blue-600/80 px-2 py-0.5 text-xs text-white">
                {fetchResult?.preview_url && !previewTileUrl
                  ? "Building cloud-masked mosaic..."
                  : fetchResult?.preview_url
                    ? "Generating clipped COG..."
                    : "Fetching images..."}
              </span>
            )}
            {fetchStatus === "processing" && (
              <span className="inline-block rounded bg-amber-600/80 px-2 py-0.5 text-xs text-white">Processing...</span>
            )}
            {fetchStatus === "ready" && (
              <span className="inline-block rounded bg-green-600/80 px-2 py-0.5 text-xs text-white">
                {fetchResult?.cached ? "Cached" : "Ready"}
                {fetchResult?.scene_count !== undefined && fetchResult.scene_count > 0 && <> &middot; {fetchResult.scene_count} scene{fetchResult.scene_count > 1 ? "s" : ""}</>}
              </span>
            )}
            {fetchStatus === "error" && (
              <span className="inline-block rounded bg-red-600/80 px-2 py-0.5 text-xs text-white">
                {fetchError?.includes("API key") ? "Auth required" : fetchError || "Failed"}
              </span>
            )}
            {fetchStatus === "idle" && (
              <span className="inline-block rounded bg-gray-800/60 px-2 py-0.5 text-xs text-white">
                {coverage
                  ? coverPct !== null && coverPct >= 80
                    ? "Good coverage — fetch to preview"
                    : "Low coverage — adjust filters"
                  : coverageLoading
                    ? "Checking coverage..."
                    : ""}
              </span>
            )}
          </div>

          {/* Error action buttons (overlay on map) */}
          {fetchStatus === "error" && (
            <div className="pointer-events-auto absolute bottom-3 right-3 z-10 flex gap-2">
              {fetchError?.includes("API key") ? (
                <>
                  <button onClick={() => { localStorage.removeItem("realitysync_api_key"); window.location.href = "/login" }} className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">Sign In</button>
                  <button onClick={() => { localStorage.removeItem("realitysync_api_key"); localStorage.removeItem("realitysync_user"); window.location.reload() }} className="rounded border border-white/30 px-3 py-1 text-xs text-white hover:bg-white/10">Clear key</button>
                </>
              ) : (
                <>
                  <button onClick={() => setMaxCloudCover((c) => Math.min(100, c + 25))} className="rounded bg-amber-500/80 px-2 py-1 text-xs text-white hover:bg-amber-600">Raise cloud</button>
                  <button onClick={() => { setDateFrom(threeMonthsAgo()); setDateTo(todayISO()) }} className="rounded bg-amber-500/80 px-2 py-1 text-xs text-white hover:bg-amber-600">Expand dates</button>
                  <button onClick={handleFetch} className="rounded bg-blue-600/80 px-2 py-1 text-xs text-white hover:bg-blue-700">Retry</button>
                </>
              )}
            </div>
          )}
        </div>

        {/* Footer — export */}
        <div className="flex shrink-0 items-center justify-between border-t px-6 py-2">
          <div className="text-[11px] text-gray-400">
            {fetchStatus === "ready" && fetchResult?.scene_ids && fetchResult.scene_ids.length > 0 && (
              <span title={fetchResult.scene_ids.join(", ")}>
                Scene{fetchResult.scene_ids.length > 1 ? "s" : ""}: {fetchResult.scene_ids.slice(0, 3).join(", ")}
                {fetchResult.scene_ids.length > 3 && ` +${fetchResult.scene_ids.length - 3} more`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {fetchStatus === "ready" && fetchResult?.cog_url && (
              <button onClick={downloadGeoTiff} disabled={downloading !== null} className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50">
                {downloading === "tif" ? "..." : "GeoTIFF"}
              </button>
            )}
            <button onClick={() => exportFromMap("png")} className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50">PNG</button>
            <button onClick={() => exportFromMap("jpg")} className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50">JPEG</button>
          </div>
        </div>
      </div>
    </div>
  )
}

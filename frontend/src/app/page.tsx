"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import MapView from "@/components/Map/MapView"
import ImageryUpload from "@/components/Upload/ImageryUpload"
import { IMAGERY_SOURCES } from "@/types/polygon"
import type { ImagerySource } from "@/types/polygon"
import { fetchImagery, fetchPolygon, correctBoundary } from "@/lib/api"
import type { PolygonDetail } from "@/lib/api"
import { wktToCoords } from "@/lib/wkt"

function HomePageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const reviewId = searchParams.get("review")

  const [drawnGeometry, setDrawnGeometry] = useState<number[][][] | null>(null)
  const [selectedSource, setSelectedSource] = useState<ImagerySource>(IMAGERY_SOURCES[0])
  const [userSources, setUserSources] = useState<ImagerySource[]>([])
  const [status, setStatus] = useState<string>("")
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const [reviewPolygon, setReviewPolygon] = useState<PolygonDetail | null>(null)
  const [reviewCoords, setReviewCoords] = useState<number[][][] | null>(null)
  const [correctionDrawn, setCorrectionDrawn] = useState<number[][][] | null>(null)

  const allSources = [...IMAGERY_SOURCES, ...userSources]

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchImagery()
        const sources: ImagerySource[] = data.items
          .filter((i) => i.status === "ready" && i.tile_url)
          .map((i) => ({
            id: i.imagery_id,
            label: i.filename,
            tileUrl: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${i.tile_url!}`,
            attribution: "User upload",
          }))
        setUserSources(sources)
      } catch {
        // not logged in or no imagery — ignore
      }
    })()
  }, [])

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

  const handleUploadComplete = useCallback(
    (_assetId: string, tileUrl?: string | null) => {
      if (tileUrl) {
        setSelectedSource({
          id: _assetId,
          label: "Uploaded Imagery",
          tileUrl: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${tileUrl}`,
          attribution: "User upload",
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
        <MapView
          onPolygonDraw={handlePolygonDraw}
          imagerySource={selectedSource}
          highlightPolygon={reviewCoords || (drawnGeometry ? drawnGeometry : null)}
          className="h-full"
        />
      </div>

      <div className="w-80 border-l border-gray-200 bg-white p-4 overflow-y-auto">
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
            <h2 className="mb-4 text-lg font-semibold">Validation</h2>

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
          <p className="mt-3 text-sm text-gray-600">{status}</p>
        )}

        {result && !reviewPolygon && (
          <div className="mt-4 rounded border border-gray-200 p-3">
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

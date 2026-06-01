"use client"

import { useState } from "react"
import MapView from "@/components/Map/MapView"

export default function HomePage() {
  const [drawnGeometry, setDrawnGeometry] = useState<number[][][] | null>(null)
  const [status, setStatus] = useState<string>("")
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const handlePolygonDraw = (geometry: number[][][]) => {
    setDrawnGeometry(geometry)
    setResult(null)
    setStatus("Polygon drawn. Submit to validate.")
  }

  const handleSubmit = async () => {
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
        body: JSON.stringify({ geometry: wkt }),
      })

      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResult(data)
      setStatus("Validation complete")
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Unknown error"}`)
    }
  }

  return (
    <div className="flex h-[calc(100vh-60px)]">
      {/* Map */}
      <div className="flex-1">
        <MapView
          onPolygonDraw={handlePolygonDraw}
          className="h-full"
        />
      </div>

      {/* Sidebar */}
      <div className="w-80 border-l border-gray-200 bg-white p-4 overflow-y-auto">
        <h2 className="mb-4 text-lg font-semibold">Validation</h2>

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
          Validate Against NAIP
        </button>

        {status && (
          <p className="mt-3 text-sm text-gray-600">{status}</p>
        )}

        {result && (
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

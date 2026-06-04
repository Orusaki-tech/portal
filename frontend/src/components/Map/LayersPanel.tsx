"use client"

import { useCallback, useRef, useState } from "react"
import type { VectorOverlay } from "@/types/polygon"

interface LayersPanelProps {
  overlays: VectorOverlay[]
  onToggle: (id: string) => void
  onAddCustom: (name: string, data: GeoJSON.FeatureCollection, color: string, opacity: number) => void
  onRemove: (id: string) => void
}

const COLORS = ["#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"]

export default function LayersPanel({ overlays, onToggle, onAddCustom, onRemove }: LayersPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      try {
        const text = await file.text()
        const data = JSON.parse(text)
        if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) {
          throw new Error("File must be a GeoJSON FeatureCollection")
        }
        const name = file.name.replace(/\.(geojson|json)$/i, "")
        const color = COLORS[overlays.length % COLORS.length]
        onAddCustom(name, data, color, 0.3)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to parse file")
      } finally {
        setUploading(false)
      }
    },
    [overlays.length, onAddCustom]
  )

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase text-gray-500">Layers</h3>

      <div className="space-y-1">
        {overlays.map((ov) => (
          <div
            key={ov.id}
            className="flex items-center justify-between rounded border border-gray-200 px-2 py-1.5"
          >
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={ov.visible}
                onChange={() => onToggle(ov.id)}
                className="h-3.5 w-3.5 rounded"
              />
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: ov.color }}
              />
              <span className="text-xs text-gray-700">{ov.name}</span>
            </div>
            <button
              onClick={() => onRemove(ov.id)}
              className="text-xs text-red-500 hover:text-red-700"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div
        onClick={() => inputRef.current?.click()}
        className="cursor-pointer rounded border-2 border-dashed border-gray-300 p-3 text-center text-xs text-gray-500 hover:border-gray-400"
      >
        {uploading ? "Loading..." : "+ Add Vector Overlay (GeoJSON)"}
        <input
          ref={inputRef}
          type="file"
          accept=".geojson,.json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
          }}
        />
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}

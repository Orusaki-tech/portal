"use client"

import type { ImagerySource } from "@/types/polygon"

interface ImageryCardProps {
  source: ImagerySource
  selected: boolean
  onSelect: () => void
}

export default function ImageryCard({ source, selected, onSelect }: ImageryCardProps) {
  return (
    <button
      onClick={onSelect}
      className={`relative flex flex-col items-start rounded-lg border-2 p-4 text-left transition-all ${
        selected
          ? "border-blue-500 bg-blue-50 shadow-md"
          : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm"
      }`}
    >
      {selected && (
        <span className="absolute top-2 right-2 flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-xs text-white">
          ✓
        </span>
      )}

      <span className="mb-2 text-2xl">{source.thumbnail || "🛰️"}</span>

      <h3 className="text-sm font-semibold text-gray-900">{source.label}</h3>

      <div className="mt-1 flex flex-wrap gap-1.5">
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
          {source.resolution}
        </span>
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
          {source.coverage}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
            source.type === "xyz"
              ? "bg-green-100 text-green-700"
              : source.type === "stac"
                ? "bg-blue-100 text-blue-700"
                : "bg-purple-100 text-purple-700"
          }`}
        >
          {source.type === "xyz" ? "Tiles" : source.type === "stac" ? "STAC" : "COG"}
        </span>
      </div>
    </button>
  )
}

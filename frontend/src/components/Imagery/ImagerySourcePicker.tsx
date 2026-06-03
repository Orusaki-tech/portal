"use client"

import { useState } from "react"
import type { ImagerySource } from "@/types/polygon"
import { IMAGERY_SOURCES } from "@/types/polygon"
import ImageryCard from "@/components/Imagery/ImageryCard"
import StacEndpointForm from "@/components/Imagery/StacEndpointForm"
import ImageryUpload from "@/components/Upload/ImageryUpload"

interface ImagerySourcePickerProps {
  selectedId: string | null
  onSelect: (source: ImagerySource) => void
  userSources: ImagerySource[]
  onUserSourceAdded: (source: ImagerySource) => void
}

export default function ImagerySourcePicker({
  selectedId,
  onSelect,
  userSources,
  onUserSourceAdded,
}: ImagerySourcePickerProps) {
  const [showStacForm, setShowStacForm] = useState(false)
  const [showCogUpload, setShowCogUpload] = useState(false)
  const [customStacSources, setCustomStacSources] = useState<ImagerySource[]>([])

  const allSources = [...IMAGERY_SOURCES, ...userSources, ...customStacSources]

  const handleAddStac = (params: {
    stacUrl: string
    collection: string
    label: string
    authToken?: string
  }) => {
    const newSource: ImagerySource = {
      id: `custom-stac-${Date.now()}`,
      label: params.label,
      tileUrl: "",
      attribution: `${params.collection} via ${params.stacUrl}`,
      type: "stac",
      resolution: "Custom",
      coverage: "User-defined",
      stacUrl: params.stacUrl,
      stacCollection: params.collection,
      thumbnail: "🔗",
    }
    setCustomStacSources((prev) => [...prev, newSource])
    onSelect(newSource)
    setShowStacForm(false)
  }

  const handleUploadComplete = (_assetId: string, tileUrl?: string | null) => {
    if (tileUrl) {
      const source: ImagerySource = {
        id: _assetId,
        label: "Uploaded Imagery",
        tileUrl: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${tileUrl}`,
        attribution: "User upload",
        type: "cog",
        resolution: "Uploaded",
        coverage: "User-defined",
        thumbnail: "📂",
      }
      onUserSourceAdded(source)
      onSelect(source)
    }
    setShowCogUpload(false)
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Satellite & Aerial Imagery
        </h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {allSources.map((source) => (
            <ImageryCard
              key={source.id}
              source={source}
              selected={selectedId === source.id}
              onSelect={() => onSelect(source)}
            />
          ))}
        </div>
      </div>

      <div className="border-t border-gray-200 pt-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Add Your Own
        </h3>
        <div className="flex gap-3">
          <button
            onClick={() => setShowStacForm(true)}
            className="rounded-lg border-2 border-dashed border-gray-300 px-4 py-3 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600"
          >
            + Custom STAC Endpoint
          </button>
          <button
            onClick={() => setShowCogUpload(true)}
            className="rounded-lg border-2 border-dashed border-gray-300 px-4 py-3 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600"
          >
            + Upload My COG Imagery
          </button>
        </div>
      </div>

      {showStacForm && (
        <StacEndpointForm
          onAdd={handleAddStac}
          onClose={() => setShowStacForm(false)}
        />
      )}

      {showCogUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Upload COG Imagery</h2>
              <button
                onClick={() => setShowCogUpload(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                &times;
              </button>
            </div>
            <ImageryUpload onUploadComplete={handleUploadComplete} />
          </div>
        </div>
      )}
    </div>
  )
}

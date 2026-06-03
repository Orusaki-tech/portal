"use client"

import { useCallback, useRef, useState } from "react"

const ALLOWED_TYPES = [
  "image/tiff",
  "image/geotiff",
  "image/png",
  "image/jpeg",
]
const ALLOWED_EXTENSIONS = [".tif", ".geotiff", ".png", ".jpg", ".jpeg"]

interface UploadedAsset {
  id: string
  filename: string
  tileUrl?: string | null
}

interface ImageryUploadProps {
  onUploadComplete: (assetId: string, tileUrl?: string | null) => void
}

export default function ImageryUpload({
  onUploadComplete,
}: ImageryUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [assets, setAssets] = useState<UploadedAsset[]>([])
  const [dragOver, setDragOver] = useState(false)

  const isValidFile = (file: File) => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase()
    return (
      ALLOWED_TYPES.includes(file.type) ||
      ALLOWED_EXTENSIONS.includes(ext)
    )
  }

  const uploadFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      setProgress(0)

      try {
        const apiKey = localStorage.getItem("realitysync_api_key")
        const userId = JSON.parse(localStorage.getItem("realitysync_user") || "{}").user_id

        const formData = new FormData()
        formData.append("file", file)
        formData.append("user_id", userId)

        const res = await fetch("/api/upload/local", {
          method: "POST",
          headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
          body: formData,
        })

        if (!res.ok) {
          const errData = await res.text()
          throw new Error(errData || "Upload failed")
        }

        const { imagery_id, status, file_path } = await res.json()
        const tileUrl = `/tiles/user/${imagery_id}/{z}/{x}/{y}.png`

        const newAsset: UploadedAsset = {
          id: imagery_id,
          filename: file.name,
          tileUrl,
        }
        setAssets((prev) => [...prev, newAsset])
        onUploadComplete(imagery_id, tileUrl)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed")
      } finally {
        setUploading(false)
        setProgress(0)
      }
    },
    [onUploadComplete],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file && isValidFile(file)) {
        uploadFile(file)
      }
    },
    [uploadFile],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDragOver(false)
  }, [])

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        uploadFile(file)
      }
    },
    [uploadFile],
  )

  return (
    <div className="space-y-4">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-gray-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".tif,.geotiff,.png,.jpg,.jpeg"
          className="hidden"
          onChange={handleInputChange}
        />
        <p className="text-sm text-gray-600">
          {uploading
            ? `Uploading... ${progress}%`
            : "Drag & drop an imagery file here, or click to select"}
        </p>
        <p className="mt-1 text-xs text-gray-400">
          Supported: .tif, .geotiff, .png, .jpg
        </p>
      </div>

      {uploading && (
        <div className="h-2 overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-full rounded-full bg-blue-600 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}

      {assets.length > 0 && (
        <ul className="space-y-2">
          {assets.map((asset) => (
            <li
              key={asset.id}
              className="flex items-center justify-between rounded border px-3 py-2"
            >
              <span className="truncate text-sm">{asset.filename}</span>
              <button
                onClick={() => onUploadComplete(asset.id, asset.tileUrl)}
                className="ml-2 shrink-0 rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
              >
                Use as Base Layer
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

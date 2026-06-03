"use client"

import { useCallback, useRef, useState } from "react"
import { parseFile } from "@/lib/file-parser"
import type { FileParseResult } from "@/lib/file-parser"
import type { ParsedGeometry } from "@/types/polygon"

interface DatasetUploaderProps {
  onGeometriesParsed: (geometries: ParsedGeometry[], warnings: string[], errors: string[]) => void
}

export default function DatasetUploader({ onGeometriesParsed }: DatasetUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  const handleFile = useCallback(
    async (file: File) => {
      setParsing(true)
      setError(null)
      setFileName(file.name)

      try {
        const result: FileParseResult = await parseFile(file)

        if (result.errors.length > 0) {
          setError(result.errors.join(". "))
        }

        if (result.geometries.length === 0) {
          if (result.errors.length === 0) {
            setError("No valid polygon geometries found in the file")
          }
          onGeometriesParsed([], result.warnings, result.errors)
        } else {
          onGeometriesParsed(result.geometries, result.warnings, result.errors)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to parse file")
        onGeometriesParsed([], [], [])
      } finally {
        setParsing(false)
      }
    },
    [onGeometriesParsed]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile]
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
      if (file) handleFile(file)
    },
    [handleFile]
  )

  return (
    <div className="space-y-4">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
          dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-gray-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".geojson,.json,.csv,.zip"
          className="hidden"
          onChange={handleInputChange}
        />

        {parsing ? (
          <div className="space-y-2">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
            <p className="text-sm text-gray-600">Parsing file...</p>
          </div>
        ) : (
          <>
            <div className="mb-3 text-4xl text-gray-300">
              <svg className="mx-auto h-12 w-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <p className="text-sm text-gray-600">
              Drag & drop your ML dataset here, or click to select
            </p>
            <p className="mt-1 text-xs text-gray-400">
              Supported: .geojson, .json (GeoJSON), .csv (WKT column), .zip (Shapefile)
            </p>
          </>
        )}
      </div>

      {fileName && !parsing && (
        <div className="flex items-center gap-2 rounded bg-blue-50 px-3 py-2 text-sm text-blue-700">
          <span>📄</span>
          <span className="truncate">{fileName}</span>
          <button
            onClick={() => {
              setFileName(null)
              setError(null)
            }}
            className="ml-auto text-blue-500 hover:text-blue-700"
          >
            &times;
          </button>
        </div>
      )}

      {error && (
        <div className="rounded bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  )
}

"use client"

import { useCallback, useState } from "react"
import { useRouter } from "next/navigation"
import type { ImagerySource, ParsedGeometry } from "@/types/polygon"
import ImagerySourcePicker from "@/components/Imagery/ImagerySourcePicker"
import DatasetUploader from "@/components/Upload/DatasetUploader"
import GeometryValidationTable from "@/components/Upload/GeometryValidationTable"
import DatasetPreviewMap from "@/components/Map/DatasetPreviewMap"
import ValidationProgressBar from "@/components/Upload/ValidationProgressBar"
import { validateGeometries } from "@/lib/geometry-validate"
import { batchValidate } from "@/lib/api"

type Step = "imagery" | "dataset" | "validating" | "complete"

export default function UploadPage() {
  const router = useRouter()
  const [step, setStep] = useState<Step>("imagery")
  const [selectedSource, setSelectedSource] = useState<ImagerySource | null>(null)
  const [userSources, setUserSources] = useState<ImagerySource[]>([])
  const [geometries, setGeometries] = useState<ParsedGeometry[]>([])
  const [validating, setValidating] = useState(false)
  const [parseWarnings, setParseWarnings] = useState<string[]>([])
  const [parseErrors, setParseErrors] = useState<string[]>([])

  const [validationProgress, setValidationProgress] = useState({
    total: 0,
    completed: 0,
    status: "pending" as "pending" | "running" | "complete" | "error",
  })
  const [validationResult, setValidationResult] = useState<{
    setId: string
    polygonCount: number
  } | null>(null)

  const handleSourceSelect = useCallback((source: ImagerySource) => {
    setSelectedSource(source)
  }, [])

  const handleUserSourceAdded = useCallback((source: ImagerySource) => {
    setUserSources((prev) => {
      if (prev.find((s) => s.id === source.id)) return prev
      return [...prev, source]
    })
  }, [])

  const handleGeometriesParsed = useCallback(
    async (
      parsed: ParsedGeometry[],
      warnings: string[],
      errors: string[]
    ) => {
      setGeometries(parsed)
      setParseWarnings(warnings)
      setParseErrors(errors)

      if (parsed.length > 0) {
        setValidating(true)
        try {
          const validated = await validateGeometries(parsed)
          setGeometries(validated)
        } catch {
          // keep unvalidated
        } finally {
          setValidating(false)
        }
      }
    },
    []
  )

  const handleRunValidation = async () => {
    if (!selectedSource || geometries.length === 0) return

    setStep("validating")
    setValidationProgress({
      total: geometries.length,
      completed: 0,
      status: "running",
    })

    const userId = JSON.parse(
      localStorage.getItem("realitysync_user") || "{}"
    ).user_id

    if (!userId) {
      setValidationProgress((p) => ({ ...p, status: "error" }))
      return
    }

    try {
      const wkts = geometries.map((g) => g.wkt)
      const result = await batchValidate({
        geometries: wkts,
        imagerySource: selectedSource.id,
        userId,
        datasetName: `Upload ${new Date().toISOString().split("T")[0]}`,
      })

      setValidationProgress({
        total: geometries.length,
        completed: geometries.length,
        status: "complete",
      })

      setValidationResult({
        setId: result.set_id,
        polygonCount: result.polygon_count,
      })

      setStep("complete")
    } catch {
      setValidationProgress((p) => ({ ...p, status: "error" }))
    }
  }

  const validCount = geometries.filter((g) => g.status === "valid").length
  const canValidate =
    selectedSource && geometries.length > 0 && validCount > 0

  return (
    <div className="mx-auto flex h-[calc(100vh-60px)] max-w-7xl flex-col">
      {/* Step indicator */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="flex items-center gap-2 text-sm">
          <StepIndicator num={1} label="Choose Imagery" active={step === "imagery"} complete={step !== "imagery"} />
          <span className="text-gray-300">→</span>
          <StepIndicator num={2} label="Upload & Validate" active={step === "dataset" || step === "validating" || step === "complete"} complete={step === "validating" || step === "complete"} />
        </div>
      </div>

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-96 overflow-y-auto border-r border-gray-200 bg-white p-6">
          {step === "imagery" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-lg font-semibold">Choose Your Imagery Source</h2>
                <p className="mt-1 text-sm text-gray-500">
                  Every polygon boundary will be validated against this imagery.
                </p>
              </div>

              <ImagerySourcePicker
                selectedId={selectedSource?.id ?? null}
                onSelect={handleSourceSelect}
                userSources={userSources}
                onUserSourceAdded={handleUserSourceAdded}
              />

              {selectedSource && (
                <div className="rounded-lg bg-blue-50 p-4">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{selectedSource.thumbnail || "🛰️"}</span>
                    <div>
                      <p className="font-medium text-blue-900">{selectedSource.label}</p>
                      <p className="text-xs text-blue-600">
                        {selectedSource.resolution} · {selectedSource.coverage}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <button
                onClick={() => selectedSource && setStep("dataset")}
                disabled={!selectedSource}
                className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Continue to Upload Dataset
              </button>
            </div>
          )}

          {step !== "imagery" && (
            <div className="space-y-6">
              <div>
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Upload ML Dataset</h2>
                  <button
                    onClick={() => setStep("imagery")}
                    className="text-xs text-blue-600 hover:text-blue-800"
                  >
                    Change imagery
                  </button>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  Source: <span className="font-medium">{selectedSource?.label}</span>
                </p>
              </div>

              <DatasetUploader onGeometriesParsed={handleGeometriesParsed} />

              <GeometryValidationTable
                geometries={geometries}
                loading={validating}
              />

              {parseWarnings.length > 0 && (
                <div className="space-y-1">
                  {parseWarnings.map((w, i) => (
                    <p key={i} className="text-xs text-yellow-600">
                      ⚠ {w}
                    </p>
                  ))}
                </div>
              )}

              <ValidationProgressBar
                total={validationProgress.total}
                completed={validationProgress.completed}
                status={validationProgress.status}
              />

              {step === "complete" && validationResult && (
                <div className="rounded-lg bg-green-50 p-4 text-sm text-green-800">
                  <p className="font-medium">
                    ✓ Validation complete
                  </p>
                  <p className="mt-1 text-green-600">
                    {validationResult.polygonCount} polygons validated against{" "}
                    {selectedSource?.label}
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => router.push("/dashboard")}
                      className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700"
                    >
                      View in Triage
                    </button>
                    <button
                      onClick={() => {
                        setStep("imagery")
                        setGeometries([])
                        setValidationResult(null)
                      }}
                      className="rounded border border-green-300 px-4 py-2 text-sm text-green-700 hover:bg-green-100"
                    >
                      Upload Another
                    </button>
                  </div>
                </div>
              )}

              {step === "dataset" && (
                <button
                  onClick={handleRunValidation}
                  disabled={!canValidate}
                  className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {geometries.length === 0
                    ? "Upload a dataset first"
                    : validCount === 0
                      ? "No valid polygons to validate"
                      : `Validate ${validCount} polygons against ${selectedSource?.label}`}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Map preview */}
        <div className="flex-1">
          <DatasetPreviewMap
            geometries={geometries}
            imagerySource={selectedSource}
            className="h-full"
          />
        </div>
      </div>
    </div>
  )
}

function StepIndicator({
  num,
  label,
  active,
  complete,
}: {
  num: number
  label: string
  active: boolean
  complete: boolean
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
          complete
            ? "bg-blue-600 text-white"
            : active
              ? "border-2 border-blue-600 text-blue-600"
              : "border-2 border-gray-300 text-gray-400"
        }`}
      >
        {complete ? "✓" : num}
      </span>
      <span
        className={
          active || complete ? "font-medium text-gray-900" : "text-gray-400"
        }
      >
        {label}
      </span>
    </div>
  )
}

"use client"

import type { ParsedGeometry } from "@/types/polygon"

interface GeometryValidationTableProps {
  geometries: ParsedGeometry[]
  loading: boolean
}

export default function GeometryValidationTable({
  geometries,
  loading,
}: GeometryValidationTableProps) {
  const validCount = geometries.filter((g) => g.status === "valid").length
  const warningCount = geometries.filter((g) => g.status === "warning").length
  const errorCount = geometries.filter((g) => g.status === "error").length

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-200 p-6 text-center">
        <div className="mx-auto h-6 w-6 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
        <p className="mt-2 text-sm text-gray-500">Validating geometries...</p>
      </div>
    )
  }

  if (geometries.length === 0) return null

  return (
    <div className="space-y-3">
      <div className="flex gap-3 text-xs">
        <span className="rounded bg-green-100 px-2 py-1 text-green-700">
          {validCount} valid
        </span>
        {warningCount > 0 && (
          <span className="rounded bg-yellow-100 px-2 py-1 text-yellow-700">
            {warningCount} warnings
          </span>
        )}
        {errorCount > 0 && (
          <span className="rounded bg-red-100 px-2 py-1 text-red-700">
            {errorCount} errors
          </span>
        )}
      </div>

      <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-200">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-3 py-2 font-medium text-gray-500">#</th>
              <th className="px-3 py-2 font-medium text-gray-500">ID</th>
              <th className="px-3 py-2 font-medium text-gray-500">Vertices</th>
              <th className="px-3 py-2 font-medium text-gray-500">Area (m²)</th>
              <th className="px-3 py-2 font-medium text-gray-500">Self-Intersect</th>
              <th className="px-3 py-2 font-medium text-gray-500">Status</th>
            </tr>
          </thead>
          <tbody>
            {geometries.map((g, i) => (
              <tr
                key={g.id}
                className={`border-b border-gray-100 ${
                  g.status === "error"
                    ? "bg-red-50"
                    : g.status === "warning"
                      ? "bg-yellow-50"
                      : ""
                }`}
              >
                <td className="px-3 py-2 text-gray-400">{i + 1}</td>
                <td className="px-3 py-2 font-mono text-gray-700">{g.id}</td>
                <td className="px-3 py-2 text-gray-700">
                  {g.validation?.vertexCount ?? "-"}
                </td>
                <td className="px-3 py-2 text-gray-700">
                  {g.validation?.areaSqM
                    ? g.validation.areaSqM.toFixed(1)
                    : "-"}
                </td>
                <td className="px-3 py-2">
                  {g.validation ? (
                    g.validation.hasSelfIntersections ? (
                      <span className="font-medium text-red-600">Yes</span>
                    ) : (
                      <span className="text-green-600">No</span>
                    )
                  ) : (
                    "-"
                  )}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded px-1.5 py-0.5 font-medium ${
                      g.status === "valid"
                        ? "bg-green-100 text-green-700"
                        : g.status === "warning"
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-red-100 text-red-700"
                    }`}
                  >
                    {g.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {geometries.some(
        (g) => (g.validation?.warnings.length ?? 0) > 0 || (g.validation?.errors.length ?? 0) > 0
      ) && (
        <div className="space-y-1">
          {geometries
            .filter(
              (g) =>
                (g.validation?.warnings.length ?? 0) > 0 ||
                (g.validation?.errors.length ?? 0) > 0
            )
            .slice(0, 5)
            .map((g) => (
              <div key={g.id} className="rounded bg-gray-50 px-3 py-1.5 text-xs">
                <span className="font-medium text-gray-700">{g.id}:</span>
                {g.validation?.errors.map((e, i) => (
                  <span key={i} className="ml-1 text-red-600">
                    {e}
                  </span>
                ))}
                {g.validation?.warnings.map((w, i) => (
                  <span key={i} className="ml-1 text-yellow-600">
                    {w}
                  </span>
                ))}
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

"use client"

import { useState } from "react"
import type { TriageItem } from "@/types/polygon"

export default function DashboardPage() {
  const [items] = useState<TriageItem[]>([])

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Triage Queue</h1>

      {items.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">
            No polygons in the triage queue.
          </p>
          <p className="mt-2 text-sm text-gray-400">
            Upload and validate a dataset from the Map page to populate the queue.
          </p>
        </div>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2 font-medium">ID</th>
              <th className="py-2 font-medium">Confidence</th>
              <th className="py-2 font-medium">Deviation</th>
              <th className="py-2 font-medium">Priority</th>
              <th className="py-2 font-medium">Corrections</th>
              <th className="py-2 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.polygon_id} className="border-b border-gray-100">
                <td className="py-2 font-mono text-xs">
                  {item.polygon_id.slice(0, 8)}...
                </td>
                <td className="py-2">
                  {(item.computed_confidence * 100).toFixed(0)}%
                </td>
                <td className="py-2">
                  {item.avg_deviation_m.toFixed(2)}m
                </td>
                <td className="py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      item.priority_tier === "escalate"
                        ? "bg-red-100 text-red-700"
                        : item.priority_tier === "needs_correction"
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-blue-100 text-blue-700"
                    }`}
                  >
                    {item.priority_tier.replace("_", " ")}
                  </span>
                </td>
                <td className="py-2">{item.correction_count}</td>
                <td className="py-2">
                  <button className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">
                    Review
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

"use client"

import { useState } from "react"

interface Initiative {
  id: string
  name: string
  status: string
  total_blocks: number
  completed_blocks: number
  completion_pct: number
}

export default function InitiativesPage() {
  const [initiatives] = useState<Initiative[]>([])

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Initiatives</h1>
        <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
          New Initiative
        </button>
      </div>

      {initiatives.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">No initiatives yet.</p>
          <p className="mt-2 text-sm text-gray-400">
            Create an initiative to divide a region into grid blocks and assign
            annotators.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {initiatives.map((init) => (
            <div
              key={init.id}
              className="rounded-lg border border-gray-200 bg-white p-4"
            >
              <h3 className="font-semibold">{init.name}</h3>
              <p className="mt-1 text-xs text-gray-500">
                Status: {init.status}
              </p>
              <div className="mt-3">
                <div className="flex items-center justify-between text-sm">
                  <span>Progress</span>
                  <span>{init.completion_pct.toFixed(0)}%</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-gray-200">
                  <div
                    className="h-2 rounded-full bg-blue-600"
                    style={{ width: `${init.completion_pct}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-gray-400">
                  {init.completed_blocks} / {init.total_blocks} blocks
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

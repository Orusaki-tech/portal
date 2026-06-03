"use client"

import { useState } from "react"

interface InitiativeCreateFormProps {
  onClose: () => void
  onCreated: () => void
}

const currentUserId = typeof window !== "undefined" ? JSON.parse(localStorage.getItem("realitysync_user") || "{}").user_id : ""

export default function InitiativeCreateForm({ onClose, onCreated }: InitiativeCreateFormProps) {
  const [name, setName] = useState("")
  const [gridSizeM, setGridSizeM] = useState(1000)
  const [budgetCredits, setBudgetCredits] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError("Name is required")
      return
    }
    if (!currentUserId) {
      setError("Please log in first")
      return
    }
    setSubmitting(true)
    setError("")
    try {
      const { createInitiative } = await import("@/lib/api")
      const region = "POLYGON((-180 -90, 180 -90, 180 90, -180 90, -180 -90))"
      const result = await createInitiative(currentUserId, name.trim(), region, gridSizeM)
      if (budgetCredits) {
        const { topUpCredits } = await import("@/lib/api")
        await topUpCredits(currentUserId, Number(budgetCredits))
      }
      const { generateGridBlocks } = await import("@/lib/api")
      await generateGridBlocks(result.initiative_id)
      onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create initiative")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">New Initiative</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">&times;</button>
        </div>

        {error && (
          <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              placeholder="My Initiative"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Grid Size (meters)</label>
            <input
              type="number"
              value={gridSizeM}
              onChange={(e) => setGridSizeM(Number(e.target.value))}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              min={10}
              max={100000}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Budget Credits (optional)</label>
            <input
              type="number"
              value={budgetCredits}
              onChange={(e) => setBudgetCredits(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              min={0}
              placeholder="0"
            />
          </div>

          <div className="rounded bg-gray-50 p-3 text-xs text-gray-500">
            Region will be set to world extent (custom region drawing coming soon).
          </div>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

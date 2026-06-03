"use client"

import { useEffect, useState, useCallback } from "react"
import InitiativeCreateForm from "@/components/Initiatives/InitiativeCreateForm"
import GridBlockMap from "@/components/Initiatives/GridBlockMap"
import ParticipantList from "@/components/Initiatives/ParticipantList"
import { deleteInitiative } from "@/lib/api"
import type { InitiativeResponse as Initiative, GridBlockResponse } from "@/types/api"

interface Participant {
  initiative_id: string
  user_id: string
  role: string
  joined_at?: string
}

export default function InitiativesPage() {
  const [initiatives, setInitiatives] = useState<Initiative[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [detailError, setDetailError] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [selectedInit, setSelectedInit] = useState<Initiative | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [grids, setGrids] = useState<GridBlockResponse[]>([])
  const [participants, setParticipants] = useState<Participant[]>([])
  const [deleting, setDeleting] = useState<string | null>(null)

  const loadInitiatives = useCallback(async () => {
    try {
      const { fetchInitiatives } = await import("@/lib/api")
      const data = await fetchInitiatives()
      setInitiatives(data.items)
    } catch (err) {
      console.error(err)
      setError(err instanceof Error ? err.message : "Failed to load initiatives")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadInitiatives() }, [loadInitiatives])

  const loadInitiativeDetail = useCallback(async (init: Initiative) => {
    setSelectedInit(init)
    setDetailLoading(true)
    try {
      const { fetchInitiativeGrids } = await import("@/lib/api")
      const [gridData] = await Promise.all([
        fetchInitiativeGrids(init.id),
      ])
      setGrids(gridData.items)
      setParticipants(gridData.items.map((g) => ({
        initiative_id: init.id,
        user_id: g.assigned_user_id || "",
        role: "annotator",
      })).filter((p) => p.user_id))
    } catch (err) {
      console.error(err)
      setDetailError(err instanceof Error ? err.message : "Failed to load details")
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const handleDelete = async (id: string) => {
    setDeleting(id)
    try {
      await deleteInitiative(id)
      setInitiatives((prev) => prev.filter((i) => i.id !== id))
      if (selectedInit?.id === id) setSelectedInit(null)
    } catch (err) {
      console.error(err)
    } finally {
      setDeleting(null)
    }
  }

  const statusBadge = (status: string) => {
    switch (status) {
      case "active": return "bg-green-100 text-green-800"
      case "completed": return "bg-blue-100 text-blue-800"
      case "archived": return "bg-gray-100 text-gray-800"
      default: return "bg-yellow-100 text-yellow-800"
    }
  }

  if (selectedInit) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <button
          onClick={() => setSelectedInit(null)}
          className="mb-4 text-sm text-blue-600 hover:text-blue-800"
        >
          &larr; Back to Initiatives
        </button>

        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold">{selectedInit.name}</h1>
            <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(selectedInit.status)}`}>
                {selectedInit.status}
              </span>
              <span>Grid: {selectedInit.grid_size_m}m</span>
              {selectedInit.created_at && (
                <span>Created: {new Date(selectedInit.created_at).toLocaleDateString()}</span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleDelete(selectedInit.id)}
              disabled={deleting === selectedInit.id}
              className="rounded border border-red-300 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              {deleting === selectedInit.id ? "..." : "Archive"}
            </button>
          </div>
        </div>

        {detailLoading ? (
          <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
            <p className="text-gray-500">Loading details...</p>
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <h3 className="mb-2 text-sm font-semibold text-gray-700">Grid Blocks</h3>
              <GridBlockMap grids={grids} />
              {grids.length === 0 && (
                <p className="mt-2 text-sm text-gray-400">No grid blocks generated yet.</p>
              )}
            </div>
            <div>
              <ParticipantList
                initiativeId={selectedInit.id}
                participants={participants}
                onParticipantAdded={() => loadInitiativeDetail(selectedInit)}
              />
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Initiatives</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          New Initiative
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {showCreate && (
        <InitiativeCreateForm
          onClose={() => setShowCreate(false)}
          onCreated={loadInitiatives}
        />
      )}

      {loading ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">Loading initiatives...</p>
        </div>
      ) : initiatives.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">No initiatives yet.</p>
          <p className="mt-2 text-sm text-gray-400">
            Create an initiative to divide a region into grid blocks and assign annotators.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {initiatives.map((init) => (
            <button
              key={init.id}
              onClick={() => loadInitiativeDetail(init)}
              className="rounded-lg border border-gray-200 bg-white p-4 text-left hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <h3 className="font-semibold">{init.name}</h3>
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(init.status)}`}>
                  {init.status}
                </span>
              </div>
              <div className="mt-2 space-y-1 text-xs text-gray-500">
                <p>Grid: {init.grid_size_m}m</p>
                <p>Region: {init.region ? `${init.region.slice(0, 40)}...` : "N/A"}</p>
                {init.created_at && <p>Created: {new Date(init.created_at).toLocaleDateString()}</p>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

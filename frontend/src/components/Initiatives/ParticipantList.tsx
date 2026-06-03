"use client"

import { useState } from "react"

interface Participant {
  initiative_id: string
  user_id: string
  role: string
  joined_at?: string
}

interface ParticipantListProps {
  initiativeId: string
  participants: Participant[]
  onParticipantAdded: () => void
}

export default function ParticipantList({ initiativeId, participants, onParticipantAdded }: ParticipantListProps) {
  const [showAdd, setShowAdd] = useState(false)
  const [userId, setUserId] = useState("")
  const [role, setRole] = useState("annotator")
  const [adding, setAdding] = useState(false)

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!userId.trim()) return
    setAdding(true)
    try {
      const { assignParticipant } = await import("@/lib/api")
      await assignParticipant(initiativeId, userId.trim(), role)
      setUserId("")
      setShowAdd(false)
      onParticipantAdded()
    } catch (err) {
      console.error(err)
    } finally {
      setAdding(false)
    }
  }

  const roleBadge = (r: string) => {
    switch (r) {
      case "manager": return "bg-purple-100 text-purple-800"
      case "reviewer": return "bg-blue-100 text-blue-800"
      default: return "bg-green-100 text-green-800"
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-700">Participants</h4>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          {showAdd ? "Cancel" : "+ Add"}
        </button>
      </div>

      {showAdd && (
        <form onSubmit={handleAdd} className="mb-3 flex gap-2">
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="User ID"
            className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs"
            required
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-xs"
          >
            <option value="annotator">Annotator</option>
            <option value="reviewer">Reviewer</option>
            <option value="manager">Manager</option>
          </select>
          <button
            type="submit"
            disabled={adding}
            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {adding ? "..." : "Add"}
          </button>
        </form>
      )}

      {participants.length === 0 ? (
        <p className="text-xs text-gray-400">No participants assigned.</p>
      ) : (
        <div className="space-y-1">
          {participants.map((p) => (
            <div key={p.user_id} className="flex items-center justify-between rounded bg-gray-50 px-2 py-1">
              <span className="text-xs text-gray-700">{p.user_id.slice(0, 12)}...</span>
              <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${roleBadge(p.role)}`}>
                {p.role}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

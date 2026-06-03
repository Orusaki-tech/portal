"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { getLeaderboard, joinHackathon, submitHackathonResult } from "@/lib/api"
import type { LeaderboardEntry } from "@/lib/api"

export default function HackathonLeaderboardPage() {
  const params = useParams()
  const initiativeId = params.initiative_id as string
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [score, setScore] = useState("")
  const [accuracy, setAccuracy] = useState("")
  const [message, setMessage] = useState("")

  const load = async () => {
    try {
      setLoading(true)
      const data = await getLeaderboard(initiativeId)
      setEntries(data.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leaderboard")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [initiativeId])

  const userId = typeof window !== "undefined"
    ? JSON.parse(localStorage.getItem("realitysync_user") || "{}").user_id
    : ""

  const handleJoin = async () => {
    if (!userId) { setMessage("Please log in first"); return }
    try {
      await joinHackathon(initiativeId, userId)
      setMessage("Joined successfully!")
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : "Unknown"}`)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!userId) { setMessage("Please log in first"); return }
    try {
      await submitHackathonResult(initiativeId, userId, Number(score), Number(accuracy))
      setMessage("Result submitted!")
      setScore("")
      setAccuracy("")
      load()
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : "Unknown"}`)
    }
  }

  if (loading) return <div className="p-8 text-center text-gray-500">Loading leaderboard...</div>

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Hackathon Leaderboard</h1>
      <p className="mb-6 text-sm text-gray-500">Initiative: {initiativeId}</p>

      {message && (
        <p className="mb-4 rounded bg-blue-50 p-3 text-sm text-blue-800">{message}</p>
      )}
      {error && (
        <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
      )}

      <div className="mb-6 flex gap-3">
        <button
          onClick={handleJoin}
          className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700"
        >
          Join Hackathon
        </button>
      </div>

      <div className="mb-8 rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">Submit Result</h2>
        <form onSubmit={handleSubmit} className="flex items-end gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Score</label>
            <input
              type="number" value={score} step="0.1"
              onChange={(e) => setScore(e.target.value)} required
              className="w-32 rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Accuracy (%)</label>
            <input
              type="number" value={accuracy} min="0" max="100" step="0.1"
              onChange={(e) => setAccuracy(e.target.value)} required
              className="w-32 rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            Submit
          </button>
        </form>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase">
              <th className="px-4 py-3">Rank</th>
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Accuracy</th>
              <th className="px-4 py-3">Polygons</th>
              <th className="px-4 py-3">Submitted</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No entries yet</td></tr>
            ) : entries.map((e) => (
              <tr key={e.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium">{e.place}</td>
                <td className="px-4 py-3 font-mono text-xs">{e.user_id.slice(0, 8)}...</td>
                <td className="px-4 py-3">{e.score}</td>
                <td className="px-4 py-3">{e.accuracy_pct}%</td>
                <td className="px-4 py-3">{e.polygons_submitted}</td>
                <td className="px-4 py-3 text-gray-400">
                  {e.submitted_at ? new Date(e.submitted_at).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
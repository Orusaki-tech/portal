"use client"

import { useState } from "react"
import { requestExport } from "@/lib/api"

interface ExportJob {
  export_id: string
  export_format: string
  source_type: string
  source_id: string
  status: string
}

export default function ExportsPage() {
  const [status, setStatus] = useState("")
  const [jobs, setJobs] = useState<ExportJob[]>([])
  const userId = "00000000-0000-0000-0000-000000000001"

  const handleRequest = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    try {
      const result = await requestExport(
        userId,
        fd.get("format") as string,
        fd.get("sourceType") as string,
        crypto.randomUUID(),
      )
      setStatus(`Export ${result.export_id.slice(0, 8)} — ${result.status}`)
      setJobs((prev) => [
        { export_id: result.export_id, export_format: result.export_format, source_type: fd.get("sourceType") as string, source_id: crypto.randomUUID(), status: result.status },
        ...prev,
      ])
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Unknown"}`)
    }
  }

  const formats = ["geojson", "coco", "yolo", "pascal_voc", "tfrecord"]
  const sourceTypes = ["dataset", "initiative", "grid"]

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Exports</h1>

      {status && (
        <p className="mb-4 rounded bg-blue-50 p-3 text-sm text-blue-800">{status}</p>
      )}

      <div className="mb-8 rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-semibold">Request Export</h2>
        <form onSubmit={handleRequest} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Format</label>
            <select name="format" required className="rounded border border-gray-300 px-3 py-2 text-sm">
              {formats.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Source Type</label>
            <select name="sourceType" required className="rounded border border-gray-300 px-3 py-2 text-sm">
              {sourceTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button type="submit" className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
            Request Export
          </button>
        </form>
      </div>

      <h2 className="mb-3 text-lg font-semibold">Export History</h2>
      {jobs.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">No exports yet.</p>
        </div>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2 font-medium">Export ID</th>
              <th className="py-2 font-medium">Format</th>
              <th className="py-2 font-medium">Source</th>
              <th className="py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.export_id} className="border-b border-gray-100">
                <td className="py-2 font-mono text-xs">{j.export_id.slice(0, 8)}...</td>
                <td className="py-2">{j.export_format}</td>
                <td className="py-2">{j.source_type}</td>
                <td className="py-2">
                  <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
                    {j.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

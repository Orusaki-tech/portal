"use client"

import { useState } from "react"

interface StacEndpointFormProps {
  onAdd: (source: {
    stacUrl: string
    collection: string
    label: string
    authToken?: string
  }) => void
  onClose: () => void
}

export default function StacEndpointForm({ onAdd, onClose }: StacEndpointFormProps) {
  const [stacUrl, setStacUrl] = useState("")
  const [collection, setCollection] = useState("")
  const [label, setLabel] = useState("")
  const [authToken, setAuthToken] = useState("")
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  const handleTest = async () => {
    if (!stacUrl || !collection) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await fetch("/api/stac/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stacUrl,
          collection,
          maxItems: 1,
          authToken: authToken || undefined,
        }),
      })
      if (res.ok) {
        setTestResult({ ok: true, message: "Connection successful" })
      } else {
        const err = await res.text()
        setTestResult({ ok: false, message: err || "Connection failed" })
      }
    } catch {
      setTestResult({ ok: false, message: "Could not reach STAC endpoint" })
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onAdd({
      stacUrl: stacUrl.replace(/\/$/, ""),
      collection,
      label: label || `${collection} (Custom STAC)`,
      authToken: authToken || undefined,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Add Custom STAC Endpoint</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              STAC API URL
            </label>
            <input
              type="url"
              value={stacUrl}
              onChange={(e) => setStacUrl(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              placeholder="https://planetarycomputer.microsoft.com/api/stac/v1"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Collection Name
            </label>
            <input
              type="text"
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm font-mono"
              placeholder="sentinel-2-l2a"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Display Label
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              placeholder="My Custom Source"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              API Key / Bearer Token <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="password"
              value={authToken}
              onChange={(e) => setAuthToken(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              placeholder="For private STAC servers"
            />
          </div>

          <button
            type="button"
            onClick={handleTest}
            disabled={!stacUrl || !collection || testing}
            className="w-full rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {testing ? "Testing Connection..." : "Test Connection"}
          </button>

          {testResult && (
            <p
              className={`text-sm ${testResult.ok ? "text-green-600" : "text-red-600"}`}
            >
              {testResult.message}
            </p>
          )}

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
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
            >
              Add Source
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

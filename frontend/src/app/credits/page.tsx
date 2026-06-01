"use client"

import { useState } from "react"
import { topUpCredits } from "@/lib/api"

export default function CreditsPage() {
  const [status, setStatus] = useState("")
  const [balance, setBalance] = useState<number | null>(null)
  const userId = "00000000-0000-0000-0000-000000000001"

  const handleTopUp = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    try {
      const result = await topUpCredits(userId, Number(fd.get("amount")))
      setBalance(result.credits_remaining)
      setStatus(`Top-up successful — ${result.credits_remaining} credits remaining`)
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Unknown"}`)
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Credits</h1>

      {status && (
        <p className="mb-4 rounded bg-blue-50 p-3 text-sm text-blue-800">{status}</p>
      )}

      {balance !== null && (
        <div className="mb-6 rounded-lg border border-gray-200 bg-white p-6 text-center">
          <p className="text-sm text-gray-500">Current Balance</p>
          <p className="text-4xl font-bold text-blue-700">{balance}</p>
          <p className="text-sm text-gray-400">credits</p>
        </div>
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold">Top Up Credits</h2>
        <form onSubmit={handleTopUp} className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Amount</label>
            <input
              name="amount"
              type="number"
              min="1"
              step="1"
              placeholder="e.g. 100"
              required
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            className="rounded bg-blue-600 px-6 py-2 text-sm text-white hover:bg-blue-700"
          >
            Add Credits
          </button>
        </form>
      </div>

      <div className="mt-8">
        <h2 className="mb-3 text-lg font-semibold">Pricing</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="font-semibold">Starter</h3>
            <p className="text-2xl font-bold text-gray-800">$299<span className="text-sm font-normal text-gray-500">/mo</span></p>
            <ul className="mt-3 list-inside list-disc text-sm text-gray-600">
              <li>1,000 validation credits</li>
              <li>5 active initiatives</li>
              <li>Community support</li>
            </ul>
          </div>
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <h3 className="font-semibold">Professional</h3>
            <p className="text-2xl font-bold text-blue-700">$999<span className="text-sm font-normal text-gray-500">/mo</span></p>
            <ul className="mt-3 list-inside list-disc text-sm text-gray-600">
              <li>10,000 validation credits</li>
              <li>Unlimited initiatives</li>
              <li>Priority support</li>
              <li>Team management</li>
            </ul>
          </div>
        </div>
      </div>

      <p className="mt-6 text-xs text-gray-400">
        Credits cost $0.15–$0.40 per pair depending on volume. Contact sales for custom pricing.
      </p>
    </div>
  )
}

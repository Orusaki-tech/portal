"use client"

import { useState } from "react"
import { createListing, purchaseListing, topUpCredits } from "@/lib/api"

export default function MarketplacePage() {
  const [status, setStatus] = useState("")
  const [listings, setListings] = useState<
    { listing_id: string; title: string; price_tokens: number; geometry_count: number; status: string }[]
  >([])

  // Mock user ID for demo
  const userId = "00000000-0000-0000-0000-000000000001"

  const handleCreateListing = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    try {
      const result = await createListing(
        userId,
        crypto.randomUUID(),
        fd.get("title") as string,
        Number(fd.get("price")),
        Number(fd.get("geomCount")),
      )
      setStatus(`Listed: ${result.title}`)
      setListings((prev) => [
        ...prev,
        { listing_id: result.listing_id, title: result.title, price_tokens: result.price_tokens, geometry_count: Number(fd.get("geomCount")), status: "active" },
      ])
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Unknown"}`)
    }
  }

  const handlePurchase = async (listingId: string) => {
    try {
      const result = await purchaseListing(listingId, userId)
      setStatus(`Purchased — dataset ${result.dataset_id.slice(0, 8)} for ${result.tokens_paid} tokens`)
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : "Unknown"}`)
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Marketplace</h1>

      {status && (
        <p className="mb-4 rounded bg-blue-50 p-3 text-sm text-blue-800">{status}</p>
      )}

      <div className="mb-8 rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-semibold">List a Dataset</h2>
        <form onSubmit={handleCreateListing} className="flex flex-wrap gap-3">
          <input name="title" placeholder="Dataset title" required className="rounded border border-gray-300 px-3 py-2 text-sm" />
          <input name="price" type="number" step="0.01" placeholder="Price (tokens)" required className="w-32 rounded border border-gray-300 px-3 py-2 text-sm" />
          <input name="geomCount" type="number" placeholder="Geometry count" defaultValue={0} className="w-32 rounded border border-gray-300 px-3 py-2 text-sm" />
          <button type="submit" className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
            List
          </button>
        </form>
      </div>

      <h2 className="mb-3 text-lg font-semibold">Active Listings</h2>
      {listings.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">No listings yet. Create one above.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {listings.map((l) => (
            <div key={l.listing_id} className="rounded-lg border border-gray-200 bg-white p-4">
              <h3 className="font-semibold">{l.title}</h3>
              <p className="mt-1 text-sm text-gray-500">{l.geometry_count} polygons</p>
              <p className="mt-1 text-lg font-bold text-blue-700">{l.price_tokens} tokens</p>
              {l.status === "active" && (
                <button
                  onClick={() => handlePurchase(l.listing_id)}
                  className="mt-3 w-full rounded bg-green-600 px-3 py-2 text-sm text-white hover:bg-green-700"
                >
                  Purchase
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

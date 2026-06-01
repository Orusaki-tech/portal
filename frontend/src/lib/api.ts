const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------

export async function uploadDataset(
  userId: string,
  name: string,
  geometries: string[]
): Promise<{ set_id: string; polygon_count: number }> {
  const res = await fetch(`${API_BASE}/api/datasets/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, name, geometries }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function validatePolygon(
  gridId: string,
  polygonId: string,
  imagerySource = "naip"
): Promise<{ polygon_id: string; status: string; confidence: number }> {
  const res = await fetch(`${API_BASE}/api/datasets/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grid_id: gridId,
      polygon_id: polygonId,
      imagery_source: imagerySource,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function correctBoundary(
  gridId: string,
  polygonId: string,
  userId: string,
  newGeometry: string
): Promise<{ polygon_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/polygons/correct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grid_id: gridId,
      polygon_id: polygonId,
      user_id: userId,
      new_geometry: newGeometry,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Initiatives
// ---------------------------------------------------------------------------

export async function createInitiative(
  ownerId: string,
  name: string,
  region: string,
  gridSizeM = 1000
): Promise<{ initiative_id: string; status: string; name: string }> {
  const res = await fetch(`${API_BASE}/api/initiatives`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_id: ownerId, name, region, grid_size_m: gridSizeM }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function generateGridBlocks(
  initiativeId: string
): Promise<{ initiative_id: string; grids_generated: number }> {
  const res = await fetch(`${API_BASE}/api/initiatives/generate-grids`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initiative_id: initiativeId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function assignParticipant(
  initiativeId: string,
  userId: string,
  role = "annotator"
): Promise<{ initiative_id: string; user_id: string; role: string }> {
  const res = await fetch(`${API_BASE}/api/initiatives/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initiative_id: initiativeId, user_id: userId, role }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function lockGridBlock(
  gridId: string,
  userId: string
): Promise<{ grid_id: string; status: string; assigned_user_id: string }> {
  const res = await fetch(`${API_BASE}/api/grids/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grid_id: gridId, user_id: userId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Credits
// ---------------------------------------------------------------------------

export async function topUpCredits(
  userId: string,
  amount: number
): Promise<{ user_id: string; credits_remaining: number }> {
  const res = await fetch(`${API_BASE}/api/credits/top-up`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, amount }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export async function requestExport(
  userId: string,
  exportFormat: string,
  sourceType: string,
  sourceId: string
): Promise<{ export_id: string; status: string; export_format: string }> {
  const res = await fetch(`${API_BASE}/api/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      export_format: exportFormat,
      source_type: sourceType,
      source_id: sourceId,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Marketplace
// ---------------------------------------------------------------------------

export async function createListing(
  sellerId: string,
  datasetId: string,
  title: string,
  priceTokens: number,
  geometryCount = 0,
  description?: string
): Promise<{ listing_id: string; title: string; price_tokens: number }> {
  const res = await fetch(`${API_BASE}/api/marketplace/listings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      seller_id: sellerId,
      dataset_id: datasetId,
      title,
      price_tokens: priceTokens,
      geometry_count: geometryCount,
      description,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function purchaseListing(
  listingId: string,
  buyerId: string
): Promise<{ purchase_id: string; dataset_id: string; tokens_paid: number }> {
  const res = await fetch(`${API_BASE}/api/marketplace/purchase`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ listing_id: listingId, buyer_id: buyerId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Triage
// ---------------------------------------------------------------------------

export async function getTriage(
  params?: {
    initiative_id?: string
    priority_tier?: string
    page?: number
    per_page?: number
  }
): Promise<{ items: unknown[]; total: number; page: number; per_page: number }> {
  const search = new URLSearchParams()
  if (params?.initiative_id) search.set("initiative_id", params.initiative_id)
  if (params?.priority_tier) search.set("priority_tier", params.priority_tier)
  if (params?.page) search.set("page", String(params.page))
  if (params?.per_page) search.set("per_page", String(params.per_page))
  const qs = search.toString()
  const res = await fetch(`${API_BASE}/api/triage${qs ? `?${qs}` : ""}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

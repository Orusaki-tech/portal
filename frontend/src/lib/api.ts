import type { InitiativeResponse, GridBlockResponse, MarketplaceListingResponse, PaginatedResponse } from "@/types/api"
import type { ImagerySource, GeometryValidationResult, BatchValidationProgress } from "@/types/polygon"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {}
  const key = localStorage.getItem("realitysync_api_key")
  return key ? { Authorization: `Bearer ${key}` } : {}
}

export async function login(email: string): Promise<{ user_id: string; api_key: string; name: string; role: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function register(email: string, name: string): Promise<{ user_id: string; api_key: string; name: string; role: string }> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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

export async function fetchInitiatives(): Promise<{ items: InitiativeResponse[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/initiatives`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createInitiative(
  ownerId: string,
  name: string,
  region: string,
  gridSizeM = 1000
): Promise<{ initiative_id: string; status: string; name: string }> {
  const res = await fetch(`${API_BASE}/api/initiatives`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ initiative_id: initiativeId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchInitiative(
  id: string
): Promise<{ id: string; name: string; status: string; region: string; grid_size_m: number; budget_credits?: number; created_at?: string; completed_at?: string }> {
  const res = await fetch(`${API_BASE}/api/initiatives/${id}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchInitiativeGrids(
  id: string
): Promise<{ items: GridBlockResponse[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/initiatives/${id}/grids`, { headers: authHeaders() })
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ grid_id: gridId, user_id: userId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteInitiative(
  id: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/initiatives/${id}`, { method: "DELETE", headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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
  sourceId: string,
  filters?: {
    qa_status?: string
    confidence_min?: number
    confidence_max?: number
    include_original?: boolean
  }
): Promise<{ export_id: string; status: string; export_format: string }> {
  const res = await fetch(`${API_BASE}/api/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      user_id: userId,
      export_format: exportFormat,
      source_type: sourceType,
      source_id: sourceId,
      ...filters,
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ listing_id: listingId, buyer_id: buyerId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Marketplace
// ---------------------------------------------------------------------------

export async function getListings(): Promise<{
  listings: MarketplaceListingResponse[]
  total: number
}> {
  const res = await fetch(`${API_BASE}/api/marketplace/listings`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Triage
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// User Imagery
// ---------------------------------------------------------------------------

export async function fetchImagery(): Promise<{
  items: {
    imagery_id: string
    filename: string
    status: string
    cog_uri: string | null
    tile_url: string | null
  }[]
  total: number
}> {
  const res = await fetch(`${API_BASE}/api/imagery`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface EdgeMetric {
  vertex_index: number
  deviation_meters: number
  spectral_contrast: number
  snake_strain: number
  confidence_score: number
  is_ambiguous: boolean
}

export interface PolygonDetail {
  polygon_id: string
  polygon_set_id: string
  task_grid_id: string | null
  original_geometry: string
  corrected_geometry: string | null
  qa_status: string
  confidence_avg: number | null
  created_at: string
  edge_metrics: EdgeMetric[]
  corrections: {
    id: string
    user_id: string
    action: string
    corrected_geometry: string
    notes: string | null
    created_at: string
  }[]
}

export async function fetchPolygon(polygonId: string): Promise<PolygonDetail> {
  const res = await fetch(`${API_BASE}/api/polygons/${polygonId}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getTriage(
  params?: {
    initiative_id?: string
    priority_tier?: string
    page?: number
    per_page?: number
  }
): Promise<PaginatedResponse<unknown>> {
  const search = new URLSearchParams()
  if (params?.initiative_id) search.set("initiative_id", params.initiative_id)
  if (params?.priority_tier) search.set("priority_tier", params.priority_tier)
  if (params?.page) search.set("page", String(params.page))
  if (params?.per_page) search.set("per_page", String(params.per_page))
  const qs = search.toString()
  const res = await fetch(`${API_BASE}/api/triage${qs ? `?${qs}` : ""}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export interface LeaderboardEntry {
  id: string
  user_id: string
  score: number
  polygons_submitted: number
  accuracy_pct: number
  place: number
  submitted_at: string | null
}

export async function joinHackathon(initiativeId: string, userId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/hackathons/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ initiative_id: initiativeId, user_id: userId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function submitHackathonResult(
  initiativeId: string, userId: string, score: number, accuracyPct: number
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/hackathons/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ initiative_id: initiativeId, user_id: userId, score, accuracy_pct: accuracyPct }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getLeaderboard(initiativeId: string): Promise<{ items: LeaderboardEntry[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/hackathons/${initiativeId}/leaderboard`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchCredits(userId: string): Promise<{ user_id: string; credits_remaining: number }> {
  if (!userId) throw new Error("userId is required")
  const res = await fetch(`${API_BASE}/api/credits/${userId}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Imagery Sources
// ---------------------------------------------------------------------------

export async function fetchImagerySources(): Promise<{
  sources: ImagerySource[]
  total: number
}> {
  const res = await fetch(`${API_BASE}/api/imagery/sources`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// STAC
// ---------------------------------------------------------------------------

export async function queryStac(params: {
  stacUrl: string
  collection: string
  bbox?: [number, number, number, number]
  geometry?: Record<string, unknown>
  datetime?: string
  maxItems?: number
  authToken?: string
}): Promise<{
  items: {
    id: string
    bbox: [number, number, number, number]
    datetime: string
    cogUrl: string
    resolution: number | null
    cloudCover: number | null
  }[]
  total: number
}> {
  const res = await fetch(`${API_BASE}/api/stac/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Geometry Validation
// ---------------------------------------------------------------------------

export async function validateGeometries(
  geometries: { wkt: string; id: string }[]
): Promise<GeometryValidationResult[]> {
  const res = await fetch(`${API_BASE}/api/datasets/validate-geometries`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ geometries }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ---------------------------------------------------------------------------
// Batch Validation
// ---------------------------------------------------------------------------

export async function batchValidate(params: {
  geometries: string[]
  imagerySource: string
  userId: string
  datasetName: string
}): Promise<{ set_id: string; job_id: string; polygon_count: number }> {
  const res = await fetch(`${API_BASE}/api/datasets/batch-validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getBatchProgress(
  jobId: string
): Promise<BatchValidationProgress> {
  const res = await fetch(`${API_BASE}/api/datasets/batch-progress/${jobId}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

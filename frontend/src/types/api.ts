export interface InitiativeResponse {
  id: string
  owner_id: string
  name: string
  region: string
  status: string
  grid_size_m: number
  budget_credits: number | null
  created_at: string | null
  completed_at?: string | null
}

export interface GridBlockResponse {
  grid_id: string
  geometry: string
  status: string
  assigned_user_id: string | null
  polygon_count: number
}

export interface MarketplaceListingResponse {
  listing_id: string
  seller_id: string
  dataset_id: string
  title: string
  description: string | null
  price_tokens: number
  geometry_count: number
  status: string
  created_at: string | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

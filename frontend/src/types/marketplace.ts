export interface ExportJob {
  export_id: string
  user_id: string
  export_format: string
  source_type: string
  source_id: string
  status: "pending" | "processing" | "completed" | "failed"
  output_url?: string
  error_message?: string
  created_at?: string
  completed_at?: string
}

export interface MarketplaceListing {
  listing_id: string
  seller_id: string
  dataset_id: string
  title: string
  description?: string
  price_tokens: number
  geometry_count: number
  status: "active" | "sold" | "archived"
  created_at?: string
}

export interface DatasetPurchase {
  purchase_id: string
  listing_id: string
  buyer_id: string
  dataset_id: string
  tokens_paid: number
  purchased_at?: string
}

export interface Participant {
  initiative_id: string
  user_id: string
  role: "annotator" | "reviewer" | "manager"
  joined_at?: string
}

export interface VertexMetric {
  vertex_index: number
  deviation_meters: number
  spectral_contrast: number
  snake_strain: number
  confidence_score: number
}

export interface EdgeResult {
  polygon_id: string
  run_id: string
  is_ambiguous: boolean
  confidence_avg: number
  vertices: VertexMetric[]
  processed_at: string
}

export type QaStatus =
  | "pending"
  | "validated"
  | "low_confidence"
  | "corrected"
  | "escalated"

export interface PolygonFeature {
  id: string
  type: "Feature"
  geometry: {
    type: "Polygon"
    coordinates: number[][][]
  }
  properties: {
    original_geometry?: string
    qa_status: QaStatus
    confidence_avg?: number
    corrected_geometry?: string
  }
}

export interface TriageItem {
  polygon_id: string
  polygon_set_id: string
  qa_status: string
  computed_confidence: number
  avg_deviation_m: number
  ambiguous_vertices: number
  correction_count: number
  priority_tier: "auto_approved" | "needs_review" | "needs_correction" | "escalate"
}

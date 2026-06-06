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

export type ImagerySourceType = "xyz" | "stac" | "cog"

export interface ImagerySource {
  id: string
  label: string
  tileUrl: string
  attribution: string
  type: ImagerySourceType
  resolution: string
  coverage: string
  stacUrl?: string
  stacCollection?: string
  thumbnail?: string
}

export interface StacSource {
  id: string
  label: string
  stacUrl: string
  stacCollection: string
  authToken?: string
  attribution: string
  resolution: string
  coverage: string
  tileUrl?: string
}

export interface GeometryValidationResult {
  index: number
  vertexCount: number
  areaSqM: number
  isValid: boolean
  isSimple: boolean
  hasSelfIntersections: boolean
  hasWrongRingOrientation: boolean
  isDegenerate: boolean
  bbox: [number, number, number, number] | null
  warnings: string[]
  errors: string[]
}

export type GeometryStatus = "valid" | "warning" | "error"

export interface ParsedGeometry {
  id: string
  wkt: string
  coords: number[][][]
  validation: GeometryValidationResult | null
  status: GeometryStatus
  properties: Record<string, unknown>
}

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

export interface BatchValidationProgress {
  total: number
  completed: number
  status: "pending" | "running" | "complete" | "error"
  results?: BatchValidationResult[]
}

export interface BatchValidationResult {
  polygon_id: string
  status: string
  confidence: number
  deviation_m: number
  ambiguous_vertices: number
}

export const IMAGERY_SOURCES: ImagerySource[] = [
  {
    id: "naip",
    label: "NAIP (60cm, US)",
    tileUrl: "/tiles/naip/{z}/{x}/{y}.png",
    attribution: "USDA NAIP — Planet Labs",
    type: "xyz",
    resolution: "60cm–1m",
    coverage: "Continental US",
    thumbnail: "🛰️",
  },
  {
    id: "sentinel-2-l2a",
    label: "Sentinel-2 L2A (10m, Global)",
    tileUrl: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "ESA Copernicus — Esri",
    type: "stac",
    resolution: "10m",
    coverage: "Global",
    stacUrl: "https://planetarycomputer.microsoft.com/api/stac/v1",
    stacCollection: "sentinel-2-l2a",
    thumbnail: "🛰️",
  },
  {
    id: "landsat-c2-l2",
    label: "Landsat 8/9 (30m, Global)",
    tileUrl: "",
    attribution: "USGS — Microsoft Planetary Computer",
    type: "stac",
    resolution: "30m",
    coverage: "Global",
    stacUrl: "https://planetarycomputer.microsoft.com/api/stac/v1",
    stacCollection: "landsat-c2-l2",
    thumbnail: "🌍",
  },
  {
    id: "esri-world-imagery",
    label: "Esri World Imagery (~1m, Global)",
    tileUrl: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri, Maxar, Earthstar Geographics",
    type: "xyz",
    resolution: "~1m",
    coverage: "Global",
    thumbnail: "🌐",
  },
  {
    id: "sentinel-1-rtc",
    label: "Sentinel-1 SAR (10m, Global)",
    tileUrl: "",
    attribution: "ESA — Microsoft Planetary Computer",
    type: "stac",
    resolution: "10m",
    coverage: "Global",
    stacUrl: "https://planetarycomputer.microsoft.com/api/stac/v1",
    stacCollection: "sentinel-1-rtc",
    thumbnail: "📡",
  },
  {
    id: "cbers-4-mux",
    label: "CBERS-4 (64m, Latin America)",
    tileUrl: "",
    attribution: "INPE — Brazil Data Cube",
    type: "stac",
    resolution: "64m",
    coverage: "Latin America",
    stacUrl: "https://data.inpe.br/bdc/stac/v1/",
    stacCollection: "CBERS4-MUX",
    thumbnail: "🛰️",
  },
  {
    id: "amazonia-1-wfi",
    label: "Amazonia-1 WFI (64m, Brazil)",
    tileUrl: "",
    attribution: "INPE — Brazil Data Cube",
    type: "stac",
    resolution: "64m",
    coverage: "Brazil",
    stacUrl: "https://data.inpe.br/bdc/stac/v1/",
    stacCollection: "AMAZONIA1-WFI",
    thumbnail: "🛰️",
  },
  {
    id: "cop-dem-glo-30",
    label: "Copernicus DEM (30m, Global)",
    tileUrl: "",
    attribution: "ESA — Microsoft Planetary Computer",
    type: "stac",
    resolution: "30m",
    coverage: "Global",
    stacUrl: "https://planetarycomputer.microsoft.com/api/stac/v1",
    stacCollection: "cop-dem-glo-30",
    thumbnail: "⛰️",
  },
  {
    id: "osm",
    label: "OpenStreetMap (Reference)",
    tileUrl: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "OpenStreetMap contributors",
    type: "xyz",
    resolution: "N/A",
    coverage: "Global",
    thumbnail: "🗺️",
  },
]

export interface PreprocessingOptions {
  cloud_mask?: boolean
  cloud_mask_method?: "scl" | "qa_pixel" | "s2cloudless"
  speckle_filter?: boolean
  pansharpen?: false | "brovey" | "pca" | "ihs"
}

export interface ImageryFetchRequest {
  source_id: string
  geojson: GeoJSON.GeoJSON
  buffer_meters: number
  date_from?: string
  date_to?: string
  max_cloud_cover: number
  mosaic: boolean
  preprocessing?: PreprocessingOptions
}

export type FetchStatus = "idle" | "previewing" | "processing" | "ready" | "error"

export interface ImageryFetchResponse {
  status: "preview" | "processing" | "ready" | "error"
  job_hash: string
  preview_available: boolean
  preview_url?: string
  cog_url?: string
  scene_count?: number
  scene_ids?: string[]
  datetime_from?: string
  datetime_to?: string
  cloud_cover_avg?: number
  resolution?: number
  area_km2?: number
  source_type?: string
  cached?: boolean
  error?: string
  preprocessing_applied?: string[]
}

export type AdminLevel = "admin0" | "admin1" | "admin2"

export interface AdminBoundary {
  id: string
  name: string
  level: AdminLevel
  pcode: string
  parentPcode?: string
  parentName?: string
  center: [number, number]
  areaSqKm: number
}

export interface VectorOverlay {
  id: string
  name: string
  visible: boolean
  color: string
  opacity: number
  data?: GeoJSON.FeatureCollection
  dataUrl?: string
  type: "admin" | "custom"
  level?: AdminLevel
}

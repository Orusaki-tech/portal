# Domain Model

## Ubiquitous Language

| Term | Definition |
|------|------------|
| **Polygon** | A geospatial boundary (building footprint, field boundary, etc.) needing validation. Entity within a `TaskGrid` aggregate. Has ≥3 vertices and a validation status. |
| **TaskGrid** | A 1km² grid block. The **aggregate root** and transactional consistency boundary. Contains many Polygons. Has a lifecycle: `pending → in_progress (locked) → complete`. |
| **Initiative** | A named collection of TaskGrids covering a region of interest. Owned by a user, worked on by participants. Has a budget in credits and a deadline. |
| **ValidationRun** | A batch process that runs edge detection against a set of Polygons over specific imagery. Creates `VertexMetric` records per polygon. |
| **VertexMetric** | Value object. Per-vertex edge detection results: deviation (meters), spectral contrast, snake strain, confidence score (0.0–1.0). |
| **EdgeResult** | The aggregate output of validating one polygon: summary confidence, per-vertex metrics, ambiguous flag. |
| **ConfidenceScore** | Value object. Composite of three weighted metrics: 40% spectral contrast, 30% snake strain (inverted), 30% deviation (inverted). |
| **Correction** | A human-submitted revised geometry for a low-confidence polygon. Includes original + new geometry, annotator identity, and QA notes. |
| **Credit** | Unit of pre-paid validation work. Consumed per polygon validated or per edge detect run. |
| **NAIP** | National Agriculture Imagery Program. 30cm–60cm resolution multispectral aerial imagery covering continental US. |

---

## Aggregates & Consistency Boundaries

### `TaskGrid` (Primary Aggregate)

The `TaskGrid` is the **consistency boundary** — not the individual Polygon. Rationale:

- In multi-user mode, two annotators should not edit the same grid block simultaneously
- Row-locking a grid block is cheaper and simpler than locking individual polygons
- QA peer review operates at the grid block level (two annotations → tiebreaker → merge)

```
TaskGrid {
  id: UUID
  initiative_id: UUID
  geometry: POLYGON(4326)  // 1km² bounding box
  status: pending | in_progress | awaiting_review | complete | disputed
  assigned_user_id: UUID?
  locked_at: Timestamp?
  completed_at: Timestamp?
  review_notes: TEXT?

  // Behaviors
  assign_to(user): void
  lock(): void                     // Row-level lock acquired
  submit_qc(user, corrections[]): void
  mark_complete(): void
  dispute(reason): void

  // Invariants
  - Cannot transition from complete → any other state
  - Cannot assign if already assigned (unless released)
  - Cannot lock if already locked (prevents concurrent edits)
  - Can only submit QC if locked by this user
}
```

### `ValidationRun` (Secondary Aggregate)

A separate aggregate because it spans multiple TaskGrids/Polygons and has its own lifecycle independent of grid state.

```
ValidationRun {
  id: UUID
  user_id: UUID
  polygon_set_id: UUID
  imagery_id: UUID?
  region: GEOMETRY
  status: queued | processing | complete | failed
  polygon_count: int
  ambiguous_count: int
  cost_credits: decimal
  created_at: Timestamp
  completed_at: Timestamp?
}
```

---

## Entities

### `Polygon`

```
Polygon {
  id: UUID
  task_grid_id: UUID           // FK to parent aggregate
  polygon_set_id: UUID         // FK to source set
  original_geometry: POLYGON(4326)
  corrected_geometry: POLYGON(4326)?  // Set after human correction
  qa_status: pending | validated | low_confidence | corrected | escalated
  confidence_avg: float?       // Cached from latest ValidationRun
  properties: JSONB            // Original ML model metadata
  created_at: Timestamp
}
```

### `User`

```
User {
  id: UUID
  email: str                   // Unique
  name: str
  role: admin | manager | annotator | reviewer | senior_reviewer | viewer
  credits_remaining: Decimal   // Must always be ≥ 0
  subscription_tier: free | starter | professional
  api_key: str?
  created_at: Timestamp
  updated_at: Timestamp
}
```

### `Initiative`

```
Initiative {
  id: UUID
  owner_id: UUID
  name: str
  region: GEOMETRY
  status: draft | active | paused | complete | archived
  grid_size_m: int
  budget_credits: Decimal?
  hackathon_mode: bool
  max_participants: int?
  created_at: Timestamp
  completed_at: Timestamp?
}
```

### `Correction`

```
Correction {
  id: UUID
  polygon_id: UUID
  user_id: UUID
  original_geometry: POLYGON
  corrected_geometry: POLYGON
  action: correct | refine | reset
  notes: str?
  created_at: Timestamp
}
```

### `ExportJob`

```
ExportJob {
  export_id: UUID
  user_id: UUID
  export_format: geojson | coco | yolo | pascal_voc | tfrecord | parquet | geopackage
  source_type: dataset | initiative | grid
  source_id: UUID
  status: pending | processing | complete | failed
  output_url: str?
  error_message: str?
  export_params: dict?       // Filters: qa_status, confidence_min/max, include_original
  created_at: Timestamp?
  completed_at: Timestamp?
}
```

### `MarketplaceListing`

```
MarketplaceListing {
  listing_id: UUID
  seller_id: UUID
  dataset_id: UUID
  title: str
  price_tokens: Decimal
  geometry_count: int
  quality_score: float?       // 0.0–1.0, computed from polygon confidence
  completion_rate: float?     // 0.0–1.0, computed from polygon validation status
  description: str?
  status: active | sold | archived
  created_at: Timestamp?
}
```

### `DatasetPurchase`

```
DatasetPurchase {
  purchase_id: UUID
  listing_id: UUID
  buyer_id: UUID
  dataset_id: UUID
  tokens_paid: Decimal
  purchased_at: Timestamp?
}
```

### `CreditTransaction`

```
CreditTransaction {
  id: UUID
  user_id: UUID
  amount: Decimal
  transaction_type: top_up | validation | correction | purchase | refund
  reference_id: UUID?
  description: str?
  created_at: Timestamp?
}
```

### `LeaderboardEntry`

```
LeaderboardEntry {
  id: UUID
  initiative_id: UUID
  user_id: UUID
  score: float (0.0–1.0)
  polygons_submitted: int
  accuracy_pct: float (0.0–100.0)
  place: int?
  submitted_at: Timestamp?
}
```

---

## Value Objects

| Value Object | Fields | Immutable | Notes |
|---|---|---|---|
| `ConfidenceScore` | `overall: float(0..1)`, `per_vertex: list[float]` | Yes | Computed, not stored directly |
| `VertexMetric` | `vertex_index: int`, `deviation_m: float`, `spectral_contrast: float`, `snake_strain: float`, `confidence_score: float` | Yes | Per-vertex edge detection output |
| `Coordinate` | `longitude: float`, `latitude: float` | Yes | WGS-84 decimal degrees |

---

## Domain Events

| Event | Raised When | Payload | Handlers |
|---|---|---|---|
| `GridBlockLocked` | Grid block is locked by a user | `grid_id: UUID`, `user_id: UUID` | `handle_validate_on_lock` |
| `GridBlockSubmitted` | All polygons in a grid block are reviewed | `grid_id: UUID`, `initiative_id: UUID` | `handle_check_grid_complete` |
| `GridBlockCompleted` | All polygons in a TaskGrid are resolved | `grid_id: UUID`, `initiative_id: UUID` | `handle_check_initiative_complete` |
| `GridBlockDisputed` | Grid block review fails peer review | `grid_id: UUID`, `initiative_id: UUID` | `handle_flag_for_senior_review` |
| `InitiativeCompleted` | All grid blocks in an initiative are complete | `initiative_id: UUID`, `owner_id: UUID` | `handle_initiative_completed_notification` |
| `DatasetPurchased` | A dataset is bought on the marketplace | `listing_id: UUID`, `buyer_id: UUID`, `dataset_id: UUID` | `handle_dataset_purchased_notification` |
| `HackathonJoined` | A user joins a hackathon initiative | `initiative_id: UUID`, `user_id: UUID` | `handle_hackathon_joined_notification` |
| `ConsensusReached` | Peer review reaches consensus on a disputed polygon | `polygon_id: UUID`, `grid_id: UUID`, `merged_geometry: str` | (TODO) |
| `HackathonScoreUpdated` | Hackathon leaderboard score changes | `initiative_id: UUID`, `user_id: UUID`, `new_score: float` | (TODO) |
| `BoundaryCorrected` | Human submits a correction | `polygon_id: UUID`, `user_id: UUID`, `new_geometry: POLYGON`, `old_geometry: POLYGON` | `handle_update_geometry`, `handle_deduct_credits` |
| `CreditsExhausted` | User's credits_remaining reaches 0 | `user_id: UUID` | `handle_pause_validation` |

---

## Invariants (Enforced in Domain Models)

1. **TaskGrid state machine**: `pending → in_progress → awaiting_review → complete`. No backwards transitions. `complete` is terminal.
2. **Non-negative credits**: `User.credits_remaining` must never go below 0. Enforced at the aggregate level before any credit-consuming operation.
3. **Minimum vertices**: `Polygon.original_geometry` must have ≥3 vertices (closed ring, PostGIS enforces this but domain validates in Python too).
4. **Spatial containment**: A Polygon's centroid must fall within its parent `TaskGrid` geometry.
5. **Unique grid assignment**: A `TaskGrid` cannot be assigned to two users simultaneously (row-lock + status check).
6. **Confidence bounds**: `ConfidenceScore.overall` and all `per_vertex` values must be in `[0.0, 1.0]`.
7. **Correction ownership**: Only the user who locked a TaskGrid can submit corrections for its polygons.
8. **No double-counting credits**: A ValidationRun consumes credits once at initiation, not per-polygon.

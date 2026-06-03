# Data Model

## ERD (ASCII)

```
┌──────────────┐       ┌──────────────────┐       ┌───────────────────┐
│    users     │       │ ml_polygon_sets   │       │    initiatives    │
├──────────────┤       ├──────────────────┤       ├───────────────────┤
│ id (PK)      │──┐    │ id (PK)          │       │ id (PK)           │
│ email        │  │    │ user_id (FK)     │──┐    │ owner_id (FK)─────┤
│ name         │  │    │ name             │  │    │ name              │
│ role         │  │    │ model_version    │  │    │ description       │
│ credits_remain│  │    │ description      │  │    │ region (GEOM)     │
│ subscription_ │  │    │ created_at       │  │    │ status            │
│   tier       │  │    └──────────────────┘  │    │ grid_size_m       │
│ api_key      │  │                          │    │ budget_credits    │
│ created_at   │  │    ┌──────────────┐      │    │ hackathon_mode    │
│ updated_at   │  │    │ ml_polygons  │      │    │ max_participants  │
└──────────────┘  │    ├──────────────┤      │    │ created_at        │
                  └────│ id (PK)     │      │    │ completed_at      │
                       │ polygon_set_id│────┘    └───────────────────┘
                       │ original_geom (POLYGON)        │
                       │ qa_status    │                 │
                       │ confidence_avg│                │
                       │ corrected_geom│                │
                       │ properties (JSONB)             │
                       │ created_at   │                 │
                       └──────┬───────┘                 │
                              │                         │
              ┌───────────────┼──────────────┐          │
              ▼               ▼              ▼          │
┌──────────────────┐ ┌──────────────┐ ┌────────────┐   │
│  edge_metrics    │ │ human_correct.│ │user_imagery│   │
├──────────────────┤ ├──────────────┤ ├────────────┤   │
│ id (PK)          │ │ id (PK)      │ │ id (PK)    │   │
│ polygon_id (FK)──┘ │ polygon_id   │ │ user_id(FK)│   │
│ run_id            │ │ user_id(FK)  │ │ gcs_uri    │   │
│ vertex_index      │ │ orig_geom    │ │ cog_uri    │   │
│ deviation_meters  │ │ corrected_geo│ │ bbox(GEOM) │   │
│ spectral_contrast │ │ action       │ │ resolution │   │
│ snake_strain      │ │ notes        │ │ status     │   │
│ confidence_score  │ │ created_at   │ │ stac_record│   │
│ is_ambiguous      │ └──────────────┘ │ created_at │   │
│ created_at        │                  │ processed  │   │
└──────────────────┘                  └───────┬─────┘   │
                                              │         │
                                    ┌─────────┴────────┐│
                                    │ validation_runs  ││
                                    ├──────────────────┤│
                                    │ id (PK)          ││
                                    │ user_id(FK)──────┘│
                                    │ polygon_set_id(FK)│
                                    │ polygon_count   ││
                                    │ cost_credits    ││
                                    │ status          ││
                                    │ created_at      ││
                                    │ completed_at    ││
                                    └──────────────────┘

┌─────────────────────────┐         ┌───────────────────────────────┐
│   map_task_grid         │         │   credit_transactions         │
├─────────────────────────┤         ├───────────────────────────────┤
│ grid_id (PK)            │         │ id (PK)                      │
│ initiative_id(FK)───────┤         │ user_id (FK)─────────────────┤
│ geometry (POLYGON)      │         │ amount (Decimal)             │
│ status                  │         │ transaction_type             │
│ assigned_user_id(FK)────┤         │ reference_id (UUID?)         │
│ locked_at               │         │ description (text?)          │
│ completed_at            │         │ created_at                   │
│ review_notes            │         └───────────────────────────────┘
└─────────────────────────┘

┌───────────────────────────────┐   ┌───────────────────────────────┐
│ initiative_participants       │   │      export_jobs              │
├───────────────────────────────┤   ├───────────────────────────────┤
│ initiative_id (FK) (COMPOSITE │   │ export_id (PK)               │
│ user_id (FK)     │  PK)      │   │ user_id (FK)─────────────────┤
│ role                        │   │ export_format                │
│ joined_at                   │   │ source_type                  │
└───────────────────────────────┘   │ source_id                    │
                                    │ status                       │
┌───────────────────────────────┐   │ output_url (text?)           │
│ marketplace_listings          │   │ error_message (text?)        │
├───────────────────────────────┤   │ export_params (JSONB?)       │
│ listing_id (PK)              │   │ created_at                   │
│ seller_id (FK)───────────────┤   │ completed_at                 │
│ dataset_id (FK)──────────────┤   └───────────────────────────────┘
│ title                        │
│ price_tokens (Decimal)       │   ┌───────────────────────────────┐
│ geometry_count               │   │ dataset_purchases            │
│ quality_score (real?)        │   ├───────────────────────────────┤
│ completion_rate (real?)      │   │ purchase_id (PK)             │
│ description (text?)          │   │ listing_id (FK)──────────────┤
│ status                       │   │ buyer_id (FK)────────────────┤
│ created_at                   │   │ dataset_id (FK)──────────────┤
└───────────────────────────────┘   │ tokens_paid (Decimal)        │
                                    │ purchased_at                 │
┌───────────────────────────────┐   └───────────────────────────────┘
│ hackathon_leaderboard        │
├───────────────────────────────┤
│ id (PK)                      │
│ initiative_id (FK)───────────┤
│ user_id (FK)─────────────────┤
│ score (real)                 │
│ polygons_submitted (int)     │
│ accuracy_pct (real)          │
│ place (int?)                 │
│ submitted_at                 │
└───────────────────────────────┘
```

---

## Table Reference

### `users`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `email` | `varchar(255)` | `NOT NULL UNIQUE` | Used for auth + notifications |
| `name` | `varchar(255)` | `NOT NULL` | Display name |
| `role` | `varchar(20)` | `NOT NULL CHECK (role IN ('admin','manager','annotator','reviewer','senior_reviewer','viewer'))` | |
| `credits_remaining` | `decimal(12,2)` | `NOT NULL DEFAULT 0 CHECK (credits_remaining >= 0)` | Invariant: must never be negative |
| `subscription_tier` | `varchar(20)` | `NOT NULL DEFAULT 'free' CHECK (IN ('free','starter','professional'))` | |
| `api_key` | `varchar(64)` | `UNIQUE` | API key for programmatic access |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `UNIQUE (email)`

---

### `ml_polygon_sets`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Owner |
| `name` | `varchar(255)` | `NOT NULL` | e.g. "Austin Buildings v1" |
| `model_version` | `varchar(100)` | | ML model that produced these |
| `description` | `text` | | |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `(user_id)`

---

### `ml_polygons`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `polygon_set_id` | `uuid` | `NOT NULL REFERENCES ml_polygon_sets(id) ON DELETE CASCADE` | Source set |
| `original_geometry` | `geometry(Polygon,4326)` | `NOT NULL` | Original ML output |
| `qa_status` | `varchar(20)` | `NOT NULL DEFAULT 'pending' CHECK (IN ('pending','validated','low_confidence','corrected','escalated'))` | |
| `confidence_avg` | `real` | | Cached from latest edge run |
| `corrected_geometry` | `geometry(Polygon,4326)` | | Set by human correction |
| `properties` | `jsonb` | `NOT NULL DEFAULT '{}'` | Original ML metadata |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `GIST (original_geometry)`, `(qa_status)`, `(polygon_set_id)`

---

### `edge_metrics`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `polygon_id` | `uuid` | `NOT NULL REFERENCES ml_polygons(id) ON DELETE CASCADE` | |
| `run_id` | `uuid` | `NOT NULL` | Correlates with validation_runs |
| `vertex_index` | `int` | `NOT NULL` | 0-indexed position in ring |
| `deviation_meters` | `real` | | Distance from ML boundary to detected edge |
| `spectral_contrast` | `real` | `CHECK (0.0 <= spectral_contrast <= 1.0)` | Inter-cluster distance |
| `snake_strain` | `real` | | Energy required to fit snake |
| `confidence_score` | `real` | `CHECK (0.0 <= confidence_score <= 1.0)` | Composite score |
| `is_ambiguous` | `boolean` | `NOT NULL` | `true` if confidence < 0.70 |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `(polygon_id, run_id)`, `(is_ambiguous)` — supports triage queue query

---

### `human_corrections`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `polygon_id` | `uuid` | `NOT NULL REFERENCES ml_polygons(id) ON DELETE CASCADE` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | Annotator |
| `original_geometry` | `geometry(Polygon,4326)` | `NOT NULL` | Snapshot before edit |
| `corrected_geometry` | `geometry(Polygon,4326)` | `NOT NULL` | Snapshot after edit |
| `action` | `varchar(20)` | `NOT NULL CHECK (IN ('correct','confirm','escalate','skip'))` | |
| `notes` | `text` | | Annotator notes |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `(polygon_id, user_id)`, `(created_at DESC)`

---

### `initiatives`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `owner_id` | `uuid` | `NOT NULL REFERENCES users(id)` | Creator |
| `name` | `varchar(255)` | `NOT NULL` | |
| `description` | `text` | | |
| `region` | `geometry(Geometry,4326)` | `NOT NULL` | Area of interest |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'draft' CHECK (IN ('draft','active','paused','complete','archived'))` | |
| `grid_size_m` | `int` | `NOT NULL DEFAULT 1000` | Grid block size in meters |
| `budget_credits` | `decimal(12,2)` | | Pre-allocated credits |
| `hackathon_mode` | `boolean` | `NOT NULL DEFAULT false` | Enables leaderboard + scoring |
| `max_participants` | `int` | | Cap on hackathon participants |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `completed_at` | `timestamptz` | | |

**Indexes:** `GIST (region)`, `(owner_id)`, `(status)`

---

### `initiative_participants`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `initiative_id` | `uuid` | `NOT NULL REFERENCES initiatives(id) ON DELETE CASCADE` | Composite PK |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | Composite PK |
| `role` | `varchar(20)` | `NOT NULL CHECK (IN ('annotator','reviewer','manager'))` | |
| `joined_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** Primary key on `(initiative_id, user_id)`

---

### `map_task_grid`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `grid_id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `initiative_id` | `uuid` | `NOT NULL REFERENCES initiatives(id) ON DELETE CASCADE` | |
| `geometry` | `geometry(Polygon,4326)` | `NOT NULL` | 1km² cell |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'pending' CHECK (IN ('pending','in_progress','awaiting_review','complete','disputed'))` | State machine |
| `assigned_user_id` | `uuid` | `REFERENCES users(id)` | Current editor |
| `locked_at` | `timestamptz` | | Row-lock timestamp |
| `completed_at` | `timestamptz` | | |
| `review_notes` | `text` | | |

**Indexes:** `GIST (geometry)`, `(initiative_id, status)`, `(assigned_user_id)`

---

### `user_imagery`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | |
| `original_filename` | `varchar(500)` | `NOT NULL` | |
| `gcs_uri` | `text` | `NOT NULL` | Landing bucket URI |
| `cog_uri` | `text` | | Production bucket URI |
| `bounding_box` | `geometry(Polygon,4326)` | | Extracted during GDAL processing |
| `resolution_cm` | `int` | | GSD from metadata |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'uploaded' CHECK (IN ('uploaded','processing','ready','failed'))` | |
| `stac_record` | `jsonb` | | STAC item metadata |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `processed_at` | `timestamptz` | | COG ready timestamp |

**Indexes:** `(user_id, status)`, `GIST (bounding_box)`

---

### `validation_runs`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | Requestor |
| `polygon_set_id` | `uuid` | `REFERENCES ml_polygon_sets(id)` | |
| `polygon_count` | `int` | `DEFAULT 0` | |
| `cost_credits` | `decimal(12,2)` | `DEFAULT 0` | Credits consumed |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'queued' CHECK (IN ('queued','processing','complete','failed'))` | |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `completed_at` | `timestamptz` | | |

---

### `credit_transactions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | |
| `amount` | `decimal(12,2)` | `NOT NULL` | Positive = top-up, negative = spend |
| `transaction_type` | `varchar(20)` | `NOT NULL CHECK (IN ('top_up','validation','correction','purchase','refund'))` | |
| `reference_id` | `uuid` | | Links to related entity |
| `description` | `text` | | |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `(user_id, created_at DESC)`

---

### `export_jobs`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `export_id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | |
| `export_format` | `varchar(20)` | `NOT NULL CHECK (IN ('geojson','coco','yolo','pascal_voc','tfrecord','parquet','geopackage'))` | |
| `source_type` | `varchar(20)` | `NOT NULL CHECK (IN ('dataset','initiative','grid'))` | |
| `source_id` | `uuid` | `NOT NULL` | |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'pending' CHECK (IN ('pending','processing','complete','failed'))` | |
| `output_url` | `text` | | |
| `error_message` | `text` | | |
| `export_params` | `jsonb` | `DEFAULT '{}'` | Filter params: qa_status, confidence_min/max, include_original |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `completed_at` | `timestamptz` | | |

**Indexes:** `(user_id, created_at DESC)`, `(status)`

---

### `marketplace_listings`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `listing_id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `seller_id` | `uuid` | `NOT NULL REFERENCES users(id)` | |
| `dataset_id` | `uuid` | `NOT NULL REFERENCES ml_polygon_sets(id)` | |
| `title` | `varchar(255)` | `NOT NULL` | |
| `price_tokens` | `decimal(12,2)` | `NOT NULL CHECK (price_tokens >= 0)` | |
| `geometry_count` | `int` | `NOT NULL DEFAULT 0` | |
| `quality_score` | `real` | | Computed from polygon confidence |
| `completion_rate` | `real` | | Computed from polygon validation status |
| `description` | `text` | | |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'active' CHECK (IN ('active','sold','archived'))` | |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `(seller_id)`, `(status)`

---

### `dataset_purchases`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `purchase_id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `listing_id` | `uuid` | `NOT NULL REFERENCES marketplace_listings(listing_id)` | |
| `buyer_id` | `uuid` | `NOT NULL REFERENCES users(id)` | |
| `dataset_id` | `uuid` | `NOT NULL REFERENCES ml_polygon_sets(id)` | |
| `tokens_paid` | `decimal(12,2)` | `NOT NULL` | |
| `purchased_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:** `(buyer_id)`, `(listing_id)`

---

### `hackathon_leaderboard`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `initiative_id` | `uuid` | `NOT NULL REFERENCES initiatives(id)` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id)` | |
| `score` | `real` | `NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 1.0)` | |
| `polygons_submitted` | `int` | `NOT NULL DEFAULT 0` | |
| `accuracy_pct` | `real` | `NOT NULL DEFAULT 0 CHECK (accuracy_pct >= 0 AND accuracy_pct <= 100.0)` | |
| `place` | `int` | | Computed rank |
| `submitted_at` | `timestamptz` | | |

**Indexes:** `UNIQUE (initiative_id, user_id)`, `(initiative_id, score DESC)`

---

**Indexes:** `(user_id, created_at DESC)`, `(status)`

---

## Index Strategy

| Query Pattern | Index | Type |
|---|---|---|
| Find polygons in viewport | `ml_polygons.original_geometry` | GIST |
| Triage queue (ambiguous only) | `edge_metrics.is_ambiguous` | B-tree |
| Polygons by QA status | `ml_polygons.qa_status` | B-tree |
| Grid blocks for an initiative | `map_task_grid.initiative_id` | B-tree |
| User's active validations | `validation_runs.user_id` | B-tree |
| Credit history for a user | `credit_transactions.user_id` | B-tree |
| Export jobs for a user | `export_jobs.user_id` | B-tree |
| Active marketplace listings | `marketplace_listings.status` | B-tree |
| Hackathon leaderboard ranking | `hackathon_leaderboard.initiative_id + score` | Composite B-tree |
| Spatial intersection (any geometry column) | All geometry columns | GIST |
| Initiative progress heatmap | `map_task_grid.initiative_id + status` | Composite B-tree |

---

## Migration Pattern

### Naming Convention
```
NNN_descriptive_name.sql
```

Examples: `001_users.sql`, `002_polygons.sql`, `003_corrections.sql`

### Rules
1. **Idempotent**: Use `IF NOT EXISTS` for all creates, `IF EXISTS` for drops
2. **Sequential**: New migrations append, never renumber
3. **Implicit transactions**: Each migration runs in its own transaction
4. **No rollback files**: Rollbacks are written on-demand when needed
5. **Comments**: Every table and column has a `COMMENT ON` for dbt docs

### Runner
`database/run_migrations.py` — reads `database/migrations/*.sql` in order, applies with psycopg2, tracks applied migrations in a `_migrations` table.

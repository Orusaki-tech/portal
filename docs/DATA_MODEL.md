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
│ created_at   │  │    │ created_at       │  │    │ status            │
│ updated_at   │  │    └──────────────────┘  │    │ grid_size_m       │
└──────────────┘  │    └──────────────────┘  │    │ budget_credits    │
                  │                          │    │ created_at        │
                  │    ┌──────────────┐      │    │ completed_at      │
                  │    │ ml_polygons  │      │    └───────────────────┘
                  │    ├──────────────┤      │           │
                  └────│ id (PK)     │      │           │
                       │ polygon_set_id│────┘           │
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
                                    │ imagery_id(FK)────┘
                                    │ region (GEOM)     │
                                    │ status            │
                                    │ polygon_count     │
                                    │ ambiguous_count   │
                                    │ cost_credits      │
                                    │ created_at        │
                                    │ completed_at      │
                                    └──────────────────┘

┌─────────────────────────┐
│   map_task_grid         │
├─────────────────────────┤
│ grid_id (PK)            │
│ initiative_id(FK)───────┤
│ geometry (POLYGON)      │
│ status                  │
│ assigned_user_id(FK)────┤
│ locked_at               │
│ completed_at            │
│ review_notes            │
└─────────────────────────┘

┌───────────────────────────────┐
│ initiative_participants       │
├───────────────────────────────┤
│ initiative_id (FK) (COMPOSITE │
│ user_id (FK)     │  PK)      │
│ role                        │
│ joined_at                   │
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
| `role` | `varchar(20)` | `NOT NULL CHECK (role IN ('admin','manager','annotator','reviewer'))` | |
| `credits_remaining` | `decimal(12,2)` | `NOT NULL DEFAULT 0 CHECK (credits_remaining >= 0)` | Invariant: must never be negative |
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
| `imagery_id` | `uuid` | `REFERENCES user_imagery(id)` | Optional custom imagery |
| `region` | `geometry(Geometry,4326)` | | Extent of this run |
| `status` | `varchar(20)` | `NOT NULL DEFAULT 'queued' CHECK (IN ('queued','processing','complete','failed'))` | |
| `polygon_count` | `int` | `DEFAULT 0` | |
| `ambiguous_count` | `int` | `DEFAULT 0` | |
| `cost_credits` | `decimal(12,2)` | `DEFAULT 0` | Credits consumed |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `completed_at` | `timestamptz` | | |

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

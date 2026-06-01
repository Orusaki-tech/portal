# Phase Plan — RealitySync Build

## Phase 0: Foundation (Current Session)

| Task | Files | Verification |
|---|---|---|
| Write 6 reference docs to `docs/` | `DOMAIN_MODEL.md`, `PATTERN_MAP.md`, `PHASE_PLAN.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `CONVENTIONS.md` | All docs readable and consistent |
| Root config files | `pyproject.toml`, `docker-compose.yml`, `.env.example`, `Makefile`, `.gitignore` | `make docker-up` starts PostGIS |
| Local PostGIS | `docker-compose.yml` (postgis:16-3.4 + pgadmin) | `psql` connects |
| Migration runner | `database/run_migrations.py` or Alembic | `make migrate` applies all 5 `.sql` files |
| Verify STAC access | Quick notebook or `pytest` | Can query `planetarycomputer.microsoft.com/api/stac/v1` for NAIP tile |

**Depends on:** Nothing  
**Time estimate:** 1 session  
**Exit criteria:** `make test` passes, `make docker-up` starts PostGIS, all 5 migrations apply cleanly

---

## Phase 1: Domain & Service Layer

| Task | Files | Verification |
|---|---|---|
| Refactor `backend/engine/` to book pattern | See `PATTERN_MAP.md` for full file list | Directory structure matches pattern map |
| Write domain models | `domain/models.py`, `domain/events.py`, `domain/commands.py` | All entity/aggregate invariants tested |
| Write `AbstractTaskGridRepository` | `adapters/repository.py` (Protocol) | `mypy --strict` passes |
| Write `PostgresTaskGridRepository` | `adapters/repository.py` | Integration test with real PostGIS |
| Write `FakeTaskGridRepository` | `adapters/repository.py` | Unit tests use in-memory repo |
| Write `PostgresUnitOfWork` | `service_layer/unit_of_work.py` | UoW commits atomically, collects events, rolls back on error |
| Write `MessageBus` | `service_layer/messagebus.py` | Commands route to correct handlers, events dispatched after commit |
| Write `bootstrap.py` | `bootstrap.py` | `bus = bootstrap()` returns fully wired bus |
| Write handlers | `service_layer/handlers.py` | All commands + events have handlers |
| Unit tests | `tests/unit/` | 90%+ coverage on domain + handlers |
| Integration tests | `tests/integration/` | Full round-trip: handler → UoW → PostGIS → event dispatch |

**Depends on:** Phase 0 (PostGIS running)  
**Time estimate:** 2–3 sessions  
**Exit criteria:** `pytest` passes with both fake and PostGIS fixtures. No class-based services — all handler functions.

---

## Phase 2: Edge Algorithm (Jupyter Notebook)

| Task | Files | Verification |
|---|---|---|
| Notebook: STAC exploration | `notebooks/01_stac_exploration.ipynb` | Can fetch NAIP tile by bounding box |
| Notebook: Spectral edge detection | `notebooks/02_edge_detection.ipynb` | K-means + active contour produces usable boundaries |
| Notebook: Confidence calibration | `notebooks/03_confidence_calibration.ipynb` | 40/30/30 weights produce reasonable triage on 5 test polygons |
| Freeze parameters | `backend/engine/config.py` + `edge_config.yaml` | Notebook uses same YAML as production |
| Validate against hand-labeled data | Manual inspection of 10 polygons | Precision/recall acceptable (< 30% false positives in low-confidence bucket) |

**Depends on:** Phase 1 (handler shell exists to call edge functions)  
**Time estimate:** 1–2 sessions  
**Exit criteria:** Notebook reproducible, parameters frozen to YAML, algorithm container-ready.

---

## Phase 3: Container & API

| Task | Files | Verification |
|---|---|---|
| Refactor edge container | `backend/engine/entrypoints/main.py` (calls `bus.handle()`) | `docker build` green |
| FastAPI REST layer | `backend/engine/entrypoints/api.py` | Endpoints: `POST /validate`, `POST /correct`, `GET /polygons`, `GET /triage` |
| CORS, middleware, health check | `api.py` | `curl /health` returns 200 |
| Docker Compose wiring | `docker-compose.yml` (PostGIS + API + TiTiler) | `docker compose up` starts all services |
| E2E smoke test | `curl` script | Upload polygon → validate → read results → submit correction → confirm |

**Depends on:** Phase 1 + Phase 2  
**Time estimate:** 2 sessions  
**Exit criteria:** `docker compose up` + `curl` round-trip works end-to-end.

---

## Phase 4: dbt & Analytics

| Task | Files | Verification |
|---|---|---|
| dbt project init | `dbt/profiles.yml`, `dbt/dbt_project.yml` | `dbt debug` connects to PostGIS |
| Staging models | `dbt/models/staging/stg_*.sql` | Raw → cleaned, column renaming, type casting |
| Intermediate models | `dbt/models/intermediate/int_*.sql` | Metrics rollup per polygon, per grid, per initiative |
| Mart models | `dbt/models/marts/` | `fct_triage_queue`, `dim_initiatives`, `fct_credit_ledger` |
| Tests | `dbt/tests/` | `dbt test` — not-null, unique, referential, custom |
| Seed data | `dbt/seeds/` | Admin user, demo ML polygon set, sample NAIP record |

**Depends on:** Phase 1 (schema exists)  
**Time estimate:** 1 session  
**Exit criteria:** `dbt build` passes, mart views return correct data for a seeded validation run.

---

## Phase 5: Frontend (Next.js + MapLibre GL)

| Task | Files | Verification |
|---|---|---|
| Next.js scaffold | `frontend/package.json`, `frontend/tsconfig.json` | `npm run dev` starts |
| MapLibre GL map component | `frontend/src/components/Map/MapView.tsx` | Map renders with NAIP tile layer |
| Polygon digitization | `frontend/src/components/Map/DrawControl.tsx` | User can draw/edit polygon on map |
| Polygon upload flow | `frontend/src/app/api/validate/route.ts` + UI | Draw → submit → see spinner → see results |
| Triage queue | `frontend/src/app/dashboard/page.tsx` | List of low-confidence polygons with scores + map preview |
| Correction submission | `frontend/src/components/Map/CorrectionTool.tsx` | Click low-confidence polygon → adjust boundary → submit |
| Initiative dashboard | `frontend/src/app/initiatives/page.tsx` | View initiative progress, grid block heatmap |

**Depends on:** Phase 3 (API exists)  
**Time estimate:** 3–4 sessions  
**Exit criteria:** User can open browser, draw a polygon, submit it, see validation results, submit a correction.

---

## Phase 6: Multi-User & Initiatives

| Task | Files | Verification |
|---|---|---|
| TaskGrid row-locking | `service_layer/handlers.py` (already defined) | Two users cannot lock same grid |
| Peer QA loop | `service_layer/handlers.py` + dbt consensus merge | Two annotations → tiebreaker → merged geometry |
| Initiative lifecycle | Full CRUD in API + frontend | Create → invite → grid generation → track progress |
| Notification system | `adapters/email_sender.py` (stub) | Stub ready for SendGrid/Gmail integration |

**Depends on:** Phase 5  
**Time estimate:** 2 sessions  
**Exit criteria:** Two users working on the same initiative cannot conflict. QA consensus merges correctly.

---

## Phase 7: User-Uploaded Imagery (GDAL COG Pipeline)

| Task | Files | Verification |
|---|---|---|
| Signed URL endpoint | API: `POST /upload/generate-url` | Returns GCS signed URL |
| GDAL Pub/Sub processor | `backend/gdal_cog_processor/` (already scaffolded) | Upload raw TIFF → COG appears in production bucket within 30s |
| TiTiler COG serving | `backend/titiler/app.py` (already scaffolded) | COG tile renders in MapLibre |
| User imagery UI | `frontend/src/components/Upload/` | User uploads file → sees progress → map updates |

**Depends on:** Phase 3 (API exists) + GCP access (for GCS)  
**Time estimate:** 2 sessions  
**Exit criteria:** Upload a GeoTIFF → see it as a map tile.

---

## Phase 8: Production Deployment (GCP)

| Task | Files | Verification |
|---|---|---|
| Terraform: Cloud SQL | `infrastructure/terraform/database.tf` | `terraform apply` creates PostGIS instance |
| Terraform: Cloud Run | `infrastructure/terraform/cloud_run.tf` | API + TiTiler + GDAL deployed |
| Terraform: GCS | `infrastructure/terraform/storage.tf` | Landing + production buckets |
| Terraform: Pub/Sub | `infrastructure/terraform/pubsub.tf` | GDAL trigger topic |
| Terraform: CDN | `infrastructure/terraform/cdn.tf` | TiTiler behind Cloud CDN |
| Terraform: IAM | `infrastructure/terraform/iam.tf` | Least-privilege service accounts |
| CI/CD pipeline | `.github/workflows/deploy.yml` or Cloud Build | `git push production` deploys |
| Deploy over US county | One county, open ML building footprints | E2E URL, cost < $35/month |

**Depends on:** Phase 3 + Phase 5 + Phase 7  
**Time estimate:** 2–3 sessions  
**Exit criteria:** Production URL works end-to-end. Monitoring shows cost below $35/month.

---

## Dependency Graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 5 ──► Phase 6
               │                       │            │
               ▼                       ▼            ▼
            Phase 4                 Phase 7     Phase 8
```

Phases 4 and 7 are on the critical path to Phase 8 but can be built in parallel with 5 and 6 respectively.

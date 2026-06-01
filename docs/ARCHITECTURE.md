# RealitySync Architecture

## System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                     ANNOTATOR (Browser)                          │
│  Draws polygons, reviews triage queue, submits corrections      │
└────────────────┬────────────────────────────────────────────────┘
                 │ HTTPS
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     REVIEWER (Browser)                           │
│  QA peer review, dispute resolution, export                     │
└────────────────┬────────────────────────────────────────────────┘
                 │ HTTPS
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   REALITYSYNC SYSTEM                              │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │
│  │  Next.js │  │  FastAPI │  │  TiTiler │  │  GDAL COG      │   │
│  │  (CDN)   │  │  (CR)    │  │  (CR)    │  │  Processor(CR) │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬────────┘   │
│       │              │             │                │            │
│       └──────┬───────┘             │                │            │
│              ▼                     ▼                ▼            │
│       ┌──────────────────────────────────────────────────┐       │
│       │          Cloud SQL (PostGIS / Postgres)          │       │
│       └──────────────────────────────────────────────────┘       │
│                                                                   │
│       ┌──────────────────────┐   ┌────────────────────────┐      │
│       │  Google Cloud Storage│   │  Pub/Sub               │      │
│       │  (COGs + uploads)    │   │  (GDAL trigger)        │      │
│       └──────────────────────┘   └────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              EXTERNAL SERVICES                                     │
│  Microsoft Planetary Computer STAC API                            │
│  AWS Open Data Registry                                           │
│  SendGrid (email notifications - future)                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Container Diagram

### Compute (GCP Cloud Run)

| Service | Runtime | Purpose | Scaling |
|---|---|---|---|
| `realitysync-api` | Python 3.11 + FastAPI | REST API + command handling | Min 0, Max 10, concurrency 80 |
| `realitysync-titiler` | Python 3.11 + TiTiler | Dynamic COG tile serving | Min 0, Max 20, concurrency 100 |
| `realitysync-edge` | Python 3.11 | Batch validation (Cloud Run Job) | Ephemeral, 1 per validation run |
| `realitysync-gdal` | osgeo/gdal | COG conversion (Pub/Sub triggered) | Min 0, Max 5 |
| `realitysync-frontend` | Node.js 20 + Next.js | SSR web app | Min 0, Max 5 (behind CDN) |

### Storage

| Service | Purpose | Estimated Cost (MVP) |
|---|---|---|
| Cloud SQL (PostGIS) | Domain data + spatial queries | ~$15/month (db-f1-micro) |
| GCS (COG bucket) | Cloud-optimized GeoTIFFs | ~$5/month (200MB) |
| GCS (uploads landing) | Raw user uploads (ephemeral) | ~$2/month |

### Networking

| Component | Purpose |
|---|---|
| Cloud CDN | Cache TiTiler tiles + frontend static assets |
| Cloud NAT | Outbound for Cloud Run (no public IP) |
| VPC | Private network internal to Cloud SQL |

---

## Data Flow Diagrams

### 1. Polygon Validation Flow

```
User draws polygon on MapLibre
        │
        ▼
Next.js → POST /api/validate  →  FastAPI  →  bus.handle(ValidatePolygon)
                                                 │
                                                 ▼
                                          STAC API query
                                          (find best NAIP tile)
                                                 │
                                                 ▼
                                          rio-tiler HTTP range request
                                          (stream 2m buffer strip)
                                                 │
                                                 ▼
                                          Edge detection pipeline:
                                          contrast → K-means → snake
                                                 │
                                                 ▼
                                          Confidence scorer
                                          (40/30/30 formula)
                                                 │
                                                 ▼
                                          UoW.commit()
                                          ├── Write edge_metrics to PostGIS
                                          ├── Write validation_runs record
                                          └── Dispatch event:
                                              ├── PolygonValidated (if ≥0.70)
                                              └── LowConfidenceDetected (if <0.70)
                                                 │
                                                 ▼
                                          User sees result on map
                                          (green = high conf, yellow = review)
```

### 2. User-Uploaded Imagery Flow

```
User uploads GeoTIFF via Next.js
        │
        ▼
FastAPI → POST /upload/generate-url → Returns GCS signed URL
        │
        ▼
User uploads directly to GCS landing bucket
        │
        ▼
GCS → Pub/Sub notification → GDAL COG processor
        │
        ▼
gdalwarp(EPSG:3857) → gdal_translate(COG, DEFLATE, 512)
        │
        ▼
Uploads COG to production bucket
        │
        ▼
Writes user_imagery record to PostGIS
        │
        ▼
TiTiler serves COG tiles → MapLibre renders
```

### 3. Initiative Flow

```
Admin creates initiative (region + grid size + budget)
        │
        ▼
Divide region into 1km² grid blocks → insert TaskGrid rows
        │
        ▼
Invite participants → assign grid blocks
        │
        ▼
Annotator: lock grid → validate polygons → submit corrections
        │
        ▼
Peer reviewer: review corrections → approve/dispute
        │
        ▼
dbt consensus merge: 2 annotations + tiebreaker → merged geometry
        │
        ▼
Grid complete → initiative complete → export GeoJSON/COCO
```

---

## Technology Choices

| Choice | Rationale | Rejected Alternatives |
|---|---|---|
| **PostGIS over Cloud SQL** | Spatial queries (ST_DWithin, KNN), row-level locking for initiatives. MVP volume < 1M polygons. | BigQuery GIS (no row locking, higher latency for CRUD), MongoDB (no spatial joins) |
| **Cloud Run over GKE** | Serverless, pay-per-use, no cluster management. Cold starts acceptable for batch. | GKE (overhead for MVP), App Engine (less flexible than Cloud Run) |
| **rio-tiler over GDAL CLI** | HTTP range requests avoid downloading full imagery. Stream 2m strips per polygon. | GDAL CLI (full file download, costly at scale), PDAL (point cloud focused) |
| **scikit-image active contour** | Snake model works well for low-contrast boundaries where Canny fails. | OpenCV (heavier), Canny only (fails on agricultural boundaries) |
| **dbt for analytics** | Version-controlled SQL transformations, built-in testing, documentation generation. | Plain SQL (no lineage, no testing), Python ETL (overkill for SQL transforms) |
| **MapLibre GL over Leaflet** | WebGL rendering, 3D terrain support, better performance with large polygon datasets. | Leaflet (no WebGL, slower with 500+ polygons), Google Maps (licensing cost) |
| **raw SQL + Python (no ORM)** | Follows Architecture Patterns with Python. Simpler domain code, explicit SQL control. | SQLAlchemy ORM (implicit loading, unit of work conflicts with domain UoW) |
| **Cloud Pub/Sub for GDAL trigger** | Reliable async delivery, exactly-once processing for uploads. | HTTP trigger (no ordering guarantees), polling (wasteful) |

---

## Scalability & Bottlenecks

| Component | MVP Capacity | Bottleneck | Upgrade Path |
|---|---|---|---|
| Cloud SQL (db-f1-micro) | ~500K polygons, ~10 concurrent users | CPU (0.25 vCPU) | db-g1-small → db-custom-2-7680 |
| Edge detector (single run) | ~5000 polygons/run, ~2 min each | I/O (STAC + rio-tiler requests) | Parallelize with Cloud Run Jobs array |
| TiTiler (concurrent tiles) | ~20 req/s per instance | GDAL COG decode | Increase concurrency + CDN |
| Cloud Run API | ~100 req/s with 80 concurrency | UoW serialized commits | Read replicas for read models |

---

## Security Boundaries

1. **API → Cloud SQL**: Private IP only (VPC connector), never exposed to internet
2. **Service accounts**: Least-privilege per service (API can write PostGIS only, TiTiler can read COG bucket only)
3. **CORS**: Restricted to production frontend domain
4. **Uploads**: Signed URLs with 15-minute expiry, size limits (100MB), file type validation (GeoTIFF only)
5. **Row-level security**: TaskGrid locking prevents cross-user conflicts at the database level

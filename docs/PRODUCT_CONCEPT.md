# RealitySync — Product Concept

## User Research Synthesis

### Who We Interviewed

We spoke with 12 geospatial engineers and ML practitioners across 8 companies (3 startups, 2 mid-size, 3 enterprise) who build AI models on satellite and aerial imagery. We also spoke with 5 annotation service buyers and 3 hackathon organizers.

### The Problem (7 quotes)

> *"We spent 3 months hand-correcting 50,000 building footprints from our model. Three months. Most were off by 2–3 meters but that's the difference between a good dataset and a useless one."*
> — ML Engineer, mapping startup

> *"We use NAIP for validation because it's free and 60cm. Our model outputs are 30cm. The mismatch is real. We need to know which predictions are trustworthy and which need a human."*
> — Computer Vision Lead, agtech company

> *"We built our own validation pipeline. It was a 6-month detour. GDAL, STAC, edge detection, a whole web app just to QA polygons. I wish something off-the-shelf existed."*
> — CTO, geospatial data company

> *"Our annotators use QGIS. They download GeoJSON, open it, zoom to each polygon, toggle satellite, decide if it's correct. For 5,000 polygons. Per week."*
> — Operations Manager, AI training data provider

> *"We have building footprints from 3 different models. Some are great, some are trash. We have no systematic way to tell which is which without manual review."*
> — Data Scientist, government contractor

> *"We pay a freelancer on Upwork to fix building footprints. We send them a GeoJSON, they send one back, and we have no idea if they actually checked every polygon against the imagery."*
> — CEO, mapping data buyer

> *"Hackathons are great for volume but the quality is inconsistent. We need a way to run them with structured QA — peer review, tiebreakers, not just 'whoever submits the most polygons wins'."*
> — Community Manager, open mapping NGO

### Common Pain Points

| Pain Point | Frequency | Severity |
|---|---|---|
| No automated way to validate ML polygon boundaries against imagery | 12/12 | Critical |
| Manual QA in QGIS/ArcGIS is slow and error-prone | 11/12 | High |
| Hard to know which predictions to trust without reviewing everything | 10/12 | High |
| No easy way to distribute QA work across a team | 8/12 | Medium |
| Exporting corrected datasets in ML-ready formats is manual | 9/12 | Medium |
| STAC/GDAL/COG tooling requires deep geospatial expertise | 10/12 | High |
| No way to verify that a contractor or freelancer actually checked every polygon | 5/5 buyers | High |
| No structured QA pipeline for hackathon outputs | 3/3 organizers | Medium |

### User Personas

**Persona 1: Data Curator (primary)**
- Geospatial engineer at a mapping or agtech company
- Responsible for training data quality
- Uses Python, PostGIS, QGIS daily
- Pain: spends 60% of time on QA, not model improvement
- Wants: "Upload my predictions, get a triage list of what needs fixing, export clean data"

**Persona 2: Annotation Manager (secondary)**
- Manages a team of 5–20 annotators
- Coordinates large-area boundary correction projects
- Uses spreadsheets + QGIS to track progress
- Pain: zero visibility into annotator quality or progress
- Wants: "Assign grid blocks, track completion, enforce QA standards, and lock out conflicts"

**Persona 3: ML Engineer (tertiary)**
- Trains segmentation/detection models on geospatial data
- Consumes training datasets, doesn't create them
- Pain: receives low-quality training data, doesn't know until model fails
- Wants: "Confidence scores on every polygon in my training set, and provenance on corrections"

**Persona 4: Annotation Service Buyer (new)**
- Hires contractors or teams to correct geospatial data
- Buys ready-to-use training datasets from providers
- Pain: no visibility into correction quality, no confidence scores, no structured QA
- Wants: "Buy verified polygon pairs with confidence scores and QA audit trail"

**Persona 5: Hackathon Organizer (new)**
- Runs community mapping events for NGOs, governments, or companies
- Needs fast bulk coverage across large areas
- Pain: quality inconsistency, no peer review, no structured output
- Wants: "Run a competition with grid block assignments, peer QA, automated scoring, and clean export"

---

## Value Proposition

### The One-Liner

**RealitySync validates ML-generated polygon boundaries against the satellite imagery of your choice so you know which predictions to trust and which need a human — in minutes, not months.**

### What It Does (All 8 Use Cases)

1. **Upload your ML dataset** — GeoJSON, CSV, or Shapefile with your model's polygon predictions. Validate geometry, count vertices, detect self-intersections, show a preview on the map before importing.

2. **Choose your imagery source** — NAIP (free, 60cm), your own uploaded COGs (drone/aerial/phone), any public STAC endpoint (Sentinel, Landsat, Maxar), or a private STAC server. The validation engine compares every polygon boundary against whichever imagery you pick.

3. **Auto-validate every polygon** — Spectral-guided edge detection (multi-spectral contrast enhancement → K-means clustering → active contour snake) compares each boundary against the imagery. Every vertex gets a confidence score (0.0–1.0). The algorithm is imagery-agnostic — same pipeline works on NAIP, Sentinel, drone orthophotos, or private aerial surveys.

4. **Triage the low-confidence ones** — Only polygons scoring <0.70 need human review. High-confidence polygons (>0.70) are auto-approved. Typically 60–80% of a dataset clears automatically. The triage queue shows a map, per-vertex metrics, and the reason each polygon was flagged.

5. **Fix on a map** — Click a flagged polygon. The map shows the original ML boundary, the detected edge (from the snake), and the per-vertex confidence in color (green = confident, yellow = borderline, red = uncertain). Draw corrections, confirm good ones, escalate uncertain ones to a reviewer.

6. **Distribute work across a team** — Divide a large region into 1km² grid blocks. Assign blocks to annotators. Row-level locking prevents two people from editing the same block. Track progress per-block, per-annotator. Peer QA: every correction gets reviewed. If two reviewers disagree, a third tiebreaker decides. The dbt consensus merge produces the final geometry.

7. **Upload your own imagery** — GeoTIFF from a drone, aerial survey, or phone camera. Signed URL → GCS → GDAL converts to COG → TiTiler serves tiles. Your uploaded imagery becomes available as a validation source alongside NAIP and STAC. No minimum resolution, no format lock-in.

8. **Export clean data** — GeoJSON, COCO, GeoPackage, or Parquet. Every polygon includes: original geometry, corrected geometry, per-vertex confidence scores, QA status, correction history (who changed what and when), and the imagery source it was validated against. Ready to feed into your training pipeline.

### Why It's Different

| Instead of... | RealitySync does... |
|---|---|
| Reviewing every polygon manually in QGIS | Only the low-confidence ones need attention (60–80% auto-approved) |
| Building your own GDAL/STAC/edge pipeline | It works out of the box — any imagery source, no downloads |
| Managing QA via spreadsheets and Slack | Structured triage queue with per-vertex confidence scores |
| Hiring a team for 3 months of cleanup | Loop in annotators per-grid-block with QA peer review |
| Sending GeoJSONs back and forth with freelancers | Locked grid blocks, peer review, audit trail on every correction |
| Having no idea if a contractor checked every polygon | Every polygon has a confidence score and a QA status — no blind spots |
| Running hackathons with inconsistent quality | Structured grid blocks, peer review loop, automated consensus merge |
| Re-training on noisy data | Clean, verified training data with provenance |

---

## Use Case Deep Dives

### Use Case: Team-Scale Annotation (Initiatives)

**Problem:** A large-area annotation project (e.g., all building footprints for a US county) cannot be done by one person. Splitting it across a team without conflicts, tracking progress, and enforcing quality standards is a coordination nightmare.

**How RealitySync solves it:**

1. **Admin creates an initiative** — Draws a region on the map, sets grid block size (default 1km²), allocates a credit budget, and invites participants
2. **Grid generation** — The region is divided into contiguous grid blocks. Each block is a `TaskGrid` — the unit of work and the atomic locking boundary
3. **Assignment** — Blocks are assigned to annotators manually or auto-distributed. A block can be `pending`, `in_progress` (locked by one user), `awaiting_review`, `complete`, or `disputed`
4. **Row-locking** — When an annotator opens a block, it's locked at the database level. No two users can edit the same block simultaneously. If the lock expires or is released, the block goes back to `pending`
5. **Peer QA** — Once an annotator finishes a block, it enters `awaiting_review`. A second reviewer (or the annotation manager) checks each correction, marks it as approved or disputed
6. **Consensus merge** — If two reviewers disagree on the same polygon, a third tiebreaker (senior reviewer) resolves it. The dbt consensus merge model picks the final geometry based on majority or senior reviewer override
7. **Completion** — When all blocks are complete, the initiative is done. The admin exports the full corrected dataset with full provenance

**Roles:** Admin (create/manage initiative), Annotator (lock blocks, submit corrections), Reviewer (peer QA, approve/dispute), Senior Reviewer (tiebreaker, escalation)

---

### Use Case: User-Chosen Imagery

**Problem:** NAIP covers the continental US at 60cm resolution. But many users need:
- Higher resolution (drone imagery at 5cm)
- Different time periods (post-disaster imagery, seasonal change)
- Non-US coverage (Sentinel globally at 10m)
- Proprietary imagery (private aerial surveys, Maxar)

**How RealitySync solves it:**

1. **Imagery sources are pluggable.** Every validation run specifies an imagery source. The edge engine uses the same algorithm regardless of source — contrast enhancement, K-means, active contour snake, confidence scoring
2. **Built-in sources:** NAIP (via Microsoft Planetary Computer STAC), Sentinel-2 (via AWS Open Data STAC), Landsat (via USGS STAC)
3. **User-uploaded COGs:** Upload GeoTIFF → GDAL converts to COG → TiTiler serves tiles → selectable as a validation source
4. **Custom STAC endpoints:** Point to any STAC API (private or public) and the engine queries it for overlapping imagery, picks the best scene, streams via HTTP range requests
5. **Fallback chain:** If the primary source has no coverage, automatically fall back to the next in the user's priority list

**Result:** The same upload → validate → triage → correct → export pipeline works against any imagery. The user's choice of imagery is the only variable.

---

### Use Case: User-Uploaded Imagery (GDAL COG Pipeline)

**Problem:** Users have their own high-resolution imagery (drone orthophotos, aerial surveys, phone camera composites) and want to validate polygons against it. They need a way to get their imagery into the system without a support ticket or SFTP.

**How RealitySync solves it:**

1. **Frontend upload** — Drag-and-drop a GeoTIFF into the upload zone. Size limit: 500MB (configurable). File type validation: valid GeoTIFF with georeferencing
2. **Signed URL** — Backend generates a time-limited GCS signed URL. The browser uploads directly to GCS (no server-side file handling)
3. **GDAL COG conversion** — GCS upload triggers a Pub/Sub notification. The GDAL processor container starts, runs `gdalwarp` (reproject to EPSG:3857) then `gdal_translate` (COG with DEFLATE compression, 512x512 blocks, LANCZOS resampling)
4. **Metadata extraction** — Bounding box, resolution (GSD), CRS, number of bands, cloud cover (if available) are extracted and stored to the `user_imagery` table
5. **TiTiler serving** — The COG is served dynamically by TiTiler. Map tiles render in the frontend within seconds of processing completion
6. **Available as validation source** — The uploaded imagery appears in the imagery selector dropdown for validation runs. User validates polygons against their own imagery

**Typical use:** Drone operator flies a site → orthorectifies to GeoTIFF → uploads to RealitySync → validates ML building footprints against 5cm drone imagery → exports corrected dataset.

---

### Use Case: Export for ML Training Pipelines

**Problem:** After validation and correction, the user needs data in formats their training pipeline can consume. Manually converting GeoJSON → COCO, mapping field names, preserving confidence scores — all friction that slows down the ML iteration cycle.

**How RealitySync solves it:**

| Format | When to Use | What's Included |
|---|---|---|
| **GeoJSON** | General-purpose GIS, QGIS, PostGIS import | Original + corrected geometry, confidence scores per vertex, QA status, properties |
| **COCO JSON** | Object detection / instance segmentation training (Detectron2, MMDetection, YOLO) | Polygon annotations with area, bbox, category_id. `info` block includes imagery source, validation run metadata |
| **GeoPackage** | Large datasets, QGIS, ArcGIS, mobile | Full schema, spatial indices preserved, confidence and QA as attribute columns |
| **Parquet** | ML pipelines (PyTorch, TensorFlow, Petastorm) | Tabular format, fast I/O, columnar compression. Each row is one vertex with its metrics |
| **CSV + WKT** | Simple use cases, spreadsheet review | `wkt`, `confidence_avg`, `qa_status`, `properties` flattened |

**Export filters:**
- By QA status (only validated, only corrected, all)
- By confidence range (>0.90, <0.50, etc.)
- By annotator (corrections from specific user)
- Include or exclude original/uncorrected geometry

**Result:** Export runs as an async job. User gets a download link or a GCS URI. Large exports (>1GB) are split into shards with a manifest file.

---

### Use Case: Two-Sided Marketplace

**Problem:** Two distinct but complementary needs exist in the market:
- **Buyers** need high-quality corrected training data but don't have the team or time to do it themselves
- **Annotators** have the time and skill but need structured work with clear requirements and fair pay

**How RealitySync solves it (supply side):**

**Channel 1: Hackathons (community, bulk coverage)**
- Admin creates an initiative as a "hackathon" — public or invite-only
- Grid blocks are claimed by participants on a first-come basis
- Leaderboard shows blocks completed, accuracy scores (based on peer QA agreement rate)
- Prizes awarded for top performers (credits, cash, API access)
- Consensus merge ensures quality regardless of individual skill level
- Best for: large-area coverage, community building, benchmark datasets

**Channel 2: Manual Teams (vetted contractors, premium quality)**
- Admin creates an initiative as a "managed project" — private, vetted annotators only
- Annotators are pre-qualified (test block required before unlocking full project)
- Block assignments are managed, not claimed — ensures coverage without gaps
- QA expectations are higher (stricter confidence thresholds, mandatory peer review)
- Best for: enterprise-grade data, sensitive imagery, production training datasets

**How RealitySync solves it (demand side — dataset sales):**
- A completed, verified initiative is a marketable product
- Buyers browse available datasets by region, resolution, category (building footprints, field boundaries, etc.)
- Each dataset has quality metrics: average confidence, QA agreement rate, polygon count, area covered
- Pricing: $0.15–$0.40 per verified polygon pair (original ML boundary + corrected boundary)
- Buyers download or receive a GCS transfer. Full provenance included

---

## Business Model & Pricing

### Subscription Tiers

| Tier | Price | Credits/Month | Users | Imagery Sources | Export Formats |
|---|---|---|---|---|---|
| **Starter** | $299/mo | 10,000 credits | 3 | NAIP, Sentinel, 1 custom COG | GeoJSON, CSV+WKT |
| **Professional** | $999/mo | 50,000 credits | 20 | All sources, 10 custom COGs | All formats |
| **Enterprise** | Custom | Unlimited | Unlimited | All sources, private STAC | All formats + SLA |

### How Credits Work

- **1 credit = 1 polygon validated** (edge detection + confidence scoring against chosen imagery)
- Credits are consumed when validation runs, not when uploading or exporting
- Unused credits roll over month-to-month (capped at 2x monthly allowance)
- Additional credits: $10 per 1,000 credits (top-up)

### Dataset Marketplace

- Verified polygon pairs sold per-token
- **$0.15/pair** for standard accuracy (confidence >0.85, single reviewer)
- **$0.40/pair** for premium accuracy (confidence >0.95, dual review + tiebreaker)
- RealitySync takes 20% marketplace fee; 80% goes to the annotation team
- Dataset buyers do not need a subscription — pay per-dataset

### Why This Model Works

- **Subscriptions fund platform development.** Predictable MRR for the team
- **Credits align cost with value.** Heavy users pay more, light users pay less
- **Dataset sales create a flywheel.** Annotators produce data → buyers purchase it → annotators earn → more annotators join → more datasets produced
- **Hackathons are loss leaders.** They generate bulk coverage and build the community. The best participants graduate to paid manual teams

---

## Competitive Audit

### Direct Competitors

| Product | What They Do | Why They're Not RealitySync |
|---|---|---|
| **Labelbox** | Labeling platform, geospatial support partial | General-purpose, not purpose-built for boundary validation. No edge detection. No NAIP streaming. No initiative/grid system. |
| **Superb AI** | Training data platform with QA | No geospatial-specific features. No polygon-vs-imagery validation. No multi-user grid locking. |
| **Scale AI** | Human-in-the-loop labeling | They sell the labeling service, not the validation tool. You pay per label, not per validation. No self-service upload → validate → export flow. |
| **Hivemapper** | Map data + validation | Consumer of training data, not a validation tool. Closed platform. No custom imagery support. |
| **V7 Labs** | Training data platform with auto-annotation | General-purpose. No STAC/COG integration. No spectral edge detection. |

### Adjacent Tools (Often Used Instead)

| Tool | Why Users Reach for It | What's Missing |
|---|---|---|
| **QGIS + QuickMapServices** | Free, NAIP basemap, manual digitization tools | No automation. Every polygon is manual. No confidence scores. No team workflow. No export pipeline. |
| **GeoJSON + Jupyter + rasterio** | Flexible, programmable | Requires GDAL expertise. No UI. No team features. No triage queue. No audit trail. |
| **Google Earth Engine** | Vast imagery catalog + scripting | General-purpose geospatial. Not purpose-built for boundary validation. Steep learning curve. No multi-user annotation. |
| **ArcGIS Pro** | Enterprise-grade geospatial | $1,500+/seat/year. Desktop-only. No cloud validation pipeline. No confidence-based triage. |
| **Upwork / Freelancer** | Access to cheap annotators | No platform at all. No QA. No progress tracking. No confidence scores. Trust-based. |
| **Tasking Manager (HOT)** | Grid-based mapping for humanitarian OSM | No edge detection. No confidence scoring. No dbt consensus merge. No export to ML formats. |

### Competitive Moats

| Moat | Details |
|---|---|
| **Imagery-agnostic validation** | Any STAC source, any user-uploaded COG, any resolution. Users aren't locked to NAIP or our tile server. No competitor offers this. |
| **Confidence-based triage** | 60–80% auto-approval means annotators only touch the uncertain ones. Competitors validate nothing automatically — every polygon is either fully manual or trusted blindly. |
| **Spectral-guided edge detection** | Bespoke hybrid algorithm (K-means + active contour snake) tuned for low-contrast boundaries where Canny and Sobel fail. Hard to replicate, no off-the-shelf equivalent exists. |
| **Multi-user initiatives with row-locking** | Grid blocks, row-level database locks, peer QA loop, dbt consensus merge. Most competitors don't support teams at all. Those that do (Labelbox) lack the grid block abstraction. |
| **STAC-native streaming** | No imagery storage cost. HTTP range requests from STAC APIs. Our storage bill is near-zero because we never host public imagery. Only user uploads incur storage cost. |
| **Export ML formats natively** | COCO, Parquet, GeoPackage — not just GeoJSON. Built for the training pipeline, not just GIS viewers. |
| **Two-sided marketplace + hackathons** | Competitors are either pure tools (Labelbox) or pure services (Scale). RealitySync is both — self-serve validation + structured team annotation + dataset marketplace. |

---

## Market Size

### TAM, SAM, SOM

| Metric | Value | Source |
|---|---|---|
| Global geospatial analytics market (2030) | **$80B** | Grand View Research, 2023 |
| Training data for geospatial AI (2025) | **$3.2B** | Cognilytica, 2024 |
| Addressable segment (boundary validation tools + services) | **~$200M** | Estimated — annotation tools + managed QA + training data verification |
| Serviceable obtainable (year 1, conservative) | **$500K–$1M** | 10–20 customers at $299–999/mo + dataset sales |

### Pricing Validation

- 8/12 interviewees said $299–999/mo is "reasonable" for a tool that saves 60% of QA time
- 3/5 annotation buyers said $0.15–0.40 per verified polygon is "less than we're paying freelancers" (current range: $0.50–$2.00/polygon depending on complexity)
- 2/3 hackathon organizers said they'd run their next event on RealitySync if the grid block + peer review system existed

---

## Product Principles

These guide every decision:

1. **Automate the obvious, surface the uncertain.** If confidence >0.70, trust the ML. Only bother a human for the edge cases. Saves 60–80% of manual review time.

2. **You choose the imagery.** NAIP is free, your drone COG is yours, any STAC endpoint works. We don't gatekeep the source. The algorithm adapts to any resolution or spectral band.

3. **One polygon at a time is too slow.** Grid blocks, bulk upload, batch validation. Scale from polygon → set → initiative → region.

4. **Export is not an afterthought.** The whole point is cleaner training data. GeoJSON, COCO, GeoPackage, Parquet from day one. Every polygon has full provenance.

5. **Team workflows are not optional.** Locking, peer review, consensus, role management — single-player mode is a feature, but team mode is the product.

6. **Trust is built on provenance.** Every correction is logged with who, what, when, and why. Every polygon has an audit trail. Buyers can verify, annotators can prove their work.

7. **Make the marketplace a flywheel.** Subscriptions fund the platform. Credits fund validation. Dataset sales reward annotators. Annotators produce better data. Better data attracts more buyers. More buyers fund more subscriptions.

8. **Hackathons build community, teams build revenue.** Use hackathons for bulk coverage and community growth. Convert top performers to paid annotators. Serve enterprise buyers with vetted teams at a premium.

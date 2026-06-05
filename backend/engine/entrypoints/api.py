from __future__ import annotations

import math
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

import psycopg2
import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.engine.adapters.repository import PostgresUserRepository
from backend.engine.bootstrap import bootstrap
from backend.engine.domain.commands import (
    ApproveGridBlock,
    AssignParticipant,
    BulkAssignGridBlocks,
    ClaimGridBlock,
    CorrectBoundary,
    CreateInitiative,
    DisputeGridBlock,
    GenerateGridBlocks,
    JoinHackathon,
    ListDatasetForSale,
    LockGridBlock,
    PurchaseDataset,
    RequestExport,
    ScoreHackathonSubmission,
    SubmitGridBlock,
    SubmitHackathonResult,
    TopUpCredits,
    UploadPolygonSet,
    ValidatePolygon,
)
from backend.engine.entrypoints.tiles import router as tiles_router
from backend.engine.entrypoints.upload import router as upload_router
from backend.engine.service_layer.export_worker import ExportWorker
from backend.engine.service_layer.messagebus import MessageBus
from backend.engine.service_layer.unit_of_work import PostgresUnitOfWork

_worker: ExportWorker | None = None


def _db_conn_factory() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "realitysync"),
        user=os.environ.get("DB_USER", "realitysync"),
        password=os.environ.get("DB_PASSWORD", "realitysync"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _worker
    _worker = ExportWorker(connection_factory=_db_conn_factory)
    _worker.start()
    yield
    _worker.stop()


def get_bus() -> MessageBus:
    uow = PostgresUnitOfWork(connection_factory=_db_conn_factory)
    return bootstrap(uow=uow)  # type: ignore[arg-type]


sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("APP_ENV", "development"),
    traces_sample_rate=0.1,
)

app = FastAPI(
    title="RealitySync API",
    version="0.1.0",
    description="Geospatial boundary validation and data curation API",
    lifespan=lifespan,
)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(
    ","
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_user(api_key: str) -> UUID | None:
    """Look up the user by API key. Returns user_id or None."""
    try:
        conn = _db_conn_factory()
        try:
            repo = PostgresUserRepository(conn)
            user = repo.get_by_api_key(api_key)
            return user.id if user else None
        finally:
            conn.close()
    except Exception:
        return None


@app.middleware("http")
async def auth_middleware(request: Request, call_next: Any) -> Any:
    if any(
        request.url.path.startswith(p)
        for p in ("/health", "/docs", "/openapi", "/tiles", "/api/auth")
    ):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")

    api_key: str | None = None
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]

    if not api_key:
        api_key = request.headers.get("X-API-Key", "")

    if not api_key:
        return JSONResponse(status_code=401, content={"detail": "Missing API key"})

    user_id = _resolve_user(api_key)
    if user_id is None:
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

    request.state.user_id = user_id
    return await call_next(request)


app.include_router(upload_router)
app.include_router(tiles_router)


class UploadPolygonSetRequest(BaseModel):
    user_id: UUID
    name: str
    geometries: list[str]
    model_version: str | None = None


class ValidatePolygonRequest(BaseModel):
    grid_id: UUID
    polygon_id: UUID
    imagery_source: str = "naip"
    user_id: UUID | None = None


class CorrectBoundaryRequest(BaseModel):
    grid_id: UUID
    polygon_id: UUID
    user_id: UUID
    new_geometry: str


class CreateInitiativeRequest(BaseModel):
    owner_id: UUID
    name: str
    region: str
    grid_size_m: int = 1000
    budget_credits: Decimal | None = None


class LockGridBlockRequest(BaseModel):
    grid_id: UUID
    user_id: UUID


class ClaimGridBlockRequest(BaseModel):
    initiative_id: UUID
    user_id: UUID


class SubmitGridBlockRequest(BaseModel):
    grid_id: UUID


class ApproveGridBlockRequest(BaseModel):
    grid_id: UUID
    reviewer_id: UUID


class DisputeGridBlockRequest(BaseModel):
    grid_id: UUID
    reviewer_id: UUID
    notes: str = ""


class BulkAssignGridBlocksRequest(BaseModel):
    grid_ids: list[UUID]
    user_id: UUID


class TopUpCreditsRequest(BaseModel):
    user_id: UUID
    amount: Decimal


class RequestExportRequest(BaseModel):
    user_id: UUID
    export_format: str
    source_type: str
    source_id: UUID
    qa_status: str | None = None
    confidence_min: float | None = None
    confidence_max: float | None = None
    annotator_id: UUID | None = None
    include_original: bool = True


class GenerateGridBlocksRequest(BaseModel):
    initiative_id: UUID


class AssignParticipantRequest(BaseModel):
    initiative_id: UUID
    user_id: UUID
    role: str = "annotator"


class ListDatasetForSaleRequest(BaseModel):
    seller_id: UUID
    dataset_id: UUID
    title: str
    price_tokens: Decimal
    geometry_count: int = 0
    description: str | None = None


class PurchaseDatasetRequest(BaseModel):
    listing_id: UUID
    buyer_id: UUID


class ListPolygonsRequest(BaseModel):
    initiative_id: UUID | None = None
    grid_id: UUID | None = None
    status: str | None = None
    page: int = 1
    per_page: int = 50


class UpdateInitiativeRequest(BaseModel):
    name: str | None = None
    region: str | None = None
    status: str | None = None
    grid_size_m: int | None = None
    budget_credits: Decimal | None = None
    hackathon_mode: bool | None = None
    max_participants: int | None = None


class JoinHackathonRequest(BaseModel):
    initiative_id: UUID
    user_id: UUID


class SubmitHackathonResultRequest(BaseModel):
    initiative_id: UUID
    user_id: UUID
    score: float
    accuracy_pct: float


class ScoreHackathonSubmissionRequest(BaseModel):
    initiative_id: UUID
    submission_id: UUID
    score: float


# ---------------------------------------------------------------------------
# Imagery Sources / STAC
# ---------------------------------------------------------------------------


PRESET_IMAGERY_SOURCES = [
    {
        "id": "naip",
        "label": "NAIP (60cm, US)",
        "tileUrl": "/tiles/naip/{z}/{x}/{y}.png",
        "attribution": "USDA NAIP — Planet Labs",
        "type": "xyz",
        "resolution": "60cm–1m",
        "coverage": "Continental US",
        "thumbnail": "🛰️",
    },
    {
        "id": "sentinel-2-l2a",
        "label": "Sentinel-2 L2A (10m, Global)",
        "tileUrl": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "ESA Copernicus — Esri",
        "type": "stac",
        "resolution": "10m",
        "coverage": "Global",
        "stacUrl": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "stacCollection": "sentinel-2-l2a",
        "thumbnail": "🛰️",
    },
    {
        "id": "landsat-c2-l2",
        "label": "Landsat 8/9 (30m, Global)",
        "tileUrl": "",
        "attribution": "USGS — Microsoft Planetary Computer",
        "type": "stac",
        "resolution": "30m",
        "coverage": "Global",
        "stacUrl": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "stacCollection": "landsat-c2-l2",
        "thumbnail": "🌍",
    },
    {
        "id": "esri-world-imagery",
        "label": "Esri World Imagery (~1m, Global)",
        "tileUrl": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "type": "xyz",
        "resolution": "~1m",
        "coverage": "Global",
        "thumbnail": "🌐",
    },
    {
        "id": "sentinel-1-rtc",
        "label": "Sentinel-1 SAR (10m, Global)",
        "tileUrl": "",
        "attribution": "ESA — Microsoft Planetary Computer",
        "type": "stac",
        "resolution": "10m",
        "coverage": "Global",
        "stacUrl": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "stacCollection": "sentinel-1-rtc",
        "thumbnail": "📡",
    },
    {
        "id": "cbers-4-mux",
        "label": "CBERS-4 (64m, Latin America)",
        "tileUrl": "",
        "attribution": "INPE — Brazil Data Cube",
        "type": "stac",
        "resolution": "64m",
        "coverage": "Latin America",
        "stacUrl": "https://data.inpe.br/bdc/stac/v1/",
        "stacCollection": "CBERS4-MUX",
        "thumbnail": "🛰️",
    },
    {
        "id": "amazonia-1-wfi",
        "label": "Amazonia-1 WFI (64m, Brazil)",
        "tileUrl": "",
        "attribution": "INPE — Brazil Data Cube",
        "type": "stac",
        "resolution": "64m",
        "coverage": "Brazil",
        "stacUrl": "https://data.inpe.br/bdc/stac/v1/",
        "stacCollection": "AMAZONIA1-WFI",
        "thumbnail": "🛰️",
    },
    {
        "id": "cop-dem-glo-30",
        "label": "Copernicus DEM (30m, Global)",
        "tileUrl": "",
        "attribution": "ESA — Microsoft Planetary Computer",
        "type": "stac",
        "resolution": "30m",
        "coverage": "Global",
        "stacUrl": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "stacCollection": "cop-dem-glo-30",
        "thumbnail": "⛰️",
    },
    {
        "id": "osm",
        "label": "OpenStreetMap (Reference)",
        "tileUrl": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "OpenStreetMap contributors",
        "type": "xyz",
        "resolution": "N/A",
        "coverage": "Global",
        "thumbnail": "🗺️",
    },
]


class StacQueryRequest(BaseModel):
    stac_url: str = Field(alias="stacUrl")
    collection: str
    bbox: list[float] | None = None
    geometry: dict[str, Any] | None = None
    datetime: str | None = None
    max_items: int = Field(default=10, alias="maxItems")
    auth_token: str | None = Field(default=None, alias="authToken")


class ValidateGeometriesRequest(BaseModel):
    geometries: list[dict[str, str]]


class BatchValidateRequest(BaseModel):
    geometries: list[str]
    imagery_source: str = Field(alias="imagerySource")
    user_id: UUID = Field(alias="userId")
    dataset_name: str = Field(alias="datasetName")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Any:
    """Health check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    name: str


@app.post("/api/auth/login")
async def login(body: LoginRequest) -> Any:
    """Return the user's API key for the given email."""
    conn = _db_conn_factory()
    try:
        repo = PostgresUserRepository(conn)
        user = repo.get_by_email(body.email)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "user_id": str(user.id),
            "api_key": user.api_key,
            "name": user.name,
            "role": user.role,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# User Imagery
# ---------------------------------------------------------------------------


@app.get("/api/imagery")
async def list_imagery(
    request: Request,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """List the current user's uploaded imagery."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = _db_conn_factory()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, original_filename, gcs_uri, cog_uri, bounding_box,
                       resolution_cm, status, created_at, processed_at
                FROM user_imagery
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        return {
            "items": [
                {
                    "imagery_id": str(r["id"]),
                    "filename": r["original_filename"],
                    "status": r["status"],
                    "cog_uri": r["cog_uri"],
                    "bounding_box": r["bounding_box"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "tile_url": f"/tiles/user/{r['id']}/{{z}}/{{x}}/{{y}}.png"
                    if r["status"] == "ready"
                    else None,
                }
                for r in rows
            ],
            "total": len(rows),
        }
    finally:
        conn.close()


@app.post("/api/auth/register")
async def register(body: RegisterRequest) -> Any:
    """Create a new user and return an API key."""
    import secrets

    from backend.engine.domain.models import User

    api_key = secrets.token_hex(32)
    user_id = uuid4()
    user = User(
        id=user_id,
        email=body.email,
        name=body.name,
        role="annotator",
        api_key=api_key,
    )
    conn = _db_conn_factory()
    try:
        repo = PostgresUserRepository(conn)
        repo.add(user)
        conn.commit()
        return {"user_id": str(user_id), "api_key": api_key, "name": body.name, "role": "annotator"}
    finally:
        conn.close()


@app.post("/api/datasets/upload")
async def upload_dataset(
    body: UploadPolygonSetRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Upload a set of polygons for ML-based validation."""
    try:
        results = bus.handle(
            UploadPolygonSet(
                user_id=body.user_id,
                name=body.name,
                geometries=body.geometries,
                model_version=body.model_version,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/datasets/validate")
async def validate_polygon(
    body: ValidatePolygonRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Run edge validation on a single polygon."""
    try:
        results = bus.handle(
            ValidatePolygon(
                grid_id=body.grid_id,
                polygon_id=body.polygon_id,
                imagery_source=body.imagery_source,
                user_id=body.user_id,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


@app.post("/api/polygons/correct")
async def correct_boundary(
    body: CorrectBoundaryRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Submit a human correction for a polygon boundary."""
    try:
        results = bus.handle(
            CorrectBoundary(
                grid_id=body.grid_id,
                polygon_id=body.polygon_id,
                user_id=body.user_id,
                new_geometry=body.new_geometry,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Initiatives
# ---------------------------------------------------------------------------


@app.post("/api/initiatives")
async def create_initiative(
    body: CreateInitiativeRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Create a new annotation initiative."""
    try:
        results = bus.handle(
            CreateInitiative(
                owner_id=body.owner_id,
                name=body.name,
                region=body.region,
                grid_size_m=body.grid_size_m,
                budget_credits=body.budget_credits,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/initiatives")
async def list_initiatives(
    bus: Annotated[MessageBus, Depends(get_bus)],
    owner_id: UUID | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> Any:
    """List all initiatives with optional owner/status filters."""
    with bus.uow as uow:
        items = uow.initiative_repo.list(owner_id=owner_id, status=status)
    offset = (page - 1) * per_page
    page_items = items[offset : offset + per_page]
    return {
        "items": [
            {
                "id": str(i.id),
                "owner_id": str(i.owner_id),
                "name": i.name,
                "region": i.region,
                "status": i.status.value,
                "grid_size_m": i.grid_size_m,
                "budget_credits": float(i.budget_credits) if i.budget_credits else None,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in page_items
        ],
        "total": len(items),
        "page": page,
        "per_page": per_page,
    }


@app.get("/api/initiatives/{initiative_id}")
async def get_initiative(
    initiative_id: UUID,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Get details for a single initiative."""
    with bus.uow as uow:
        initiative = uow.initiative_repo.get(initiative_id)
    if initiative is None:
        raise HTTPException(status_code=404, detail="Initiative not found")
    return {
        "id": str(initiative.id),
        "owner_id": str(initiative.owner_id),
        "name": initiative.name,
        "region": initiative.region,
        "status": initiative.status.value,
        "grid_size_m": initiative.grid_size_m,
        "budget_credits": float(initiative.budget_credits) if initiative.budget_credits else None,
        "created_at": initiative.created_at.isoformat() if initiative.created_at else None,
        "completed_at": initiative.completed_at.isoformat() if initiative.completed_at else None,
    }


@app.delete("/api/initiatives/{initiative_id}", status_code=204)
async def archive_initiative(
    initiative_id: UUID,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> None:
    """Archive (soft-delete) an initiative."""
    with bus.uow as uow:
        initiative = uow.initiative_repo.get(initiative_id)
        if initiative is None:
            raise HTTPException(status_code=404, detail="Initiative not found")
        initiative.archive()
        uow.initiative_repo.add(initiative)
        uow.commit()


@app.get("/api/initiatives/{initiative_id}/grids")
async def list_initiative_grids(
    initiative_id: UUID,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """List grid blocks belonging to an initiative."""
    with bus.uow as uow:
        grids = uow.grid_repo.get_by_initiative(initiative_id)
    return {
        "items": [
            {
                "grid_id": str(g.id),
                "geometry": g.geometry,
                "status": g.status.value,
                "assigned_user_id": str(g.assigned_user_id) if g.assigned_user_id else None,
                "polygon_count": len(g.polygons),
            }
            for g in grids
        ],
        "total": len(grids),
    }


@app.put("/api/initiatives/{initiative_id}")
async def update_initiative(
    initiative_id: UUID,
    body: UpdateInitiativeRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Update initiative fields (name, status, hackathon mode, etc.)."""
    with bus.uow as uow:
        initiative = uow.initiative_repo.get(initiative_id)
        if initiative is None:
            raise HTTPException(status_code=404, detail="Initiative not found")
        if body.name is not None:
            initiative.name = body.name
        if body.region is not None:
            initiative.region = body.region
        if body.status is not None:
            from backend.engine.domain.models import InitiativeStatus

            initiative.status = InitiativeStatus(body.status)
        if body.grid_size_m is not None:
            initiative.grid_size_m = body.grid_size_m
        if body.budget_credits is not None:
            initiative.budget_credits = body.budget_credits
        if body.hackathon_mode is not None:
            initiative.hackathon_mode = body.hackathon_mode
        if body.max_participants is not None:
            initiative.max_participants = body.max_participants
        uow.initiative_repo.add(initiative)
        uow.commit()
    return {"id": str(initiative_id), "status": "updated"}


# ---------------------------------------------------------------------------
# Hackathons
# ---------------------------------------------------------------------------


@app.post("/api/hackathons/join")
async def join_hackathon(
    body: JoinHackathonRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Join a hackathon initiative."""
    try:
        bus.handle(JoinHackathon(initiative_id=body.initiative_id, user_id=body.user_id))
        return {"status": "joined"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/hackathons/submit")
async def submit_hackathon_result(
    body: SubmitHackathonResultRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Submit a score result for a hackathon participant."""
    try:
        bus.handle(
            SubmitHackathonResult(
                initiative_id=body.initiative_id,
                user_id=body.user_id,
                score=body.score,
                accuracy_pct=body.accuracy_pct,
            )
        )
        return {"status": "submitted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/hackathons/score")
async def score_hackathon_submission(
    body: ScoreHackathonSubmissionRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Score/update a specific hackathon submission."""
    try:
        bus.handle(
            ScoreHackathonSubmission(
                initiative_id=body.initiative_id,
                submission_id=body.submission_id,
                score=body.score,
            )
        )
        return {"status": "scored"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/hackathons/{initiative_id}/leaderboard")
async def get_leaderboard(
    initiative_id: UUID,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Get the leaderboard for a hackathon initiative."""
    with bus.uow as uow:
        entries = uow.leaderboard_repo.list_by_initiative(initiative_id)
    return {
        "items": [
            {
                "id": str(e.id),
                "user_id": str(e.user_id),
                "score": e.score,
                "polygons_submitted": e.polygons_submitted,
                "accuracy_pct": e.accuracy_pct,
                "place": e.place,
                "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
            }
            for e in entries
        ],
        "total": len(entries),
    }


# ---------------------------------------------------------------------------
# Polygons
# ---------------------------------------------------------------------------


@app.post("/api/polygons/list")
async def list_polygons(
    body: ListPolygonsRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """List polygons with optional filtering and pagination."""
    with bus.uow as uow:
        conn = uow.conn if hasattr(uow, "conn") else None
        if conn is None:
            return {"items": [], "total": 0, "page": body.page, "per_page": body.per_page}

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            conditions = ["1=1"]
            params: list[Any] = []
            if body.initiative_id:
                conditions.append("g.initiative_id = %s")
                params.append(body.initiative_id)
            if body.grid_id:
                conditions.append("p.task_grid_id = %s")
                params.append(body.grid_id)
            if body.status:
                conditions.append("p.qa_status = %s")
                params.append(body.status)

            where = " AND ".join(conditions)
            cur.execute(
                f"SELECT COUNT(*) FROM ml_polygons p JOIN map_task_grid g ON p.task_grid_id = g.grid_id WHERE {where}",  # noqa: E501
                params,
            )
            total = cur.fetchone()["count"]

            offset = (body.page - 1) * body.per_page
            cur.execute(
                f"""
                SELECT p.*, g.initiative_id
                FROM ml_polygons p
                JOIN map_task_grid g ON p.task_grid_id = g.grid_id
                WHERE {where}
                ORDER BY p.created_at DESC NULLS LAST
                LIMIT %s OFFSET %s
                """,
                params + [body.per_page, offset],
            )
            items = cur.fetchall()

    return {
        "items": [dict(r) for r in items],
        "total": total,
        "page": body.page,
        "per_page": body.per_page,
    }


@app.get("/api/polygons/{polygon_id}")
async def get_polygon(
    polygon_id: UUID,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Get polygon detail with edge metrics and correction history."""
    with bus.uow as uow:
        conn = uow.conn if hasattr(uow, "conn") else None
        if conn is None:
            return {"error": "no database connection"}

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    p.id AS polygon_id,
                    p.polygon_set_id,
                    p.task_grid_id,
                    p.original_geometry,
                    p.corrected_geometry,
                    p.qa_status,
                    p.confidence_avg,
                    p.created_at
                FROM ml_polygons p
                WHERE p.id = %s
                """,
                (polygon_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"error": "polygon not found"}

            polygon = dict(row)

            cur.execute(
                """
                SELECT
                    vertex_index,
                    deviation_meters,
                    spectral_contrast,
                    snake_strain,
                    confidence_score,
                    is_ambiguous
                FROM edge_metrics
                WHERE polygon_id = %s
                ORDER BY vertex_index ASC
                """,
                (polygon_id,),
            )
            polygon["edge_metrics"] = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    action,
                    corrected_geometry,
                    notes,
                    created_at
                FROM human_corrections
                WHERE polygon_id = %s
                ORDER BY created_at DESC
                """,
                (polygon_id,),
            )
            polygon["corrections"] = [dict(r) for r in cur.fetchall()]

    return polygon


# ---------------------------------------------------------------------------
# Triage Queue
# ---------------------------------------------------------------------------


@app.get("/api/triage")
async def get_triage(
    bus: Annotated[MessageBus, Depends(get_bus)],
    initiative_id: UUID | None = Query(None),
    priority_tier: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> Any:
    """Get the triage queue of polygons needing review."""
    with bus.uow as uow:
        conn = uow.conn if hasattr(uow, "conn") else None
        if conn is None:
            return {"items": [], "total": 0, "page": page, "per_page": per_page}

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            conditions = ["1=1"]
            params: list[Any] = []
            if initiative_id:
                conditions.append("g.initiative_id = %s")
                params.append(initiative_id)
            if priority_tier:
                conditions.append(
                    "CASE "
                    "  WHEN p.confidence_avg >= 0.90 THEN 'auto_approved' "
                    "  WHEN p.confidence_avg >= 0.70 THEN 'needs_review' "
                    "  WHEN p.confidence_avg >= 0.40 THEN 'needs_correction' "
                    "  ELSE 'escalate' "
                    "END = %s"
                )
                params.append(priority_tier)

            count_q = f"""
                SELECT COUNT(*) FROM ml_polygons p
                JOIN map_task_grid g ON p.task_grid_id = g.grid_id
                WHERE {conditions[0]}
            """ + " AND ".join(f" AND {c}" for c in conditions[1:])
            cur.execute(count_q, params)
            total = cur.fetchone()["count"]

            offset = (page - 1) * per_page
            items_q = (
                f"""
                SELECT
                    p.id AS polygon_id,
                    p.polygon_set_id,
                    p.qa_status,
                    p.confidence_avg AS computed_confidence,
                    COALESCE(AVG(e.deviation_meters), 0) AS avg_deviation_m,
                    COUNT(*) FILTER (WHERE e.confidence_score < 0.70) AS ambiguous_vertices,
                    COALESCE(h.correction_count, 0) AS correction_count,
                    CASE
                        WHEN p.confidence_avg >= 0.90 THEN 'auto_approved'
                        WHEN p.confidence_avg >= 0.70 THEN 'needs_review'
                        WHEN p.confidence_avg >= 0.40 THEN 'needs_correction'
                        ELSE 'escalate'
                    END AS priority_tier
                FROM ml_polygons p
                JOIN map_task_grid g ON p.task_grid_id = g.grid_id
                LEFT JOIN edge_metrics e ON e.polygon_id = p.id
                LEFT JOIN (
                    SELECT polygon_id, COUNT(*) AS correction_count
                    FROM human_corrections GROUP BY polygon_id
                ) h ON h.polygon_id = p.id
                WHERE {conditions[0]}
            """
                + " AND ".join(f" AND {c}" for c in conditions[1:])
                + """
                GROUP BY p.id, p.polygon_set_id, p.qa_status, p.confidence_avg, h.correction_count
                ORDER BY computed_confidence ASC NULLS LAST
                LIMIT %s OFFSET %s
            """
            )
            cur.execute(items_q, params + [per_page, offset])
            items = cur.fetchall()

    return {
        "items": [dict(r) for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------


@app.post("/api/credits/top-up")
async def top_up_credits(
    body: TopUpCreditsRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Add credits to a user's account."""
    try:
        results = bus.handle(
            TopUpCredits(
                user_id=body.user_id,
                amount=body.amount,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/credits/{user_id}")
async def get_credits(
    user_id: UUID,
    request: Request,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Fetch a user's current credit balance. Only the authenticated user can view their own balance."""  # noqa: E501
    authed_user = getattr(request.state, "user_id", None)
    if authed_user is None or authed_user != user_id:
        raise HTTPException(status_code=403, detail="You can only view your own credits")
    with bus.uow as uow:
        user = uow.user_repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": str(user.id),
        "credits_remaining": float(user.credits_remaining),
    }


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


@app.post("/api/exports")
async def request_export(
    body: RequestExportRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Request an export job for a dataset."""
    try:
        results = bus.handle(
            RequestExport(
                user_id=body.user_id,
                export_format=body.export_format,
                source_type=body.source_type,
                source_id=body.source_id,
                qa_status=body.qa_status,
                confidence_min=body.confidence_min,
                confidence_max=body.confidence_max,
                annotator_id=body.annotator_id,
                include_original=body.include_original,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Grid blocks
# ---------------------------------------------------------------------------


@app.post("/api/initiatives/generate-grids")
async def generate_grids(
    body: GenerateGridBlocksRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Generate grid blocks for an initiative."""
    try:
        results = bus.handle(
            GenerateGridBlocks(
                initiative_id=body.initiative_id,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------


@app.post("/api/initiatives/assign")
async def assign_participant(
    body: AssignParticipantRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Assign a participant to an initiative."""
    try:
        results = bus.handle(
            AssignParticipant(
                initiative_id=body.initiative_id,
                user_id=body.user_id,
                role=body.role,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/grids/lock")
async def lock_grid_block(
    body: LockGridBlockRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Lock a grid block for a user to work on."""
    try:
        results = bus.handle(
            LockGridBlock(
                grid_id=body.grid_id,
                user_id=body.user_id,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/grids/claim")
async def claim_grid_block(
    body: ClaimGridBlockRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Claim the next available grid block in an initiative."""
    try:
        results = bus.handle(
            ClaimGridBlock(
                initiative_id=body.initiative_id,
                user_id=body.user_id,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/grids/submit")
async def submit_grid_block(
    body: SubmitGridBlockRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Submit a grid block for review."""
    try:
        results = bus.handle(SubmitGridBlock(grid_id=body.grid_id))
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/grids/approve")
async def approve_grid_block(
    body: ApproveGridBlockRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Approve a grid block (reviewer action)."""
    try:
        results = bus.handle(ApproveGridBlock(grid_id=body.grid_id, reviewer_id=body.reviewer_id))
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/grids/dispute")
async def dispute_grid_block(
    body: DisputeGridBlockRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Dispute a grid block (send back for rework)."""
    try:
        results = bus.handle(
            DisputeGridBlock(grid_id=body.grid_id, reviewer_id=body.reviewer_id, notes=body.notes)
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/grids/bulk-assign")
async def bulk_assign_grids(
    body: BulkAssignGridBlocksRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Bulk assign grid blocks to a user (admin)."""
    try:
        results = bus.handle(BulkAssignGridBlocks(grid_ids=body.grid_ids, user_id=body.user_id))
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------


@app.get("/api/marketplace/listings")
async def list_marketplace(
    bus: Annotated[MessageBus, Depends(get_bus)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> Any:
    """List active marketplace dataset listings."""
    with bus.uow as uow:
        listings = uow.marketplace_repo.list_active()
    offset = (page - 1) * per_page
    page_listings = listings[offset : offset + per_page]
    return {
        "listings": [
            {
                "listing_id": str(listing.listing_id),
                "seller_id": str(listing.seller_id),
                "dataset_id": str(listing.dataset_id),
                "title": listing.title,
                "description": listing.description,
                "price_tokens": float(listing.price_tokens),
                "geometry_count": listing.geometry_count,
                "quality_score": listing.quality_score,
                "completion_rate": listing.completion_rate,
                "status": listing.status,
                "created_at": listing.created_at.isoformat() if listing.created_at else None,
            }
            for listing in page_listings
        ],
        "total": len(listings),
        "page": page,
        "per_page": per_page,
    }


@app.post("/api/marketplace/listings")
async def create_listing(
    body: ListDatasetForSaleRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """List a dataset for sale on the marketplace."""
    try:
        results = bus.handle(
            ListDatasetForSale(
                seller_id=body.seller_id,
                dataset_id=body.dataset_id,
                title=body.title,
                price_tokens=body.price_tokens,
                geometry_count=body.geometry_count,
                description=body.description,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/marketplace/purchase")
async def purchase_dataset(
    body: PurchaseDatasetRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Purchase a dataset listing."""
    try:
        results = bus.handle(
            PurchaseDataset(
                listing_id=body.listing_id,
                buyer_id=body.buyer_id,
            )
        )
        return results[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Imagery Sources
# ---------------------------------------------------------------------------


@app.get("/api/imagery/sources")
async def list_imagery_sources(request: Request) -> Any:
    """Return all configured imagery sources."""
    return {
        "sources": PRESET_IMAGERY_SOURCES,
        "total": len(PRESET_IMAGERY_SOURCES),
    }


# ---------------------------------------------------------------------------
# COG Generation
# ---------------------------------------------------------------------------


class CogGenerateRequest(BaseModel):
    source_id: str = Field(min_length=1)
    geojson: dict[str, Any]
    buffer_meters: int = 0
    force: bool = False
    api_key: str | None = None


@app.post("/api/imagery/cog")
async def generate_cog(body: CogGenerateRequest, request: Request) -> Any:
    """Generate (or retrieve cached) COG for a polygon.

    Supports three source types:

      - **stac** (free) — queries STAC API for the best scene and returns
        the existing COG URL (no reprocessing). 0 credits.
      - **commercial** (paid) — downloads raw imagery via the provider's
        API, warps to EPSG:3857, converts to COG, and uploads to GCS.
        Requires credits (platform key) or the user's own API key.
      - **user_upload** — returns the user's own COG URL.

    Response includes ``cog_url`` which can be used with TiTiler:
    ``/cog/tiles/{z}/{x}/{y}.png?url={cog_url}&geojson={geojson}``
    """
    import time
    from backend.engine.service_layer.cog_service import (
        get_or_generate_cog,
        _get_source_type,
        deduct_credits,
        _insert_catalog_entry,
    )

    start = time.time()
    source_type = _get_source_type(body.source_id)
    user_id = getattr(request.state, "user_id", None)

    try:
        if source_type == "commercial" and not body.api_key:
            # Using platform key — deduct credits first
            from backend.engine.service_layer.cog_service import estimate_cost
            est = estimate_cost(body.source_id, body.geojson, body.buffer_meters)
            cost = est["cost_credits"]
            if cost > 0 and not est.get("provider_available"):
                raise HTTPException(status_code=402, detail="No API key configured for this provider")
            if cost > 0 and user_id:
                deduct_credits(str(user_id), cost)

        result = get_or_generate_cog(
            source_id=body.source_id,
            geojson=body.geojson,
            buffer_meters=body.buffer_meters,
            force=body.force,
            api_key=body.api_key,
            user_id=str(user_id) if user_id else None,
        )
        result["source_type"] = source_type
        result["duration_ms"] = int((time.time() - start) * 1000)

        # Record in catalog (non-blocking)
        try:
            conn = _db_conn_factory()
            try:
                from shapely.geometry import shape
                from shapely.geometry import mapping as mp
                poly = shape(body.geojson)
                if body.buffer_meters > 0:
                    poly = poly.buffer(body.buffer_meters / 111_320.0)
                _insert_catalog_entry(
                    conn, body.source_id,
                    result.get("hash") or "",
                    result.get("cog_url", ""),
                    result.get("scene_id"),
                    poly,
                    result.get("area_km2", 0),
                    result.get("resolution"),
                    result.get("datetime"),
                    source_type,
                    result.get("cog_size_bytes") or result.get("size_bytes"),
                )
                conn.commit()
            except Exception:
                pass  # catalog write is advisory
            finally:
                conn.close()
        except Exception:
            pass

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"COG generation failed: {e}")


@app.post("/api/credits/estimate")
async def credit_estimate(body: CogGenerateRequest) -> Any:
    """Preview the credit cost before generating a COG.

    Returns estimated area in km², credit cost, and whether the
    provider is available (has API key configured).
    """
    from backend.engine.service_layer.cog_service import estimate_cost

    return estimate_cost(
        source_id=body.source_id,
        geojson=body.geojson,
        buffer_meters=body.buffer_meters,
        user_api_key=body.api_key,
    )


@app.post("/api/imagery/cog/overlap")
async def check_cog_overlap(body: CogGenerateRequest) -> Any:
    """Check if a cached COG already covers this polygon.

    Returns either an exact match (same hash) or a containing match
    (a cached COG whose bounding box fully contains the polygon).
    """
    from backend.engine.service_layer.cog_service import find_overlapping_cog

    result = find_overlapping_cog(
        body.source_id, body.geojson, body.buffer_meters
    )
    if result:
        return {"match": result["match"], "match_type": result["match_type"]}
    return {"match": None, "match_type": "none"}


# ---------------------------------------------------------------------------
# Provider API Key Management (BYOK)
# ---------------------------------------------------------------------------


class SaveProviderKeyRequest(BaseModel):
    provider_id: str
    api_key: str
    label: str = ""


@app.post("/api/imagery/provider-keys")
async def save_provider_key(body: SaveProviderKeyRequest, request: Request) -> Any:
    """Save a user's own API key for a commercial provider."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from backend.engine.service_layer.cog_service import _encrypt_key

    encrypted = _encrypt_key(body.api_key)
    conn = _db_conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO provider_api_keys (user_id, provider_id, encrypted_key, label)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id, provider_id)
                   DO UPDATE SET encrypted_key = EXCLUDED.encrypted_key,
                                 label = EXCLUDED.label,
                                 updated_at = NOW()""",
                (user_id, body.provider_id, encrypted, body.label),
            )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save key: {e}")
    finally:
        conn.close()

    return {"status": "saved", "provider_id": body.provider_id}


@app.delete("/api/imagery/provider-keys/{provider_id}")
async def delete_provider_key(provider_id: str, request: Request) -> Any:
    """Remove a saved API key for a provider."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = _db_conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM provider_api_keys WHERE user_id = %s AND provider_id = %s",
                (user_id, provider_id),
            )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete key: {e}")
    finally:
        conn.close()

    return {"status": "deleted", "provider_id": provider_id}


@app.get("/api/imagery/provider-keys")
async def list_provider_keys(request: Request) -> Any:
    """List which providers the user has saved keys for."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = _db_conn_factory()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT provider_id, label, created_at FROM provider_api_keys WHERE user_id = %s ORDER BY provider_id",
                (user_id,),
            )
            rows = cur.fetchall()
        return {"keys": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list keys: {e}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# STAC Query
# ---------------------------------------------------------------------------


@app.post("/api/stac/query")
async def stac_query(body: StacQueryRequest, request: Request) -> Any:
    """Query a STAC endpoint for available imagery assets matching a spatial filter."""
    import httpx

    headers = {"Content-Type": "application/json"}
    if body.auth_token:
        headers["Authorization"] = f"Bearer {body.auth_token}"

    search_params: dict[str, Any] = {
        "collections": [body.collection],
        "max_items": body.max_items,
    }

    if body.bbox:
        search_params["bbox"] = body.bbox
    if body.geometry:
        search_params["intersects"] = body.geometry
    if body.datetime:
        search_params["datetime"] = body.datetime

    stac_url = body.stac_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{stac_url}/search",
                json=search_params,
                headers=headers,
            )
            if resp.status_code == 404:
                resp2 = await client.get(
                    f"{stac_url}/search",
                    params=search_params,
                    headers=headers,
                )
                if resp2.status_code != 200:
                    raise HTTPException(
                        status_code=resp2.status_code,
                        detail=f"STAC query failed: {resp2.text}",
                    )
                data = resp2.json()
            elif resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"STAC query failed: {resp.text}",
                )
            else:
                data = resp.json()

        features = data.get("features", [])
        items = []

        for feat in features:
            assets = feat.get("assets", {})
            cog_url = None
            for key in ("image", "cog", "B04", "B03", "B02", "visual", "rendered_preview"):
                if key in assets:
                    cog_url = assets[key].get("href")
                    if cog_url:
                        break

            if not cog_url:
                for asset_key in assets:
                    if assets[asset_key].get("type", "").startswith("image/tiff"):
                        cog_url = assets[asset_key].get("href")
                        break

            props = feat.get("properties", {})
            items.append({
                "id": feat.get("id"),
                "bbox": feat.get("bbox"),
                "datetime": props.get("datetime"),
                "cogUrl": cog_url,
                "resolution": props.get("gsd") or props.get("eo:gsd"),
                "cloudCover": props.get("eo:cloud_cover"),
            })

        return {"items": items, "total": len(items)}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="STAC endpoint timed out")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"STAC connection failed: {e}")


# ---------------------------------------------------------------------------
# Geometry Validation
# ---------------------------------------------------------------------------


@app.post("/api/datasets/validate-geometries")
async def validate_geometries(body: ValidateGeometriesRequest, request: Request) -> Any:
    """Server-side geometry validation using Shapely."""
    try:
        from shapely import explain_validity, is_simple, is_valid, wkt
    except ImportError:
        raise HTTPException(status_code=500, detail="Shapely not available")

    results = []

    for entry in body.geometries:
        wkt_str = entry.get("wkt", "")
        idx = entry.get("id", "")

        try:
            geom = wkt.loads(wkt_str)
        except Exception:
            results.append({
                "index": idx,
                "vertexCount": 0,
                "areaSqM": 0,
                "isValid": False,
                "isSimple": False,
                "hasSelfIntersections": True,
                "hasWrongRingOrientation": False,
                "isDegenerate": True,
                "bbox": None,
                "warnings": [],
                "errors": ["Invalid WKT: could not parse geometry"],
            })
            continue

        errors = []
        warnings = []
        has_self_intersection = False
        has_wrong_orientation = False
        is_degenerate = False

        if not bool(is_valid(geom)):
            reason = explain_validity(geom)
            errors.append(f"Invalid geometry: {reason}")

        if not bool(is_simple(geom)):
            has_self_intersection = True
            if "Self-intersection" not in " ".join(errors):
                errors.append("Self-intersection detected")

        if geom.geom_type == "Polygon":
            if not geom.exterior.is_ccw:
                has_wrong_orientation = True
                warnings.append("Exterior ring should be counter-clockwise")
        elif geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                if not poly.exterior.is_ccw:
                    has_wrong_orientation = True
                    warnings.append("Exterior ring orientation warning in polygon")

        try:
            area = geom.area
            centroid = geom.centroid
            cos_lat = abs(math.cos(math.radians(centroid.y))) if centroid.y is not None else 1.0
            area_sq_m = area * (111320 ** 2) * cos_lat
        except Exception:
            area_sq_m = 0

        try:
            bbox = list(geom.bounds) if not geom.is_empty else None
        except Exception:
            bbox = None

        vertex_count = 0
        if geom.geom_type == "Polygon":
            vertex_count = len(geom.exterior.coords)
        elif geom.geom_type == "MultiPolygon":
            vertex_count = sum(len(p.exterior.coords) for p in geom.geoms)

        if vertex_count < 3:
            is_degenerate = True
            errors.append("Degenerate: too few vertices (< 3)")
        if area_sq_m < 0.01:
            is_degenerate = True
            errors.append("Degenerate: zero or near-zero area")
        if vertex_count > 500:
            warnings.append(f"Large polygon: {vertex_count} vertices — may impact performance")

        results.append({
            "index": idx,
            "vertexCount": vertex_count,
            "areaSqM": round(area_sq_m, 2),
            "isValid": len(errors) == 0,
            "isSimple": not has_self_intersection,
            "hasSelfIntersections": has_self_intersection,
            "hasWrongRingOrientation": has_wrong_orientation,
            "isDegenerate": is_degenerate,
            "bbox": bbox,
            "warnings": warnings,
            "errors": errors,
        })

    return results


# ---------------------------------------------------------------------------
# Batch Validation
# ---------------------------------------------------------------------------

_batch_jobs: dict[str, dict[str, Any]] = {}


@app.post("/api/datasets/batch-validate")
async def batch_validate(
    body: BatchValidateRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> Any:
    """Upload a polygon set and validate all polygons against the specified imagery source."""
    from uuid import uuid4

    command = UploadPolygonSet(
        user_id=body.user_id,
        name=body.dataset_name,
        geometries=body.geometries,
        model_version=None,
    )

    try:
        results = bus.handle(command)
        upload_result = results[0]
        set_id = upload_result.get("set_id")
        polygon_count = upload_result.get("polygon_count", len(body.geometries))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = str(uuid4())
    _batch_jobs[job_id] = {
        "set_id": set_id,
        "polygon_count": polygon_count,
        "total": polygon_count,
        "completed": 0,
        "status": "pending",
        "imagery_source": body.imagery_source,
    }

    return {
        "set_id": set_id,
        "job_id": job_id,
        "polygon_count": polygon_count,
    }


@app.get("/api/datasets/batch-progress/{job_id}")
async def get_batch_progress(job_id: str, request: Request) -> Any:
    """Get the current progress of a batch validation job."""
    job = _batch_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Satellite Imagery Fetch — Two-Phase Pipeline
# ---------------------------------------------------------------------------


class ImageryFetchRequest(BaseModel):
    source_id: str = Field(min_length=1)
    geojson: dict[str, Any]
    buffer_meters: int = 0
    date_from: str | None = None
    date_to: str | None = None
    max_cloud_cover: float = Field(default=0, ge=0, le=100)
    mosaic: bool = True
    api_key: str | None = None


@app.post("/api/imagery/fetch")
async def fetch_imagery(body: ImageryFetchRequest, request: Request) -> Any:
    """Fetch satellite imagery for a polygon.

    Two-phase pipeline:

      **Phase 1 (synchronous, ~1s):** Queries STAC for scenes matching
      the polygon, date range, and cloud cover filters. Returns a
      ``preview_url`` (signed COG asset) that can be rendered instantly
      via ``/cog/tiles/...?url={preview_url}&geojson={geojson}``.

      **Phase 2 (background):** Generates a clipped, cached COG by
      building a VRT mosaic from the matching scenes, clipping to the
      polygon+buffer, and uploading to GCS. Poll the status endpoint
      ``GET /api/imagery/fetch/status/{job_hash}`` until ``"ready"``,
      then swap to the pre-clipped COG URL (no ``&geojson=`` needed).

    For commercial sources (no STAC preview) Phase 1 = Phase 2 — the
    response includes ``preview_available: false`` and the caller should
    poll the status endpoint immediately.
    """
    from backend.engine.service_layer.cog_service import (
        get_preview_scene,
        generate_clipped_cog_background,
        _get_source_type,
        _mosaic_hash,
        deduct_credits,
    )
    from backend.engine.service_layer.exceptions import (
        SatellitePipelineError,
        NoScenesFoundError,
    )

    source_type = _get_source_type(body.source_id)
    user_id = getattr(request.state, "user_id", None)
    job_hash = _mosaic_hash(
        body.geojson, body.source_id, body.buffer_meters,
        body.date_from, body.date_to, body.max_cloud_cover,
    )

    if source_type == "stac":
        try:
            preview = get_preview_scene(
                source_id=body.source_id,
                geojson=body.geojson,
                buffer_meters=body.buffer_meters,
                date_from=body.date_from,
                date_to=body.date_to,
                max_cloud_cover=body.max_cloud_cover,
            )
        except NoScenesFoundError:
            raise HTTPException(
                status_code=404,
                detail="No satellite imagery found for this area with the current filters.",
            )
        except SatellitePipelineError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)

        generate_clipped_cog_background(
            source_id=body.source_id,
            geojson=body.geojson,
            buffer_meters=body.buffer_meters,
            date_from=body.date_from,
            date_to=body.date_to,
            max_cloud_cover=body.max_cloud_cover,
            user_id=str(user_id) if user_id else None,
        )

        return {
            "status": "preview",
            "job_hash": job_hash,
            "preview_available": True,
            "preview_url": preview["preview_url"],
            "scene_count": preview["scene_count"],
            "scene_ids": preview["scene_ids"],
            "datetime_from": preview["datetime_from"],
            "datetime_to": preview["datetime_to"],
            "cloud_cover_avg": preview["cloud_cover_avg"],
            "resolution": preview["resolution"],
            "area_km2": preview["area_km2"],
            "source_type": source_type,
        }

    elif source_type == "commercial":
        if not body.api_key:
            from backend.engine.service_layer.cog_service import estimate_cost
            est = estimate_cost(body.source_id, body.geojson, body.buffer_meters)
            cost = est["cost_credits"]
            if cost > 0 and not est.get("provider_available"):
                raise HTTPException(status_code=402, detail="No API key configured for this provider")
            if cost > 0 and user_id:
                deduct_credits(str(user_id), cost)

        job_hash = generate_clipped_cog_background(
            source_id=body.source_id,
            geojson=body.geojson,
            buffer_meters=body.buffer_meters,
            date_from=body.date_from,
            date_to=body.date_to,
            max_cloud_cover=body.max_cloud_cover,
            api_key=body.api_key,
            user_id=str(user_id) if user_id else None,
        )
        return {
            "status": "processing",
            "job_hash": job_hash,
            "preview_available": False,
            "source_type": source_type,
        }

    else:
        raise HTTPException(status_code=400, detail=f"Source '{body.source_id}' does not support COG generation.")


@app.get("/api/imagery/fetch/status/{job_hash}")
async def fetch_imagery_status(job_hash: str) -> Any:
    """Poll the status of a background clipped-COG generation job.

    Returns ``{"status": "processing"}`` while the job runs,
    ``{"status": "ready", "cog_url": "...", ...}`` on completion, or
    ``{"status": "error", "error": "..."}`` on failure.
    """
    from backend.engine.service_layer.cog_service import get_job_status

    status = get_job_status(job_hash)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status

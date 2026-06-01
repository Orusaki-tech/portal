from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

import psycopg2
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from backend.engine.bootstrap import bootstrap
from backend.engine.domain.commands import (
    AssignParticipant,
    CorrectBoundary,
    CreateInitiative,
    GenerateGridBlocks,
    ListDatasetForSale,
    LockGridBlock,
    PurchaseDataset,
    RequestExport,
    TopUpCredits,
    UploadPolygonSet,
    ValidatePolygon,
)
from backend.engine.service_layer.export_worker import ExportWorker
from backend.engine.service_layer.messagebus import MessageBus


_worker: ExportWorker | None = None


def _db_conn_factory() -> psycopg2.extensions.connection:
    import os
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
    return bootstrap()


app = FastAPI(
    title="RealitySync API",
    version="0.1.0",
    description="Geospatial boundary validation and data curation API",
    lifespan=lifespan,
)


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
    budget_credits: float | None = None


class LockGridBlockRequest(BaseModel):
    grid_id: UUID
    user_id: UUID


class TopUpCreditsRequest(BaseModel):
    user_id: UUID
    amount: float


class RequestExportRequest(BaseModel):
    user_id: UUID
    export_format: str
    source_type: str
    source_id: UUID


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
    price_tokens: float
    geometry_count: int = 0
    description: str | None = None


class PurchaseDatasetRequest(BaseModel):
    listing_id: UUID
    buyer_id: UUID


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@app.post("/api/datasets/upload")
async def upload_dataset(
    body: UploadPolygonSetRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> dict:
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
) -> dict:
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
) -> dict:
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
) -> dict:
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
) -> dict:
    return {
        "items": [],
        "total": 0,
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
) -> dict:
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


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


@app.post("/api/exports")
async def request_export(
    body: RequestExportRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> dict:
    try:
        results = bus.handle(
            RequestExport(
                user_id=body.user_id,
                export_format=body.export_format,
                source_type=body.source_type,
                source_id=body.source_id,
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
) -> dict:
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
) -> dict:
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
) -> dict:
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


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------


@app.get("/api/marketplace/listings")
async def list_marketplace(
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> dict:
    return {
        "listings": [],
        "total": 0,
    }


@app.post("/api/marketplace/listings")
async def create_listing(
    body: ListDatasetForSaleRequest,
    bus: Annotated[MessageBus, Depends(get_bus)],
) -> dict:
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
) -> dict:
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

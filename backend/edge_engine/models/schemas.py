from datetime import datetime

from pydantic import BaseModel, Field


class PolygonInput(BaseModel):
    polygon_id: str
    geometry: dict  # GeoJSON geometry
    buffer_meters: float = 2.0


class VertexMetric(BaseModel):
    vertex_index: int
    deviation_meters: float
    spectral_contrast: float
    snake_strain: float
    confidence_score: float


class EdgeResult(BaseModel):
    polygon_id: str
    run_id: str
    is_ambiguous: bool
    confidence_avg: float
    vertices: list[VertexMetric]
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class STACQuery(BaseModel):
    bbox: list[float]  # [west, south, east, north]
    datetime: str | None = None
    collections: list[str] = ["naip"]
    limit: int = 5


class ValidationRunRequest(BaseModel):
    polygon_set_id: str
    imagery_id: str | None = None
    region: dict | None = None
    confidence_threshold: float = 0.7

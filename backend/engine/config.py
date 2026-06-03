from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass(frozen=True)
class EdgeConfig:
    stac_api_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    stac_collection: str = "naip"
    stac_max_items: int = 5
    buffer_width_meters: float = 2.0
    contrast_clip_percentiles: list[float] = field(default_factory=lambda: [2, 98])
    kmeans_n_clusters: int = 3
    kmeans_random_state: int = 42
    snake_max_iterations: int = 100
    snake_alpha: float = 0.01
    snake_beta: float = 0.1
    snake_convergence: float = 0.1
    confidence_spectral_weight: float = 0.40
    confidence_movement_weight: float = 0.30
    confidence_deviation_weight: float = 0.30
    confidence_threshold: float = 0.70
    export_valid_formats: tuple[str, ...] = (
        "geojson", "coco", "yolo", "pascal_voc", "tfrecord", "parquet", "geopackage",
    )
    export_valid_sources: tuple[str, ...] = ("dataset", "initiative", "grid")


def load_edge_config(path: str | None = None) -> EdgeConfig:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "edge", "edge_config.yaml")
    if not os.path.exists(path):
        return EdgeConfig()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return EdgeConfig(
        stac_api_url=data.get("stac", {}).get("api_url", EdgeConfig.stac_api_url),
        stac_collection=data.get("stac", {}).get("collection", EdgeConfig.stac_collection),
        stac_max_items=data.get("stac", {}).get("max_items", EdgeConfig.stac_max_items),
        buffer_width_meters=data.get("buffer", {}).get("width_meters", EdgeConfig.buffer_width_meters),
        contrast_clip_percentiles=data.get("contrast", {}).get("clip_percentiles", EdgeConfig.contrast_clip_percentiles),
        kmeans_n_clusters=data.get("kmeans", {}).get("n_clusters", EdgeConfig.kmeans_n_clusters),
        kmeans_random_state=data.get("kmeans", {}).get("random_state", EdgeConfig.kmeans_random_state),
        snake_max_iterations=data.get("snake", {}).get("max_iterations", EdgeConfig.snake_max_iterations),
        snake_alpha=data.get("snake", {}).get("alpha", EdgeConfig.snake_alpha),
        snake_beta=data.get("snake", {}).get("beta", EdgeConfig.snake_beta),
        snake_convergence=data.get("snake", {}).get("convergence", EdgeConfig.snake_convergence),
        confidence_spectral_weight=data.get("confidence", {}).get("spectral_weight", EdgeConfig.confidence_spectral_weight),
        confidence_movement_weight=data.get("confidence", {}).get("movement_weight", EdgeConfig.confidence_movement_weight),
        confidence_deviation_weight=data.get("confidence", {}).get("deviation_weight", EdgeConfig.confidence_deviation_weight),
        confidence_threshold=data.get("confidence", {}).get("threshold", EdgeConfig.confidence_threshold),
        export_valid_formats=tuple(data.get("export", {}).get("valid_formats", list(EdgeConfig.export_valid_formats))),
        export_valid_sources=tuple(data.get("export", {}).get("valid_sources", list(EdgeConfig.export_valid_sources))),
    )

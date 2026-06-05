"""
Commercial satellite provider adapters.

Each adapter implements the ``BaseProvider`` interface:

  - ``search(polygon, api_key) → list[Scene]``
  - ``estimate_cost(scene, area_km2) → int``
  - ``download(scene_id, api_key, dest_path) → None``

Implemented providers (2026-06):

  - **Planet** (PSScene, SkySatCollect) — Orders API v2
  - **Maxar** (WorldView-3, GeoEye-1) — SecureWatch API

Stubs for Airbus (OneAtlas) and BlackSky are included but raise
``NotImplementedError`` until their API credentials are configured.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @abstractmethod
    def search(self, polygon, api_key: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def estimate_cost(self, scene: dict[str, Any], area_km2: float) -> int: ...

    @abstractmethod
    def download(self, scene_id: str, api_key: str, dest_path: str) -> None: ...


# ---------------------------------------------------------------------------
# Planet — Orders API v2
# ---------------------------------------------------------------------------


class PlanetProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "planet"

    def search(self, polygon, api_key: str) -> list[dict[str, Any]]:
        url = "https://api.planet.com/data/v2/quick-search"
        geojson = polygon.__geo_interface__
        payload = {
            "item_types": ["PSScene", "SkySatCollect"],
            "filter": {
                "type": "GeometryFilter",
                "field_name": "geometry",
                "config": geojson,
            },
        }
        with httpx.Client(timeout=30.0, auth=(api_key, "")) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        features = data.get("features", [])
        results = []
        for feat in features:
            props = feat.get("properties", {})
            results.append({
                "scene_id": feat["id"],
                "datetime": props.get("acquired") or props.get("published"),
                "resolution": props.get("gsd") or props.get("resolution"),
                "cloud_cover": props.get("cloud_cover"),
                "geometry": feat.get("geometry"),
            })
        return results

    def estimate_cost(self, scene: dict[str, Any], area_km2: float) -> int:
        return max(2, int(area_km2 * 2))

    def download(self, scene_id: str, api_key: str, dest_path: str) -> None:
        url = f"https://api.planet.com/data/v2/items/{scene_id}/assets"
        with httpx.Client(timeout=30.0, auth=(api_key, "")) as client:
            resp = client.get(url)
            resp.raise_for_status()
            assets = resp.json()

        # Find the best asset for download
        asset_url = None
        for key in ("ortho_analytic_4b", "ortho_analytic_8b", "ortho_visual", "visual", "analytic"):
            if key in assets:
                asset_url = assets[key].get("location") or assets[key].get("href")
                if asset_url:
                    break

        if not asset_url:
            raise ValueError(f"No downloadable asset found for scene {scene_id}")

        with httpx.Client(timeout=300.0, auth=(api_key, "")) as client:
            resp = client.get(asset_url)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(resp.content)


# ---------------------------------------------------------------------------
# Maxar — SecureWatch API
# ---------------------------------------------------------------------------


class MaxarProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "maxar"

    def search(self, polygon, api_key: str) -> list[dict[str, Any]]:
        url = "https://securewatch.maxar.com/connect/v1/search"
        coords = list(polygon.exterior.coords)
        geojson = {"type": "Polygon", "coordinates": [coords]}
        payload = {
            "searchType": "geometry",
            "geometry": geojson,
            "maxResults": 5,
        }
        headers = {"API-Key": api_key}
        with httpx.Client(timeout=30.0, headers=headers) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        features = data.get("results", [])
        results = []
        for feat in features:
            results.append({
                "scene_id": feat.get("catalogId") or feat.get("id"),
                "datetime": feat.get("acquisitionDate"),
                "resolution": feat.get("resolution"),
                "cloud_cover": feat.get("cloudCover"),
                "geometry": feat.get("geometry"),
            })
        return results

    def estimate_cost(self, scene: dict[str, Any], area_km2: float) -> int:
        return max(5, int(area_km2 * 5))

    def download(self, scene_id: str, api_key: str, dest_path: str) -> None:
        url = f"https://securewatch.maxar.com/connect/v1/orders/{scene_id}"
        headers = {"API-Key": api_key}
        with httpx.Client(timeout=300.0, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        download_url = data.get("downloadUrl")
        if not download_url:
            raise ValueError(f"No download URL for scene {scene_id}")
        with httpx.Client(timeout=300.0, headers=headers) as client:
            resp = client.get(download_url)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(resp.content)


# ---------------------------------------------------------------------------
# Airbus — OneAtlas (stub / not verified)
# ---------------------------------------------------------------------------


class AirbusProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "airbus"

    def search(self, polygon, api_key: str) -> list[dict[str, Any]]:
        raise NotImplementedError("Airbus OneAtlas not yet integrated")

    def estimate_cost(self, scene: dict[str, Any], area_km2: float) -> int:
        return max(4, int(area_km2 * 4))

    def download(self, scene_id: str, api_key: str, dest_path: str) -> None:
        raise NotImplementedError("Airbus OneAtlas not yet integrated")


# ---------------------------------------------------------------------------
# BlackSky (stub / not verified)
# ---------------------------------------------------------------------------


class BlackSkyProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "blacksky"

    def search(self, polygon, api_key: str) -> list[dict[str, Any]]:
        raise NotImplementedError("BlackSky not yet integrated")

    def estimate_cost(self, scene: dict[str, Any], area_km2: float) -> int:
        return max(3, int(area_km2 * 3))

    def download(self, scene_id: str, api_key: str, dest_path: str) -> None:
        raise NotImplementedError("BlackSky not yet integrated")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, BaseProvider] = {
    "planet": PlanetProvider(),
    "maxar": MaxarProvider(),
    "airbus": AirbusProvider(),
    "blacksky": BlackSkyProvider(),
}


def get_provider(provider_id: str) -> BaseProvider | None:
    return _PROVIDERS.get(provider_id)

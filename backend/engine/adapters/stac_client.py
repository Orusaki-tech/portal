from __future__ import annotations

from abc import ABC, abstractmethod

from shapely.geometry import Polygon, shape
from pystac_client import Client as StacClient


class AbstractStacClient(ABC):
    @abstractmethod
    def find_best_imagery_for_polygon(self, geometry: Polygon) -> str | None:
        ...


class PystacClient(AbstractStacClient):
    def __init__(self, stac_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1") -> None:
        self._stac_url = stac_url

    def find_best_imagery_for_polygon(self, geometry: Polygon) -> str | None:
        catalog = StacClient.open(self._stac_url)
        search = catalog.search(
            collections=["naip"],
            intersects=shape(geometry.__geo_interface__),
            max_items=1,
        )
        items = list(search.items())
        if not items:
            return None
        return str(items[0].id)

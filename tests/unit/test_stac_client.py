from __future__ import annotations

import pytest
from shapely import wkt

from backend.engine.adapters.stac_client import (
    AbstractStacClient,
    PystacClient,
)

AUSTIN_BUILDING = wkt.loads(
    "POLYGON((-97.734 30.267, -97.733 30.267, -97.733 30.268, -97.734 30.268, -97.734 30.267))"
)


@pytest.mark.integration
def test_stac_client_returns_naip_for_austin_area() -> None:
    """Integration test: STAC client should find NAIP imagery for central Austin, TX."""
    client: AbstractStacClient = PystacClient(
        stac_url="https://planetarycomputer.microsoft.com/api/stac/v1",
    )
    result = client.find_best_imagery_for_polygon(AUSTIN_BUILDING)
    assert result is not None, "Expected to find NAIP imagery for Austin, TX area"
    assert result.startswith("naip/"), f"Expected NAIP collection item, got {result}"


@pytest.mark.integration
def test_stac_client_returns_none_for_ocean_polygon() -> None:
    """STAC client should return None for a polygon in the middle of the Pacific."""
    ocean_point = wkt.loads("POLYGON((-179.9 0.1, -179.8 0.1, -179.8 0.2, -179.9 0.2, -179.9 0.1))")
    client: AbstractStacClient = PystacClient(
        stac_url="https://planetarycomputer.microsoft.com/api/stac/v1",
    )
    result = client.find_best_imagery_for_polygon(ocean_point)
    assert result is None

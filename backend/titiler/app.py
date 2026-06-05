"""
TiTiler-based dynamic tile server for RealitySync.

Serves Cloud Optimized GeoTIFFs (COGs) as standard web map tiles
on-the-fly. The primary route is ``/cog/tiles/...`` (TilerFactory),
which supports ``&geojson=...`` clipping natively.
"""

import os

import sentry_sdk
from fastapi import FastAPI, Query
from fastapi.responses import Response
from starlette.middleware.cors import CORSMiddleware
from titiler.core.factory import TilerFactory

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("APP_ENV", "development"),
    traces_sample_rate=0.1,
)

app = FastAPI(
    title="RealitySync Tile Server",
    description="Dynamic COG tile server for RealitySync boundary validation platform",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

cog_tiler = TilerFactory()
app.include_router(cog_tiler.router, prefix="/cog")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tiles/{z}/{x}/{y}")
async def tile(
    z: int,
    x: int,
    y: int,
    url: str = Query(..., description="COG URL"),
    format: str = Query("png", description="Output format: png, webp, jpg"),
) -> Response:
    """
    Serve a single map tile from a COG by downloading the raw file into memory.

    For production, prefer the ``/cog/tiles/...`` TilerFactory route which supports
    ``&geojson=`` clipping and HTTP Range requests natively.
    """
    import httpx
    from rasterio.io import MemoryFile
    from titiler.core.factory import TileFactory

    tile_factory = TileFactory()
    tile_params = tile_factory.get_tile_params(z, x, y)

    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return Response(status_code=404, content=f"COG not found: {exc}")

    try:
        with MemoryFile(resp.content) as memfile:
            with memfile.open() as src:
                tile_data = src.read(
                    indexes=[1, 2, 3],
                    window=tile_params.window,
                    out_shape=(3, tile_params.height, tile_params.width),
                )
    except Exception as exc:
        return Response(status_code=500, content=f"Tile read error: {exc}")

    from io import BytesIO

    import numpy as np

    tile_data = np.clip(tile_data, 0, 255).astype(np.uint8)

    form = format.lower()
    from PIL import Image

    img = Image.fromarray(np.moveaxis(tile_data, 0, -1))
    buf = BytesIO()
    if form == "png":
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    elif form == "jpg":
        img.save(buf, format="JPEG", quality=85)
        return Response(content=buf.getvalue(), media_type="image/jpeg")
    else:
        img.save(buf, format="WEBP", quality=80)
        return Response(content=buf.getvalue(), media_type="image/webp")


@app.on_event("startup")
async def startup() -> None:
    print("TiTiler server started. Ready to serve COG tiles.")

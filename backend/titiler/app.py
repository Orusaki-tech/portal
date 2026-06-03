"""
TiTiler-based dynamic tile server for RealitySync.

Serves Cloud Optimized GeoTIFFs (COGs) as standard web map tiles
on-the-fly. Supports both public STAC-hosted NAIP imagery and
user-uploaded COGs stored in GCS.

Intended to run behind Cloud CDN for edge caching.
"""

import os
import re

import sentry_sdk
from fastapi import FastAPI, Query
from fastapi.responses import Response
from rasterio.io import MemoryFile
from starlette.middleware.cors import CORSMiddleware
from titiler.core.factory import TilerFactory
from titiler.core.resources.enums import ImageType

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("APP_ENV", "development"),
    traces_sample_rate=0.1,
)

app = FastAPI(
    title="RealitySync Tile Server",
    description="Dynamic COG tile server for RealitySync boundary validation platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

cog_tiler = TilerFactory()
app.include_router(cog_tiler.router, prefix="/cog")


COG_PATTERN = re.compile(r"^https?://storage\.googleapis\.com/([^/]+)/(.+\.tif)")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tiles/{z}/{x}/{y}")
async def tile(
    z: int,
    x: int,
    y: int,
    url: str = Query(..., description="COG URL"),
    format: str = Query("webp", description="Output format: png, webp, jpg"),
) -> Response:
    """
    Serve a single map tile from a COG.
    URL points to either a public STAC-hosted COG (NAIP) or a user-uploaded COG in GCS.
    """
    import httpx
    from titiler.core.factory import TileFactory

    tile_factory = TileFactory()
    tile_params = tile_factory.get_tile_params(z, x, y)

    image_type = (
        ImageType[format.upper()] if format.upper() in ImageType.__members__ else ImageType.WEBP
    )

    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return Response(status_code=404, content=f"COG not found or unreachable: {exc}")

    with MemoryFile(resp.content) as memfile:
        with memfile.open() as src:
            tile_data = src.read(
                indexes=[1, 2, 3],
                window=tile_params.window,
                out_shape=(3, tile_params.height, tile_params.width),
            )

    from io import BytesIO

    import numpy as np

    tile_data = np.clip(tile_data, 0, 255).astype(np.uint8)

    # Encode to requested format
    if image_type == ImageType.PNG:
        from PIL import Image

        img = Image.fromarray(np.moveaxis(tile_data, 0, -1))
        buf = BytesIO()
        img.save(buf, format="PNG")
        content = buf.getvalue()
        media_type = "image/png"
    elif image_type == ImageType.JPEG:
        from PIL import Image

        img = Image.fromarray(np.moveaxis(tile_data, 0, -1))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        content = buf.getvalue()
        media_type = "image/jpeg"
    else:
        from PIL import Image

        img = Image.fromarray(np.moveaxis(tile_data, 0, -1))
        buf = BytesIO()
        img.save(buf, format="WEBP", quality=80)
        content = buf.getvalue()
        media_type = "image/webp"

    return Response(content=content, media_type=media_type)


@app.on_event("startup")
async def startup() -> None:
    print("TiTiler server started. Ready to serve COG tiles.")

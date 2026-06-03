from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiles", tags=["tiles"])

PLANET_API_KEY = os.environ.get("PLANET_API_KEY", "")
NAIP_TILE_TEMPLATE = (
    "https://tiles.planet.com/basemaps/v1/planet-tiles/"
    "global_quarterly_2024q1mosaic/gmap/{z}/{x}/{y}.png"
)

_LOCAL_UPLOAD_DIR = Path(os.environ.get("LOCAL_UPLOAD_DIR", "uploads"))

_client = httpx.AsyncClient(timeout=10.0)


@router.get("/naip/{z}/{x}/{y}.png")
async def proxy_naip_tile(z: int, x: int, y: int) -> Response:
    if not PLANET_API_KEY:
        raise HTTPException(status_code=502, detail="PLANET_API_KEY not configured")
    url = f"{NAIP_TILE_TEMPLATE.format(z=z, x=x, y=y)}?{urlencode({'api_key': PLANET_API_KEY})}"
    resp = await _client.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Tile fetch failed")
    return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/png"))


@router.get("/user/{imagery_id}/{z}/{x}/{y}.png")
async def serve_user_imagery_tile(imagery_id: str, z: int, x: int, y: int) -> Response:
    """Serve a map tile from a user-uploaded imagery file using rio-tiler."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "realitysync"),
        user=os.environ.get("DB_USER", "realitysync"),
        password=os.environ.get("DB_PASSWORD", "realitysync"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cog_uri, gcs_uri FROM user_imagery WHERE id = %s AND status = 'ready'",
                (imagery_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Imagery not found or not ready")

    cog_uri, gcs_uri = row
    file_path = cog_uri or gcs_uri

    if file_path.startswith("local://"):
        local_path = _LOCAL_UPLOAD_DIR / Path(file_path[7:]).name
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Local file not found")
        try:
            from rio_tiler.io import Reader
            from io import BytesIO
            import numpy as np

            with Reader(str(local_path)) as reader:
                tile_data = reader.tile(x, y, z, tilesize=256)
                data = tile_data.data
                mask = tile_data.mask

            if data.shape[0] == 1:
                data = np.repeat(data, 3, axis=0)
            data = np.clip(data, 0, 255).astype(np.uint8)
            from PIL import Image

            arr = np.transpose(data, (1, 2, 0))
            if mask is not None and mask.any():
                arr = np.dstack((arr, mask))
            img = Image.fromarray(arr)
            buf = BytesIO()
            img.save(buf, format="PNG")
            return Response(content=buf.getvalue(), media_type="image/png")
        except Exception as e:
            logger.exception("Tile read failed for %s", local_path)
            raise HTTPException(status_code=502, detail=f"Tile read failed: {e}")

    raise HTTPException(status_code=502, detail="Only local files are supported for tile serving")

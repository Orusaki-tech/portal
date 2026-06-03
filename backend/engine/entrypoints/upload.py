from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg2
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

try:
    import google.cloud.storage as storage
except ImportError:
    storage = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

_BUCKET = "realitysync-raw-uploads"
_LOCAL_UPLOAD_DIR = Path(os.environ.get("LOCAL_UPLOAD_DIR", "uploads"))


def _db_conn_factory() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "realitysync"),
        user=os.environ.get("DB_USER", "realitysync"),
        password=os.environ.get("DB_PASSWORD", "realitysync"),
    )


class GenerateUploadUrlRequest(BaseModel):
    user_id: UUID
    filename: str
    content_type: str


class GenerateUploadUrlResponse(BaseModel):
    upload_url: str
    object_path: str


class UploadCallbackRequest(BaseModel):
    user_id: UUID
    filename: str
    object_path: str


@router.post("/generate-url", response_model=GenerateUploadUrlResponse)
async def generate_upload_url(
    body: GenerateUploadUrlRequest,
) -> GenerateUploadUrlResponse:
    object_path = f"uploads/{body.user_id}/{uuid4()}_{body.filename}"

    if storage is None:
        upload_url = f"https://storage.googleapis.com/{_BUCKET}/{object_path}"
        logger.warning("google.cloud.storage not available — returning placeholder URL")
    else:
        client = storage.Client()
        bucket = client.bucket(_BUCKET)
        blob = bucket.blob(object_path)
        upload_url = blob.create_resumable_upload_session(
            content_type=body.content_type,
        )

    return GenerateUploadUrlResponse(upload_url=upload_url, object_path=object_path)


@router.post("/callback")
async def upload_callback(body: UploadCallbackRequest) -> dict:
    gcs_uri = f"gs://{_BUCKET}/{body.object_path}"

    if storage is not None:
        client = storage.Client()
        bucket = client.bucket(_BUCKET)
        blob = bucket.blob(body.object_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Object not found in GCS")

    imagery_id = uuid4()

    conn = _db_conn_factory()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_imagery (id, user_id, original_filename, gcs_uri, status)
                    VALUES (%s, %s, %s, %s, 'uploaded')
                    """,
                    (imagery_id, body.user_id, body.filename, gcs_uri),
                )
    finally:
        conn.close()

    logger.info("Created user_imagery record %s for user %s", imagery_id, body.user_id)
    return {"imagery_id": str(imagery_id), "status": "uploaded"}


@router.post("/local")
async def upload_local(
    file: UploadFile,
    user_id: UUID,
) -> dict:
    """Direct file upload for local development — saves file to LOCAL_UPLOAD_DIR and serves tiles."""
    _LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{uuid4()}"
    ext = Path(file.filename or "unknown").suffix
    local_path = _LOCAL_UPLOAD_DIR / f"{stem}{ext}"
    cog_path = _LOCAL_UPLOAD_DIR / f"{stem}_cog.tif"

    content = await file.read()
    local_path.write_bytes(content)

    imagery_id = uuid4()
    local_uri = f"local://{local_path}"
    cog_uri = None

    try:
        from osgeo import gdal
        gdal.Translate(str(cog_path), str(local_path), options="-of COG")
        cog_uri = f"local://{cog_path}"
        logger.info("Converted upload to COG at %s", cog_path)
    except Exception:
        logger.warning("GDAL not available — serving raw upload as-is")
        cog_path = local_path

    conn = _db_conn_factory()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_imagery (id, user_id, original_filename, gcs_uri, cog_uri, status)
                    VALUES (%s, %s, %s, %s, %s, 'ready')
                    """,
                    (imagery_id, user_id, file.filename, local_uri, cog_uri or local_uri),
                )
    finally:
        conn.close()

    logger.info("Created local user_imagery record %s for user %s", imagery_id, user_id)
    return {"imagery_id": str(imagery_id), "status": "ready", "file_path": str(cog_path)}

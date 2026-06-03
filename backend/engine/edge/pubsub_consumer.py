from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LANDING_BUCKET = "realitysync-raw-uploads"
PRODUCTION_BUCKET = "realitysync-cogs"

try:
    from google.cloud import storage as gcs

    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False
    logger.warning("google.cloud.storage not available — GCS operations disabled")


def process_validation_message(message: dict[str, Any]) -> None:
    polygon_id = message.get("polygon_id")
    run_id = message.get("run_id")
    results_url = message.get("results_url")

    logger.info(
        "Validation message received — polygon_id=%s run_id=%s results_url=%s",
        polygon_id,
        run_id,
        results_url,
    )


def process_export_message(message: dict[str, Any]) -> None:
    export_id = message.get("export_id")
    user_id = message.get("user_id")
    export_format = message.get("export_format")
    source_type = message.get("source_type")
    source_id = message.get("source_id")

    logger.info(
        "Export message received — export_id=%s user_id=%s format=%s source=%s/%s",
        export_id,
        user_id,
        export_format,
        source_type,
        source_id,
    )


def process_imagery_upload_message(message: dict[str, Any]) -> None:
    bucket_name = message.get("bucket", LANDING_BUCKET)
    blob_name = message.get("name", "")

    if not blob_name or not blob_name.lower().endswith((".tif", ".tiff")):
        logger.info("Skipping non-TIFF file: %s", blob_name)
        return

    if not _GCS_AVAILABLE:
        logger.warning("GCS not available — skipping COG processing for %s", blob_name)
        return

    logger.info(
        "Imagery upload message received — bucket=%s blob=%s",
        bucket_name,
        blob_name,
    )

    storage_client = gcs.Client()

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, "raw.tif")
        warped_path = os.path.join(tmpdir, "warped.tif")
        cog_path = os.path.join(tmpdir, "output_cog.tif")

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(raw_path)
        logger.info("Downloaded gs://%s/%s to %s", bucket_name, blob_name, raw_path)

        subprocess.run(
            [
                "gdalwarp",
                raw_path,
                warped_path,
                "-t_srs",
                "EPSG:3857",
                "-r",
                "bilinear",
                "-co",
                "COMPRESS=DEFLATE",
                "-co",
                "BIGTIFF=IF_SAFER",
            ],
            check=True,
        )
        logger.info("Warped to EPSG:3857")

        subprocess.run(
            [
                "gdal_translate",
                warped_path,
                cog_path,
                "-of",
                "COG",
                "-co",
                "COMPRESS=DEFLATE",
                "-co",
                "BLOCKSIZE=512",
                "-co",
                "OVERVIEWS=IGNORE_EXISTING",
                "-co",
                "RESAMPLING=LANCZOS",
            ],
            check=True,
        )
        logger.info("Translated to COG")

        cog_filename = f"{Path(blob_name).stem}_cog.tif"
        prod_bucket = storage_client.bucket(PRODUCTION_BUCKET)
        prod_blob = prod_bucket.blob(cog_filename)
        prod_blob.upload_from_filename(cog_path)
        logger.info("Uploaded COG to gs://%s/%s", PRODUCTION_BUCKET, cog_filename)

        blob.delete()
        logger.info("Deleted raw file gs://%s/%s", bucket_name, blob_name)

    logger.info("COG processing complete for %s", blob_name)

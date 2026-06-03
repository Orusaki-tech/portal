"""
GDAL Cloud Optimized GeoTIFF (COG) converter.

Triggered by Cloud Pub/Sub when a new raw image lands in the GCS landing bucket.
Runs gdalwarp + gdal_translate to produce a web-optimized COG with internal
overviews and DEFLATE compression.

Output COG is written to the production GCS bucket. The raw file is deleted
after successful processing.
"""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import sentry_sdk
from google.cloud import storage

LANDING_BUCKET = os.getenv("LANDING_BUCKET", "realitysync-raw-uploads")
PRODUCTION_BUCKET = os.getenv("PRODUCTION_BUCKET", "realitysync-cogs")
DB_DSN = os.getenv("DB_DSN", "")
PROJECT_ID = os.getenv("GCP_PROJECT", "")

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("APP_ENV", "production"),
    traces_sample_rate=0.1,
)

storage_client = storage.Client()


def download_from_gcs(bucket_name: str, blob_name: str, dest_path: str) -> None:
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(dest_path)
    print(f"Downloaded gs://{bucket_name}/{blob_name} → {dest_path}")


def upload_to_gcs(bucket_name: str, source_path: str, dest_name: str) -> None:
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(dest_name)
    blob.upload_from_filename(source_path)
    print(f"Uploaded {source_path} → gs://{bucket_name}/{dest_name}")


def delete_from_gcs(bucket_name: str, blob_name: str) -> None:
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.delete()
    print(f"Deleted gs://{bucket_name}/{blob_name}")


def warp_to_web_mercator(input_path: str, output_path: str) -> None:
    cmd = [
        "gdalwarp",
        input_path,
        output_path,
        "-t_srs",
        "EPSG:3857",
        "-r",
        "bilinear",
        "-co",
        "COMPRESS=DEFLATE",
        "-co",
        "BIGTIFF=IF_SAFER",
    ]
    subprocess.run(cmd, check=True)
    print(f"Warped to EPSG:3857 → {output_path}")


def translate_to_cog(input_path: str, output_path: str) -> None:
    cmd = [
        "gdal_translate",
        input_path,
        output_path,
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
    ]
    subprocess.run(cmd, check=True)
    print(f"Translated to COG → {output_path}")


def extract_bbox(input_path: str) -> list[float]:
    """Extract bounding box from a raster file using gdalinfo."""
    result = subprocess.run(
        ["gdalinfo", "-json", input_path],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    corner = info.get("cornerCoordinates", {})
    ul = corner.get("upperLeft", [0, 0])
    lr = corner.get("lowerRight", [0, 0])
    return [ul[0], lr[1], lr[0], ul[1]]  # w, s, e, n


def update_database(imagery_id: str, cog_uri: str, bbox: list[float], filename: str) -> None:
    """Record the processed COG metadata in Cloud SQL."""
    import psycopg2

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE user_imagery
        SET cog_uri = %s,
            bounding_box = ST_MakeEnvelope(%s, %s, %s, %s, 4326),
            status = 'READY',
            processed_at = NOW()
        WHERE id = %s
    """,
        (cog_uri, bbox[0], bbox[1], bbox[2], bbox[3], imagery_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Database updated for imagery {imagery_id}")


def find_or_create_imagery_record(filename: str) -> str:
    """Find existing record or create a new one for the uploaded file."""
    import psycopg2

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM user_imagery WHERE original_filename = %s",
        (filename,),
    )
    row = cur.fetchone()
    if row:
        imagery_id = row[0]
    else:
        imagery_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO user_imagery (id, user_id, original_filename, status)
            VALUES (%s, '00000000-0000-0000-0000-000000000000', %s, 'PROCESSING')
        """,
            (imagery_id, filename),
        )
        conn.commit()

    cur.close()
    conn.close()
    return str(imagery_id)


def process_event(event_data: dict[str, Any]) -> None:
    """Main processing function triggered by a Pub/Sub message."""
    bucket_name = event_data.get("bucket", LANDING_BUCKET)
    blob_name = event_data.get("name", "")

    if not blob_name or not blob_name.lower().endswith((".tif", ".tiff")):
        print(f"Skipping non-TIFF file: {blob_name}")
        return

    imagery_id = find_or_create_imagery_record(blob_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, "raw.tif")
        warped_path = os.path.join(tmpdir, "warped.tif")
        cog_path = os.path.join(tmpdir, "output_cog.tif")

        download_from_gcs(bucket_name, blob_name, raw_path)
        warp_to_web_mercator(raw_path, warped_path)
        translate_to_cog(warped_path, cog_path)

        cog_filename = f"{Path(blob_name).stem}_cog.tif"
        upload_to_gcs(PRODUCTION_BUCKET, cog_path, cog_filename)

        bbox = extract_bbox(cog_path)
        cog_uri = f"gs://{PRODUCTION_BUCKET}/{cog_filename}"

        update_database(imagery_id, cog_uri, bbox, blob_name)
        delete_from_gcs(bucket_name, blob_name)

    print(f"COG processing complete for {blob_name}")


if __name__ == "__main__":
    import sys

    message_json = os.getenv("PUBSUB_MESSAGE", "{}")
    if len(sys.argv) > 1:
        message_json = sys.argv[1]

    event = json.loads(message_json)
    process_event(event)

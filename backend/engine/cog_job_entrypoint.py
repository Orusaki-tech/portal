#!/usr/bin/env python3
"""Cloud Run Job entrypoint — runs COG generation synchronously with high resources."""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.service_layer.cog_service import (
    _generate_clipped_cog_sync,
    _job_status_path,
    _write_gcs_json,
    _mosaic_hash,
)

PRODUCTION_BUCKET = os.getenv("PRODUCTION_BUCKET", "realitysync-cogs")

if __name__ == "__main__":
    args = json.loads(sys.argv[1])
    geojson = args["geojson"]
    source_id = args["source_id"]
    buffer_meters = args.get("buffer_meters", 0)
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    max_cloud_cover = args.get("max_cloud_cover", 100)

    job_hash = _mosaic_hash(geojson, source_id, buffer_meters, date_from, date_to, max_cloud_cover)
    status_path = _job_status_path(job_hash)

    # Write "processing" status
    try:
        _write_gcs_json(PRODUCTION_BUCKET, status_path, {"status": "processing"})
    except Exception:
        traceback.print_exc()

    try:
        result = _generate_clipped_cog_sync(**args)

        # Write completed status
        _write_gcs_json(PRODUCTION_BUCKET, status_path, {"status": "ready", **result})
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        _write_gcs_json(PRODUCTION_BUCKET, status_path, {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        sys.exit(1)
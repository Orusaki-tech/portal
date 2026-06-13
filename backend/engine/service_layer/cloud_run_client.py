"""Lightweight Cloud Run Jobs client using metadata server auth.
No extra dependencies — relies on google-cloud-storage which is already used."""
from __future__ import annotations

import json
import os
import urllib.request


_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "project-07850c05-c54d-486b-80a")
_REGION = os.getenv("REGION", "us-central1")
_JOB_NAME = os.getenv("COG_JOB_NAME", "realitysync-cog-worker")


def _get_id_token(audience: str) -> str:
    req = urllib.request.Request(
        f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}"
    )
    req.add_header("Metadata-Flavor", "Google")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode()


def submit_cog_job(args: dict) -> str:
    """Submit a Cloud Run Job execution and return the execution name."""
    audience = "https://run.googleapis.com"
    token = _get_id_token(audience)
    name = f"projects/{_PROJECT_ID}/locations/{_REGION}/jobs/{_JOB_NAME}"
    url = f"https://{_REGION}-run.googleapis.com/v2/{name}:run"

    body = json.dumps({
        "overrides": {"containerOverrides": [{
            "args": ["-m", "backend.engine.cog_job_entrypoint", json.dumps(args)]
        }]}
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result["metadata"]["name"]

#!/bin/sh
# Cloud Run Job wrapper — passes args correctly to the Python module.
exec python -m backend.engine.cog_job_entrypoint "$@"
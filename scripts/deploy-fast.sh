#!/usr/bin/env bash
# Fast deploy a single service — build+deploy only what changed.
# Usage:
#   PROJECT_ID=project-07850c05-c54d-486b-80a bash scripts/deploy-fast.sh titiler

set -euo pipefail
SERVICE="${1:?Usage: bash scripts/deploy-fast.sh <api|titiler|frontend>}"
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"

gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config=<(sed -n "/# ── [$]SERVICE/,/^[[:space:]]*# ──/p" cloudbuild.yaml) \
  --substitutions="_REGION=${REGION},_ARTIFACT_REGISTRY=${REGION}-docker.pkg.dev/${PROJECT_ID}/realitysync,_CLOUD_SQL_INSTANCE=${PROJECT_ID}:us-east1:affordable-gadgets-production-pg"

echo "Done: realitysync-${SERVICE}"
gcloud run services describe "realitysync-${SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)'

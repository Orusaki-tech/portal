#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# RealitySync — GCP Cloud Run deployment script
# Prerequisites:
#   1. gcloud CLI installed and authenticated
#   2. A GCP project with billing enabled
#   3. Cloud SQL PostGIS instance running
#   4. Artifact Registry repository created
#
# Usage:
#   export PROJECT_ID=your-gcp-project
#   export REGION=us-central1
#   bash scripts/deploy-gcp.sh
# ────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-east1}"
ARTIFACT_REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/realitysync"
CLOUD_SQL_INSTANCE="${PROJECT_ID}:${REGION}:affordable-gadgets-production-pg"

echo "═══ RealitySync GCP Deployment ═══"
echo " Project:       ${PROJECT_ID}"
echo " Region:        ${REGION}"
echo " Artifact Reg:  ${ARTIFACT_REGISTRY}"
echo " Cloud SQL:     ${CLOUD_SQL_INSTANCE}"
echo ""

# ── 1. Create secrets for DB credentials (if not exist) ────────
echo "── 1. Ensuring secrets ──"
for secret in realitysync-db-user realitysync-db-password; do
  if ! gcloud secrets describe "${secret}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Creating secret: ${secret}"
    printf "realitysync" | gcloud secrets create "${secret}" \
      --project="${PROJECT_ID}" \
      --replication-policy="automatic" \
      --data-file=-
  fi
done

# ── 2. Submit Cloud Build job ──────────────────────────────────
echo "── 2. Submitting Cloud Build ──"
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config=cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_ARTIFACT_REGISTRY=${ARTIFACT_REGISTRY},_CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE}"

# ── 3. Print deployed URLs ─────────────────────────────────────
echo ""
echo "═══ Deployment Complete ═══"
echo ""
echo "API:"
gcloud run services describe realitysync-api \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format='value(status.url)'

echo "Frontend:"
gcloud run services describe realitysync-frontend \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format='value(status.url)'

echo "TiTiler:"
gcloud run services describe realitysync-titiler \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format='value(status.url)'

echo ""
echo "To customise the CORS origins, update the API service:"
echo "  gcloud run services update realitysync-api \\"
echo "    --region ${REGION} \\"
echo "    --update-env-vars CORS_ORIGINS=https://your-frontend-url.run.app"

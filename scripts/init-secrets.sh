#!/usr/bin/env bash
set -euo pipefail

# Initialize Secret Manager secrets for a fresh deployment.
# Run once after `terraform apply` creates the secret resources.

PROJECT_ID="${1:-$(gcloud config get project)}"

echo "Initializing secrets in project: $PROJECT_ID"

create_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "$name" --project="$PROJECT_ID" &>/dev/null; then
    echo "Secret $name already exists, adding new version..."
    echo -n "$value" | gcloud secrets versions add "$name" --data-file=-
  else
    echo "Secret $name not found, create via Terraform first."
  fi
}

# Generate random secrets if not provided via env vars
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 24)}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(openssl rand -base64 24)}"
API_KEY="${API_KEY:-$(openssl rand -base64 24)}"

create_secret "realitysync-db-password" "$DB_PASSWORD"
create_secret "realitysync-app-secret-key" "$APP_SECRET_KEY"
create_secret "realitysync-api-key" "$API_KEY"

echo "Done. Secrets initialized in Secret Manager."

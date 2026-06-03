# ---------------------------------------------------------------------------
# Secret Manager secrets
# In production, initial secret values are set via `scripts/init-secrets.sh`
# or during CI first-deploy. Variables that are empty at plan time will be
# generated with `random_password` for local/dev environments.
# ---------------------------------------------------------------------------

resource "random_password" "db_password" {
  count  = var.db_password == "" ? 1 : 0
  length = 32
}

resource "random_password" "app_secret_key" {
  count  = var.app_secret_key == "" ? 1 : 0
  length = 32
}

resource "random_password" "api_key" {
  count  = var.api_key == "" ? 1 : 0
  length = 32
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "realitysync-db-password"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password != "" ? var.db_password : random_password.db_password[0].result
}

resource "google_secret_manager_secret_iam_member" "db_password_accessor" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret" "planet_api_key" {
  secret_id = "realitysync-planet-api-key"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "planet_api_key" {
  secret      = google_secret_manager_secret.planet_api_key.id
  secret_data = var.planet_api_key != "" ? var.planet_api_key : ""
}

resource "google_secret_manager_secret_iam_member" "planet_api_key_accessor" {
  secret_id = google_secret_manager_secret.planet_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret" "app_secret_key" {
  secret_id = "realitysync-app-secret-key"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "app_secret_key" {
  secret      = google_secret_manager_secret.app_secret_key.id
  secret_data = var.app_secret_key != "" ? var.app_secret_key : random_password.app_secret_key[0].result
}

resource "google_secret_manager_secret_iam_member" "app_secret_key_accessor" {
  secret_id = google_secret_manager_secret.app_secret_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret" "api_key" {
  secret_id = "realitysync-api-key"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "api_key" {
  secret      = google_secret_manager_secret.api_key.id
  secret_data = var.api_key != "" ? var.api_key : random_password.api_key[0].result
}

resource "google_secret_manager_secret_iam_member" "api_key_accessor" {
  secret_id = google_secret_manager_secret.api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret" "sentry_dsn" {
  secret_id = "realitysync-sentry-dsn"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "sentry_dsn" {
  secret      = google_secret_manager_secret.sentry_dsn.id
  secret_data = var.sentry_dsn != "" ? var.sentry_dsn : ""
}

resource "google_secret_manager_secret_iam_member" "sentry_dsn_accessor" {
  secret_id = google_secret_manager_secret.sentry_dsn.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

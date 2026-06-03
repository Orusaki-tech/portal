resource "google_service_account" "cloud_run" {
  account_id   = "realitysync-api-sa"
  display_name = "RealitySync API Service Account"
}

resource "google_project_iam_member" "cloud_sql_client" {
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "pubsub_publisher" {
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "pubsub_subscriber" {
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "storage_object_admin" {
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

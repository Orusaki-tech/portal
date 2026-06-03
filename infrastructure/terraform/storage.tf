resource "random_id" "suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "exports" {
  name                        = "realitysync-exports-${random_id.suffix.hex}"
  location                    = var.gcp_region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "tfstate" {
  name                        = "realitysync-tfstate-${random_id.suffix.hex}"
  location                    = var.gcp_region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket_iam_member" "tfstate_terraform_sa" {
  bucket = google_storage_bucket.tfstate.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:realitysync-terraform@${var.gcp_project_id}.iam.gserviceaccount.com"
}

resource "google_project_service" "storage" {
  service = "storage.googleapis.com"
}

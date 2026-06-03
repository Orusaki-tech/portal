resource "google_pubsub_topic" "edge_validation_results" {
  name = "edge-validation-results"
}

resource "google_pubsub_subscription" "edge_validation_results" {
  name  = "edge-validation-results-sub"
  topic = google_pubsub_topic.edge_validation_results.id
}

resource "google_pubsub_topic" "export_requests" {
  name = "export-requests"
}

resource "google_pubsub_subscription" "export_requests" {
  name  = "export-requests-sub"
  topic = google_pubsub_topic.export_requests.id
}

resource "google_pubsub_topic" "imagery_uploads" {
  name = "imagery-uploads"
}

resource "google_pubsub_subscription" "imagery_uploads" {
  name  = "imagery-uploads-sub"
  topic = google_pubsub_topic.imagery_uploads.id
}

resource "google_project_service" "pubsub" {
  service = "pubsub.googleapis.com"
}

output "api_url" {
  description = "API service URL"
  value       = google_cloud_run_v2_service.api.uri
}

output "cloud_run_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.api.name
}

output "gcs_exports_bucket" {
  description = "GCS bucket for exports"
  value       = google_storage_bucket.exports.name
}

output "cdn_url" {
  description = "CDN URL for exports"
  value       = "https://${google_compute_global_address.lb.address}"
}

output "db_private_ip" {
  description = "Cloud SQL private IP address"
  value       = google_sql_database_instance.postgis.private_ip_address
}

output "pubsub_topics" {
  description = "Pub/Sub topic names"
  value = {
    edge_validation_results = google_pubsub_topic.edge_validation_results.name
    export_requests         = google_pubsub_topic.export_requests.name
    imagery_uploads         = google_pubsub_topic.imagery_uploads.name
  }
}

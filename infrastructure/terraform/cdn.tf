resource "google_compute_global_address" "lb" {
  name = "realitysync-lb-ip"
}

resource "google_compute_backend_bucket" "exports" {
  name        = "realitysync-exports-backend"
  description = "Serves exported files from GCS"
  bucket_name = google_storage_bucket.exports.name
  enable_cdn  = true
}

resource "google_compute_backend_service" "api" {
  name    = "realitysync-api-backend"
  port_name = "http"

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "realitysync-api-neg"
  region                = var.gcp_region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_url_map" "main" {
  name            = "realitysync-url-map"
  default_service = google_compute_backend_service.api.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "all"
  }

  path_matcher {
    name            = "all"
    default_service = google_compute_backend_service.api.id

    path_rule {
      paths   = ["/exports/*"]
      service = google_compute_backend_bucket.exports.id
    }
  }
}

resource "google_compute_target_https_proxy" "main" {
  name    = "realitysync-https-proxy"
  url_map = google_compute_url_map.main.id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb.id]
}

resource "google_compute_managed_ssl_certificate" "lb" {
  name = "realitysync-lb-cert"
  managed {
    domains = [var.domain_name]
  }
}

resource "google_compute_global_forwarding_rule" "https" {
  name       = "realitysync-https-forwarding-rule"
  target     = google_compute_target_https_proxy.main.id
  port_range = "443"
  ip_address = google_compute_global_address.lb.address
}

resource "google_project_service" "compute" {
  service = "compute.googleapis.com"
}

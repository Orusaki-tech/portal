resource "google_cloud_run_v2_service" "api" {
  name     = "realitysync-api"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = "us-central1-docker.pkg.dev/${var.gcp_project_id}/realitysync/realitysync-api:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "DB_HOST"
        value = google_sql_database_instance.postgis.private_ip_address
      }
      env {
        name  = "DB_PORT"
        value = "5432"
      }
      env {
        name  = "DB_NAME"
        value = google_sql_database.realitysync.name
      }
      env {
        name  = "DB_USER"
        value = google_sql_user.realitysync.name
      }
      env {
        name  = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "PLANET_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.planet_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "APP_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.app_secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "STAC_API_URL"
        value = "https://stac.example.com"
      }
      env {
        name  = "API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "SENTRY_DSN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.sentry_dsn.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        timeout_seconds       = 240
        period_seconds        = 240
        failure_threshold     = 1
        tcp_socket {
          port = 8080
        }
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 10
        period_seconds        = 30
      }
    }

    service_account = google_service_account.cloud_run.email

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.subnet.id
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_version.planet_api_key,
    google_secret_manager_secret_version.app_secret_key,
    google_secret_manager_secret_version.api_key,
  ]
}

resource "google_project_service" "run" {
  service = "run.googleapis.com"
}

resource "google_project_service" "secretmanager" {
  service = "secretmanager.googleapis.com"
}


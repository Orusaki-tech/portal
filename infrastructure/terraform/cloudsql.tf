resource "google_sql_database_instance" "postgis" {
  name             = "realitysync-postgis"
  database_version = "POSTGRES_16"
  region           = var.gcp_region

  settings {
    tier              = "db-custom-1-3840"
    disk_size         = 10
    disk_type         = "PD_SSD"
    disk_autoresize   = true
    availability_type = "ZONAL"

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    database_flags {
      name  = "cloudsql.enable_pgaudit"
      value = "off"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "realitysync" {
  name     = "realitysync"
  instance = google_sql_database_instance.postgis.name
  charset  = "UTF8"
  collation = "en_US.UTF8"
}

resource "google_sql_user" "realitysync" {
  name     = "realitysync"
  instance = google_sql_database_instance.postgis.name
  password = var.db_password
}

resource "google_project_service" "sqladmin" {
  service = "sqladmin.googleapis.com"
}

resource "google_project_service" "cloudresourcemanager" {
  service = "cloudresourcemanager.googleapis.com"
}

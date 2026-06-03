resource "google_compute_network" "vpc" {
  name                    = "realitysync-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "realitysync-subnet"
  network       = google_compute_network.vpc.id
  region        = var.gcp_region
  ip_cidr_range = "10.0.0.0/24"

  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  name    = "realitysync-router"
  region  = var.gcp_region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "realitysync-nat"
  router                            = google_compute_router.router.name
  region                            = var.gcp_region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

resource "google_compute_firewall" "cloud_run_to_sql" {
  name    = "realitysync-allow-cloud-run-to-sql"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  source_tags = ["cloud-run"]
  target_tags = ["cloud-sql"]
}

resource "google_compute_firewall" "allow_vpc_connector" {
  name    = "realitysync-allow-vpc-connector"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["443", "80"]
  }

  source_ranges = ["10.0.0.0/24"]
}

resource "google_compute_firewall" "deny_all_inbound" {
  name    = "realitysync-deny-all-inbound"
  network = google_compute_network.vpc.name
  priority = 65534

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  direction     = "INGRESS"
}

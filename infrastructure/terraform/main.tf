terraform {
  required_version = "~> 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "gcs" {
    bucket = "realitysync-tfstate-111963419931"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# Mamaflow — GCP Infrastructure
# Phase 0: Project creation, Gmail API enablement, OAuth client
#
# Mirrors the SalesQ broker/shim pattern: infrastructure is reproducible,
# version-controlled, and credential-free in source.
#
# Prerequisites (run once, manually, before terraform apply):
#   gcloud auth login
#   gcloud auth application-default login
#
# Usage:
#   cd infra
#   terraform init
#   terraform plan
#   terraform apply

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  # Authentication comes from Application Default Credentials
  # (gcloud auth application-default login). No keys in source.
}

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
# GCP project IDs are GLOBALLY unique. If "mamaflow-prod" is taken,
# change project_id in terraform.tfvars to something like "mamaflow-prod-akhil".
resource "google_project" "mamaflow" {
  name            = var.project_name
  project_id      = var.project_id
  billing_account = var.billing_account_id

  # Prevents accidental deletion of the project via terraform destroy
  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------
# Gmail API for reading email. IAM and Secret Manager for the broker pattern
# (Phase 1+), included now so the foundation is in place.
resource "google_project_service" "apis" {
  for_each = toset([
    "gmail.googleapis.com",          # Read family emails
    "iam.googleapis.com",            # Service accounts (broker pattern)
    "secretmanager.googleapis.com",  # OAuth token storage (Phase 1)
    "cloudresourcemanager.googleapis.com",
  ])

  project = google_project.mamaflow.project_id
  service = each.value

  # Keep APIs enabled even if this resource is removed from config
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
output "project_id" {
  value       = google_project.mamaflow.project_id
  description = "The Mamaflow GCP project ID"
}

output "enabled_apis" {
  value       = [for s in google_project_service.apis : s.service]
  description = "APIs enabled on the project"
}

output "next_steps" {
  value = <<-EOT

    ✅ Project created and APIs enabled.

    MANUAL STEPS REMAINING (Google requires these via console):

    1. OAuth consent screen:
       https://console.cloud.google.com/apis/credentials/consent?project=${google_project.mamaflow.project_id}
       - User type: External
       - App name: Mamaflow
       - Add your OptimaCore Gmail as a test user
       - Scopes: add gmail.readonly

    2. Create OAuth Client ID:
       https://console.cloud.google.com/apis/credentials?project=${google_project.mamaflow.project_id}
       - Create Credentials -> OAuth client ID
       - Application type: Web application
       - Authorized redirect URI: http://localhost:8000/api/v1/auth/google/callback
       - Copy the Client ID and Client Secret into your .env file

  EOT
  description = "Manual steps Terraform cannot automate"
}

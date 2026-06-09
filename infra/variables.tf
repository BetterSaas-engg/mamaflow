# Mamaflow — Terraform Variables

variable "project_id" {
  type        = string
  description = "GCP project ID (globally unique). Default: mamaflow-prod"
  default     = "mamaflow-prod"
}

variable "project_name" {
  type        = string
  description = "Human-readable project name"
  default     = "Mamaflow"
}

variable "billing_account_id" {
  type        = string
  description = "GCP billing account ID to link to the project"
  # No default — provided in terraform.tfvars (not committed to git)
  sensitive   = true
}

variable "bootstrap_project_id" {
  type        = string
  description = "An existing GCP project used for quota/billing API calls during initial project creation"
}

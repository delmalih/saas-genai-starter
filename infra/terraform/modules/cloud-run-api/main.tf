variable "project_id" { type = string }
variable "region" { type = string }
variable "service_name" { type = string }
variable "image" { type = string }
variable "service_account_email" { type = string }
variable "env" {
  type        = map(string)
  description = "Plain environment variables"
}
variable "secret_env" {
  type        = map(string)
  description = "Env var name -> Secret Manager secret id (latest version)"
}

resource "google_cloud_run_v2_service" "this" {
  project  = var.project_id
  location = var.region
  name     = var.service_name
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = var.service_account_email
    max_instance_request_concurrency = 40
    timeout                          = "300s" # SSE chat streams fit comfortably

    scaling {
      min_instance_count = 0 # scale-to-zero: the $0 requirement
      max_instance_count = 2
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true # CPU only billed while serving requests
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
      }
    }
  }
}

# Public API — application-level auth (JWT) protects every business route,
# and /internal/jobs verifies Cloud Tasks OIDC tokens itself.
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "uri" { value = google_cloud_run_v2_service.this.uri }
output "name" { value = google_cloud_run_v2_service.this.name }

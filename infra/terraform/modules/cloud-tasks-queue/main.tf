variable "project_id" { type = string }
variable "region" { type = string }
variable "name" { type = string }

resource "google_cloud_tasks_queue" "this" {
  project  = var.project_id
  location = var.region
  name     = var.name

  retry_config {
    max_attempts  = 3
    min_backoff   = "5s"
    max_backoff   = "60s"
    max_doublings = 3
  }

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 10
  }
}

output "queue_path" { value = google_cloud_tasks_queue.this.id }

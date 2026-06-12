variable "project_id" { type = string }
variable "name" { type = string }
variable "location" { type = string }

resource "google_storage_bucket" "this" {
  project                     = var.project_id
  name                        = var.name
  location                    = var.location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true # demo environment — destroy must be clean
}

output "name" { value = google_storage_bucket.this.name }

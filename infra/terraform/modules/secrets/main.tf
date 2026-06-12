variable "project_id" { type = string }
variable "secret_ids" { type = list(string) }
variable "accessor_member" {
  type        = string
  description = "IAM member granted secretAccessor on every secret"
}

resource "google_secret_manager_secret" "this" {
  for_each  = toset(var.secret_ids)
  project   = var.project_id
  secret_id = each.key

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = google_secret_manager_secret.this
  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = var.accessor_member
}

output "secret_ids" { value = [for s in google_secret_manager_secret.this : s.secret_id] }

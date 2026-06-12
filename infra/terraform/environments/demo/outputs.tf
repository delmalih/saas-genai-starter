output "api_url" {
  value       = module.api.uri
  description = "Cloud Run URL — set as NEXT_PUBLIC_API_URL on Vercel"
}

output "artifact_repository" {
  value = module.registry.repository_url
}

output "documents_bucket" {
  value = module.documents_bucket.name
}

output "jobs_queue" {
  value = module.jobs_queue.queue_path
}

output "wif_provider" {
  value       = module.wif.provider_name
  description = "google-github-actions/auth workload_identity_provider"
}

output "deployer_service_account" {
  value = module.wif.deployer_email
}

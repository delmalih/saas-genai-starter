variable "project_id" {
  type    = string
  default = "saas-genai-starter-demo"
}

variable "region" {
  type    = string
  default = "us-east1"
}

variable "bucket_location" {
  type    = string
  default = "US-EAST1" # always-free GCS tier is US regions only
}

variable "api_service_name" {
  type    = string
  default = "api"
}

variable "api_image" {
  type        = string
  description = "Full image reference deployed to Cloud Run"
}

variable "web_base_url" {
  type    = string
  default = "https://saas-genai-starter-web.vercel.app"
}

variable "admin_emails" {
  type    = string
  default = "da.elmalih@gmail.com"
}

variable "email_from" {
  type    = string
  default = "SaaS GenAI Starter <noreply@davidelmalih.com>"
}

variable "github_repository" {
  type    = string
  default = "delmalih/saas-genai-starter"
}

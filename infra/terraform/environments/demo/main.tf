terraform {
  required_version = ">= 1.3"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    bucket = "saas-genai-starter-demo-tfstate"
    prefix = "demo"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  # Cloud Run deterministic URL — lets the service know its own public URL
  # (Cloud Tasks audience + push target) without a circular reference.
  api_url = "https://${var.api_service_name}-${data.google_project.this.number}.${var.region}.run.app"
}

# --- APIs ----------------------------------------------------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudtasks.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# --- Service accounts -----------------------------------------------------------

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "api-runtime"
  display_name = "API runtime (Cloud Run)"
}

resource "google_service_account" "jobs_invoker" {
  project      = var.project_id
  account_id   = "jobs-invoker"
  display_name = "Cloud Tasks OIDC identity for /internal/jobs"
}

# The API enqueues tasks and lets Cloud Tasks mint OIDC tokens as the invoker.
resource "google_project_iam_member" "api_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_service_account_iam_member" "api_acts_as_invoker" {
  service_account_id = google_service_account.jobs_invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# --- Modules ---------------------------------------------------------------------

module "registry" {
  source        = "../../modules/artifact-registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "saas-genai-starter"
  depends_on    = [google_project_service.apis]
}

module "documents_bucket" {
  source     = "../../modules/gcs-bucket"
  project_id = var.project_id
  name       = "${var.project_id}-documents"
  location   = var.bucket_location
  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "api_bucket_access" {
  bucket = module.documents_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

module "secrets" {
  source          = "../../modules/secrets"
  project_id      = var.project_id
  secret_ids      = ["database-url", "redis-url", "secret-encryption-key", "resend-api-key"]
  accessor_member = "serviceAccount:${google_service_account.api.email}"
  depends_on      = [google_project_service.apis]
}

module "jobs_queue" {
  source     = "../../modules/cloud-tasks-queue"
  project_id = var.project_id
  region     = var.region
  name       = "jobs"
  depends_on = [google_project_service.apis]
}

module "api" {
  source                = "../../modules/cloud-run-api"
  project_id            = var.project_id
  region                = var.region
  service_name          = var.api_service_name
  image                 = var.api_image
  service_account_email = google_service_account.api.email

  env = {
    APP_ENV                    = "production"
    QUEUE_DRIVER               = "cloud_tasks"
    STORAGE_BACKEND            = "gcs"
    GCS_BUCKET                 = module.documents_bucket.name
    WEB_BASE_URL               = var.web_base_url
    AUTH_JWKS_URL              = "${var.web_base_url}/api/auth/jwks"
    AUTH_JWT_ISSUER            = var.web_base_url
    AUTH_JWT_AUDIENCE          = var.web_base_url
    ADMIN_EMAILS               = var.admin_emails
    EMAIL_FROM                 = var.email_from
    CLOUD_TASKS_QUEUE          = module.jobs_queue.queue_path
    INTERNAL_JOBS_BASE_URL     = local.api_url
    JOBS_SERVICE_ACCOUNT_EMAIL = google_service_account.jobs_invoker.email
  }

  secret_env = {
    DATABASE_URL          = "database-url"
    REDIS_URL             = "redis-url"
    SECRET_ENCRYPTION_KEY = "secret-encryption-key"
    RESEND_API_KEY        = "resend-api-key"
  }

  depends_on = [module.secrets, google_project_service.apis]
}

# --- CI/CD identity ---------------------------------------------------------------

module "wif" {
  source                      = "../../modules/github-wif"
  project_id                  = var.project_id
  repository                  = var.github_repository
  deployer_service_account_id = "github-deployer"
  depends_on                  = [google_project_service.apis]
}

resource "google_project_iam_member" "deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${module.wif.deployer_email}"
}

resource "google_project_iam_member" "deployer_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${module.wif.deployer_email}"
}

# CD deploys revisions running as the API service account.
resource "google_service_account_iam_member" "deployer_acts_as_api" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${module.wif.deployer_email}"
}

# CD runs alembic against Neon — it reads the connection string from SM.
resource "google_secret_manager_secret_iam_member" "deployer_db_url" {
  project   = var.project_id
  secret_id = "database-url"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${module.wif.deployer_email}"
  depends_on = [module.secrets]
}

# infrastructure/opentofu/main.tf
# OpenTofu (MPL 2.0 Terraform replacement) — Trancendos Docker infrastructure
# Manages Docker Compose stacks and service configurations as code

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
  # State stored locally — no remote state backend (zero-cost)
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

# ─── Variables ────────────────────────────────────────────────
variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "traefik_domain" {
  description = "Primary domain for Traefik routing"
  type        = string
  default     = "trancendos.com"
}

variable "worker_image_tag" {
  description = "Docker image tag for Trancendos workers"
  type        = string
  default     = "latest"
}

# ─── Networks ─────────────────────────────────────────────────
resource "docker_network" "trancendos_internal" {
  name   = "trancendos-internal"
  driver = "bridge"

  labels {
    label = "com.trancendos.managed-by"
    value = "opentofu"
  }
}

resource "docker_network" "trancendos_public" {
  name   = "trancendos-public"
  driver = "bridge"

  labels {
    label = "com.trancendos.managed-by"
    value = "opentofu"
  }
}

# ─── Volumes ──────────────────────────────────────────────────
resource "docker_volume" "victoria_metrics" {
  name = "victoria-metrics-data"
}

resource "docker_volume" "grafana" {
  name = "grafana-data"
}

resource "docker_volume" "loki" {
  name = "loki-data"
}

resource "docker_volume" "openbao_data" {
  name = "openbao-data"
}

resource "docker_volume" "langfuse_db" {
  name = "langfuse-db-data"
}

# ─── Outputs ──────────────────────────────────────────────────
output "internal_network_id" {
  description = "Internal Docker network ID"
  value       = docker_network.trancendos_internal.id
}

output "public_network_id" {
  description = "Public Docker network ID"
  value       = docker_network.trancendos_public.id
}

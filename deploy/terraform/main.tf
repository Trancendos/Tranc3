# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — Terraform Root Module
# Oracle Cloud Always Free Tier — Zero-Cost Infrastructure
# ──────────────────────────────────────────────────────────────
# This module provisions the complete Tranc3 infrastructure stack
# using only Oracle Cloud Always Free resources:
#   - 4 OCPU Arm (A1 Flex) + 2 Micro AMD compute
#   - 200 GB Block Volume total
#   - 20 GB Object Storage
#   - 10 TB outbound/month
#   - 50K API requests/month
#   - 150 Vault secrets, 20 HSM key versions
# ──────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 4.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0.0"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.4.0"
    }
  }

  # ── Remote Backend (uncomment for production) ─────────────
  # backend "s3" {
  #   bucket                      = "tranc3-terraform-state"
  #   key                         = "tranc3/terraform.tfstate"
  #   region                      = "us-phoenix-1"
  #   endpoint                    = "https://<namespace>.compat.objectstorage.us-phoenix-1.oc1.oraclecloud.com"
  #   shared_credentials_file     = "~/.oci/s3_credentials"
  #   skip_region_validation      = true
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   force_path_style            = true
  # }
}

# ── OCI Provider ─────────────────────────────────────────────

provider "oci" {
  tenancy_ocid     = var.oci_tenancy_ocid
  user_ocid        = var.oci_user_ocid
  fingerprint      = var.oci_fingerprint
  private_key_path = var.oci_private_key_path
  private_key      = var.oci_private_key
  region           = var.oci_region
}

# ── Cloudflare Provider (R2 storage fallback) ────────────────

provider "cloudflare" {
  api_token = var.cloudflare_r2_access_key_id != "" ? var.cloudflare_r2_access_key_id : null
}

# ── Data Sources ─────────────────────────────────────────────

data "oci_identity_availability_domain" "ad" {
  compartment_id = var.oci_tenancy_ocid
  ad_number      = 1
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.oci_tenancy_ocid
}

# ── Free-Tier Validation Locals ──────────────────────────────

locals {
  # Calculate total resource consumption
  total_ocpus = var.nanoservice_ocpus + var.ceph_node_ocpus + var.k3s_edge_ocpus
  total_memory = var.nanoservice_memory_gbs + var.ceph_node_memory_gbs + var.k3s_edge_memory_gbs
  total_boot_volume = var.nanoservice_boot_volume_gbs + var.ceph_boot_volume_gbs + var.k3s_boot_volume_gbs

  # Free-tier constraint checks
  ocpu_within_limit      = local.total_ocpus <= var.total_ocpu_limit
  memory_within_limit    = local.total_memory <= var.total_memory_limit_gb
  boot_volume_within_limit = local.total_boot_volume <= var.total_block_volume_limit_gb

  # Common tags
  common_tags = merge(
    {
      "tranc3.io/managed-by"  = "terraform"
      "tranc3.io/environment" = var.environment
      "tranc3.io/system-mode" = var.system_mode
      "tranc3.io/part-of"     = "tranc3-ecosystem"
    },
    var.project_tags
  )

  # Instance names following PID/AID/SID/NID taxonomy
  nanoservice_name = "aid-nanoservice-${var.environment}"
  ceph_node_name   = "aid-ceph-node-${var.environment}"
  k3s_edge_name    = "aid-k3s-edge-${var.environment}"

  # Storage bucket names
  hot_bucket     = "${var.bucket_name_prefix}-hot-${var.environment}"
  cold_bucket    = "${var.bucket_name_prefix}-cold-${var.environment}"
  archive_bucket = "${var.bucket_name_prefix}-archive-${var.environment}"

  # Storage fallback chain configuration
  fallback_chain = [
    { provider = "oci", priority = 1, capacity_limit_gb = 20, crush_aware = true },
    { provider = "cloudflare_r2", priority = 2, capacity_limit_gb = 10, crush_aware = false },
    { provider = "minio", priority = 3, capacity_limit_gb = 100, crush_aware = true },
    { provider = "gcp", priority = 4, capacity_limit_gb = 5, crush_aware = false },
    { provider = "azure", priority = 5, capacity_limit_gb = 5, crush_aware = false },
    { provider = "aws", priority = 6, capacity_limit_gb = 5, crush_aware = false },
  ]

  # CRUSH configuration
  crush_config = {
    failure_domain = var.crush_failure_domain
    default_rule   = var.crush_default_rule
    rules = {
      hybrid = {
        type       = "replicated"
        min_replicas = 1
        failure_domain = var.crush_failure_domain
        osd_weights = {
          "osd.0" = 1.0
          "osd.1" = 0.8
        }
      }
      capacity-first = {
        type       = "replicated"
        min_replicas = 1
        failure_domain = "row"
        osd_weights = {
          "osd.0" = 1.0
          "osd.1" = 1.0
        }
      }
      latency-first = {
        type       = "replicated"
        min_replicas = 1
        failure_domain = "host"
        osd_weights = {
          "osd.0" = 1.0
          "osd.1" = 0.5
        }
      }
    }
  }

  # Idle defense configuration
  idle_defense = {
    enabled              = var.idle_defense_enabled
    burst_cron           = var.idle_defense_burst_cron
    burst_duration_sec   = var.idle_defense_burst_duration_seconds
    cpu_target_percent   = var.idle_defense_cpu_target_percent
  }

  # Network enablement flags
  enable_nat_gateway      = var.enable_nat_gateway
  enable_service_gateway  = var.enable_service_gateway
  enable_internet_gateway = var.enable_internet_gateway
}

# ── Free-Tier Constraint Enforcement ─────────────────────────

# These preconditions ensure we never exceed Always Free limits

check "ocpu_limit" {
  assert {
    condition     = local.total_ocpus <= var.total_ocpu_limit
    error_message = "Total OCPUs (${local.total_ocpus}) exceeds Always Free limit (${var.total_ocpu_limit}). Reduce instance OCPUs."
  }
}

check "memory_limit" {
  assert {
    condition     = local.total_memory <= var.total_memory_limit_gb
    error_message = "Total memory (${local.total_memory} GB) exceeds Always Free limit (${var.total_memory_limit_gb} GB). Reduce instance memory."
  }
}

check "boot_volume_limit" {
  assert {
    condition     = local.total_boot_volume <= var.total_block_volume_limit_gb
    error_message = "Total boot volume (${local.total_boot_volume} GB) exceeds Always Free block volume limit (${var.total_block_volume_limit_gb} GB). Reduce boot volume sizes."
  }
}

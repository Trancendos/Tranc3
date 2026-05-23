# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — Terraform Variables
# Oracle Cloud Always Free Tier — Zero-Cost Infrastructure
# ──────────────────────────────────────────────────────────────
# All defaults are within OCI Always Free limits.
# Free-tier validation preconditions enforce zero-cost mandate.
# ──────────────────────────────────────────────────────────────

# ── OCI Authentication ──────────────────────────────────────

variable "oci_tenancy_ocid" {
  description = "OCID of the OCI tenancy"
  type        = string
  sensitive   = true
}

variable "oci_user_ocid" {
  description = "OCID of the OCI user"
  type        = string
  sensitive   = true
}

variable "oci_fingerprint" {
  description = "Fingerprint of the OCI API key"
  type        = string
}

variable "oci_private_key_path" {
  description = "Path to the OCI API private key"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "oci_private_key" {
  description = "OCI API private key content (alternative to private_key_path)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oci_region" {
  description = "OCI home region — must be set to your tenancy's home region"
  type        = string
  default     = "us-phoenix-1"
}

variable "oci_compartment_ocid" {
  description = "OCID of the compartment to deploy resources into"
  type        = string
}

# ── Compute Configuration ────────────────────────────────────

variable "nanoservice_shape" {
  description = "OCI shape for the nanoservice instance (A1 Flex = Always Free ARM)"
  type        = string
  default     = "VM.Standard.A1.Flex"

  validation {
    condition     = contains(["VM.Standard.A1.Flex", "VM.Standard.E2.1.Micro"], var.nanoservice_shape)
    error_message = "Nanoservice shape must be an Always Free eligible shape (VM.Standard.A1.Flex or VM.Standard.E2.1.Micro)."
  }
}

variable "nanoservice_ocpus" {
  description = "Number of OCPUs for the nanoservice instance (max 4 total across all A1 instances on free tier)"
  type        = number
  default     = 1

  validation {
    condition     = var.nanoservice_ocpus >= 1 && var.nanoservice_ocpus <= 4
    error_message = "Nanoservice OCPUs must be between 1 and 4 (Always Free limit)."
  }
}

variable "nanoservice_memory_gbs" {
  description = "Memory in GBs for the nanoservice instance (max 24 GB total across all A1 instances)"
  type        = number
  default     = 6

  validation {
    condition     = var.nanoservice_memory_gbs >= 1 && var.nanoservice_memory_gbs <= 24
    error_message = "Nanoservice memory must be between 1 and 24 GB (Always Free limit)."
  }
}

variable "ceph_node_shape" {
  description = "OCI shape for the Ceph/MicroCeph node"
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "ceph_node_ocpus" {
  description = "Number of OCPUs for the Ceph node"
  type        = number
  default     = 2

  validation {
    condition     = var.ceph_node_ocpus >= 1 && var.ceph_node_ocpus <= 4
    error_message = "Ceph node OCPUs must be between 1 and 4."
  }
}

variable "ceph_node_memory_gbs" {
  description = "Memory in GBs for the Ceph node"
  type        = number
  default     = 12

  validation {
    condition     = var.ceph_node_memory_gbs >= 1 && var.ceph_node_memory_gbs <= 24
    error_message = "Ceph node memory must be between 1 and 24 GB."
  }
}

variable "k3s_edge_shape" {
  description = "OCI shape for the K3s edge node"
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "k3s_edge_ocpus" {
  description = "Number of OCPUs for the K3s edge node"
  type        = number
  default     = 1

  validation {
    condition     = var.k3s_edge_ocpus >= 1 && var.k3s_edge_ocpus <= 4
    error_message = "K3s edge OCPUs must be between 1 and 4."
  }
}

variable "k3s_edge_memory_gbs" {
  description = "Memory in GBs for the K3s edge node"
  type        = number
  default     = 6

  validation {
    condition     = var.k3s_edge_memory_gbs >= 1 && var.k3s_edge_memory_gbs <= 24
    error_message = "K3s edge memory must be between 1 and 24 GB."
  }
}

# ── Free-Tier Quota Guards ───────────────────────────────────

variable "total_ocpu_limit" {
  description = "Maximum total OCPUs across all A1 instances (Always Free = 4)"
  type        = number
  default     = 4
}

variable "total_memory_limit_gb" {
  description = "Maximum total memory in GBs across all A1 instances (Always Free = 24)"
  type        = number
  default     = 24
}

variable "total_block_volume_limit_gb" {
  description = "Maximum total block volume in GBs (Always Free = 200)"
  type        = number
  default     = 200
}

variable "object_storage_limit_gb" {
  description = "Maximum object storage in GBs (Always Free = 20)"
  type        = number
  default     = 20
}

variable "api_request_limit_monthly" {
  description = "Maximum monthly API requests (Always Free = 50000)"
  type        = number
  default     = 50000
}

# ── Network Configuration ────────────────────────────────────

variable "vcn_cidr" {
  description = "CIDR block for the Tranc3 VCN"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vcn_cidr))
    error_message = "VCN CIDR must be a valid IPv4 CIDR block."
  }
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet (nanoservice, K3s)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet (nanoservice internal)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "ceph_subnet_cidr" {
  description = "CIDR block for the Ceph cluster network"
  type        = string
  default     = "10.0.3.0/24"
}

variable "vcn_dns_label" {
  description = "DNS label for the VCN"
  type        = string
  default     = "tranc3"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{0,14}$", var.vcn_dns_label))
    error_message = "VCN DNS label must start with a letter and be 1-15 alphanumeric characters."
  }
}

# ── Boot Volume Configuration ────────────────────────────────

variable "nanoservice_boot_volume_gbs" {
  description = "Boot volume size in GBs for nanoservice instance"
  type        = number
  default     = 47

  validation {
    condition     = var.nanoservice_boot_volume_gbs >= 47 && var.nanoservice_boot_volume_gbs <= 200
    error_message = "Boot volume must be between 47 and 200 GB."
  }
}

variable "ceph_boot_volume_gbs" {
  description = "Boot volume size in GBs for Ceph node"
  type        = number
  default     = 47
}

variable "k3s_boot_volume_gbs" {
  description = "Boot volume size in GBs for K3s edge node"
  type        = number
  default     = 47
}

# ── Storage Configuration ────────────────────────────────────

variable "object_storage_namespace" {
  description = "OCI Object Storage namespace (auto-discovered if empty)"
  type        = string
  default     = ""
}

variable "bucket_name_prefix" {
  description = "Prefix for OCI Object Storage bucket names"
  type        = string
  default     = "tranc3"
}

variable "enable_lifecycle_policies" {
  description = "Enable object storage lifecycle policies for temperature tiering"
  type        = bool
  default     = true
}

variable "hot_to_warm_days" {
  description = "Days before hot objects transition to warm"
  type        = number
  default     = 7
}

variable "warm_to_cold_days" {
  description = "Days before warm objects transition to cold"
  type        = number
  default     = 30
}

variable "cold_to_archive_days" {
  description = "Days before cold objects transition to archive"
  type        = number
  default     = 90
}

# ── Cloudflare R2 Configuration ──────────────────────────────

variable "cloudflare_r2_account_id" {
  description = "Cloudflare account ID for R2 storage"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudflare_r2_access_key_id" {
  description = "Cloudflare R2 access key ID"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudflare_r2_secret_access_key" {
  description = "Cloudflare R2 secret access key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudflare_r2_bucket" {
  description = "Cloudflare R2 bucket name for Tranc3"
  type        = string
  default     = "tranc3-archive"
}

# ── HSM Configuration ───────────────────────────────────────

variable "hsm_provider" {
  description = "HSM provider type: softhsm2, yubihsm2, or disabled"
  type        = string
  default     = "softhsm2"

  validation {
    condition     = contains(["softhsm2", "yubihsm2", "disabled"], var.hsm_provider)
    error_message = "HSM provider must be softhsm2, yubihsm2, or disabled."
  }
}

variable "hsm_pin" {
  description = "PIN for the HSM token"
  type        = string
  default     = "tranc3-hsm-pin"
  sensitive   = true
}

variable "hsm_so_pin" {
  description = "Security Officer PIN for HSM token initialization"
  type        = string
  default     = "tranc3-hsm-so-pin"
  sensitive   = true
}

# ── CRUSH Configuration ─────────────────────────────────────

variable "crush_default_rule" {
  description = "Default CRUSH rule for data placement: hybrid, capacity-first, latency-first"
  type        = string
  default     = "hybrid"

  validation {
    condition     = contains(["hybrid", "capacity-first", "latency-first"], var.crush_default_rule)
    error_message = "CRUSH rule must be hybrid, capacity-first, or latency-first."
  }
}

variable "crush_failure_domain" {
  description = "CRUSH failure domain: host, rack, row"
  type        = string
  default     = "host"
}

# ── Idle Defense Configuration ───────────────────────────────

variable "idle_defense_enabled" {
  description = "Enable OCI idle compute reclamation defense"
  type        = bool
  default     = true
}

variable "idle_defense_burst_cron" {
  description = "Cron schedule for CPU bursts (default: every 5 minutes)"
  type        = string
  default     = "*/5 * * * *"
}

variable "idle_defense_burst_duration_seconds" {
  description = "Duration of each CPU burst in seconds"
  type        = number
  default     = 30
}

variable "idle_defense_cpu_target_percent" {
  description = "CPU utilization target during burst (percentage)"
  type        = number
  default     = 25

  validation {
    condition     = var.idle_defense_cpu_target_percent >= 10 && var.idle_defense_cpu_target_percent <= 50
    error_message = "CPU target must be between 10% and 50%."
  }
}

# ── System Mode ─────────────────────────────────────────────

variable "system_mode" {
  description = "Tranc3 system mode: true_nas (full local), hybrid (local+cloud), cloud_only"
  type        = string
  default     = "hybrid"

  validation {
    condition     = contains(["true_nas", "hybrid", "cloud_only"], var.system_mode)
    error_message = "System mode must be true_nas, hybrid, or cloud_only."
  }
}

# ── Cross-Instance IP References ─────────────────────────────
# Used to break circular dependencies in cloud-init templates.
# Defaults are placeholder IPs within the VCN CIDR range.

variable "nanoservice_private_ip" {
  description = "Private IP for the nanoservice instance (breaks cloud-init circular dependency)"
  type        = string
  default     = "10.0.2.10"
}

variable "ceph_node_private_ip" {
  description = "Private IP for the Ceph node (breaks cloud-init circular dependency)"
  type        = string
  default     = "10.0.3.10"
}

variable "k3s_edge_private_ip" {
  description = "Private IP for the K3s edge node (breaks cloud-init circular dependency)"
  type        = string
  default     = "10.0.1.10"
}

# ── SSH Configuration ────────────────────────────────────────

variable "ssh_public_key" {
  description = "SSH public key for instance access"
  type        = string
}

variable "ssh_authorized_keys" {
  description = "Additional SSH authorized keys"
  type        = list(string)
  default     = []
}

# ── Tags ─────────────────────────────────────────────────────

variable "project_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "environment" {
  description = "Environment name (production, staging, development)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be production, staging, or development."
  }
}

# ---------------------------------------------------------------------------
# Network gateway toggles (Phase 16 fix — added for terraform validate)
# ---------------------------------------------------------------------------

variable "enable_internet_gateway" {
  description = "Create an OCI Internet Gateway for the VCN (required for public subnets)"
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "Create an OCI NAT Gateway for private subnet egress"
  type        = bool
  default     = true
}

variable "enable_service_gateway" {
  description = "Create an OCI Service Gateway for private access to OCI services"
  type        = bool
  default     = true
}

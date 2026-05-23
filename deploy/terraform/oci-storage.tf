# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — OCI Storage Resources
# Object Storage, Lifecycle Policies, Vault, HSM
# Oracle Cloud Always Free Tier
# ──────────────────────────────────────────────────────────────

# ── Object Storage Buckets ───────────────────────────────────
# Three-tier storage aligned with temperature rules:
#   Hot   — Active data, frequently accessed (Standard storage tier)
#   Cold  — Infrequently accessed data (Archive storage tier)
#   Archive — Long-term retention (Archive storage tier, 90+ days)

resource "oci_objectstorage_bucket" "hot" {
  compartment_id = var.oci_compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = local.hot_bucket
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"         = "sid"
    "tranc3.io/temperature"    = "hot"
    "tranc3.io/crush-aware"    = "true"
    "tranc3.io/fallback-rank"  = "1"
    "Name"                     = "tranc3-hot"
  })

  # Free-tier precondition: ensure we don't exceed 20GB
  lifecycle {
    precondition {
      condition     = var.object_storage_limit_gb <= 20
      error_message = "Object storage limit exceeds Always Free tier (20 GB)."
    }
  }
}

resource "oci_objectstorage_bucket" "cold" {
  compartment_id = var.oci_compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = local.cold_bucket
  access_type    = "NoPublicAccess"
  storage_tier   = "Archive"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"         = "sid"
    "tranc3.io/temperature"    = "cold"
    "tranc3.io/crush-aware"    = "false"
    "tranc3.io/fallback-rank"  = "2"
    "Name"                     = "tranc3-cold"
  })
}

resource "oci_objectstorage_bucket" "archive" {
  compartment_id = var.oci_compartment_ocid
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = local.archive_bucket
  access_type    = "NoPublicAccess"
  storage_tier   = "Archive"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"         = "sid"
    "tranc3.io/temperature"    = "archive"
    "tranc3.io/crush-aware"    = "false"
    "tranc3.io/fallback-rank"  = "3"
    "Name"                     = "tranc3-archive"
  })
}

# ── Lifecycle Policies ───────────────────────────────────────
# Automatically transition objects between temperature tiers
# based on age. This implements the Tranc3 temperature rules:
#   hot → warm (7 days) → cold (30 days) → archive (90 days)
# On-access promotion: archive → cold → hot

resource "oci_objectstorage_object_lifecycle_policy" "hot" {
  count     = var.enable_lifecycle_policies ? 1 : 0
  namespace = data.oci_objectstorage_namespace.ns.namespace
  bucket    = oci_objectstorage_bucket.hot.name

  # Transition to Archive (cold) after warm period
  rules {
    action      = "ARCHIVE"
    time_amount = var.warm_to_cold_days
    time_unit   = "DAYS"
    name        = "hot-to-cold"
    is_enabled  = true
  }

  # Delete objects after 365 days (adjust per retention policy)
  rules {
    action      = "DELETE"
    time_amount = 365
    time_unit   = "DAYS"
    name        = "hot-cleanup"
    is_enabled  = true

    # Only delete objects tagged for automatic cleanup
    target      = "objects"
    object_name_filter {
      exclusion_patterns = ["permanent/*", "config/*"]
      inclusion_patterns = ["logs/*", "temp/*", "cache/*"]
    }
  }
}

resource "oci_objectstorage_object_lifecycle_policy" "cold" {
  count     = var.enable_lifecycle_policies ? 1 : 0
  namespace = data.oci_objectstorage_namespace.ns.namespace
  bucket    = oci_objectstorage_bucket.cold.name

  # Transition deeper archive after 90 days
  rules {
    action      = "ARCHIVE"
    time_amount = var.cold_to_archive_days
    time_unit   = "DAYS"
    name        = "cold-to-archive"
    is_enabled  = true
  }
}

# ── OCI Vault ────────────────────────────────────────────────
# Always Free: 150 secrets, 20 HSM key versions
# Used for: OCI credentials, R2 credentials, HSM tokens, CRUSH signing keys

resource "oci_kms_vault" "tranc3" {
  compartment_id   = var.oci_compartment_ocid
  display_name     = "tranc3-vault-${var.environment}"
  vault_type       = var.hsm_provider == "yubihsm2" ? "VIRTUAL_PRIVATE" : "DEFAULT"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "pid"
    "Name"             = "tranc3-vault"
  })
}

# ── Vault Secrets ────────────────────────────────────────────

resource "oci_vault_secret" "oci_access_key" {
  compartment_id = var.oci_compartment_ocid
  vault_id       = oci_kms_vault.tranc3.id
  key_id         = oci_kms_key.tranc3.id
  secret_name    = "tranc3-oci-access-key"
  description    = "OCI Object Storage access key for nanoservice"

  secret_content {
    content_type = "BASE64"
    content      = base64encode("placeholder-oci-access-key")
  }

  freeform_tags = local.common_tags
}

resource "oci_vault_secret" "oci_secret_key" {
  compartment_id = var.oci_compartment_ocid
  vault_id       = oci_kms_vault.tranc3.id
  key_id         = oci_kms_key.tranc3.id
  secret_name    = "tranc3-oci-secret-key"
  description    = "OCI Object Storage secret key for nanoservice"

  secret_content {
    content_type = "BASE64"
    content      = base64encode("placeholder-oci-secret-key")
  }

  freeform_tags = local.common_tags
}

resource "oci_vault_secret" "r2_access_key" {
  count          = var.cloudflare_r2_access_key_id != "" ? 1 : 0
  compartment_id = var.oci_compartment_ocid
  vault_id       = oci_kms_vault.tranc3.id
  key_id         = oci_kms_key.tranc3.id
  secret_name    = "tranc3-r2-access-key"
  description    = "Cloudflare R2 access key ID"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.cloudflare_r2_access_key_id)
  }

  freeform_tags = local.common_tags
}

resource "oci_vault_secret" "r2_secret_key" {
  count          = var.cloudflare_r2_secret_access_key != "" ? 1 : 0
  compartment_id = var.oci_compartment_ocid
  vault_id       = oci_kms_vault.tranc3.id
  key_id         = oci_kms_key.tranc3.id
  secret_name    = "tranc3-r2-secret-key"
  description    = "Cloudflare R2 secret access key"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.cloudflare_r2_secret_access_key)
  }

  freeform_tags = local.common_tags
}

resource "oci_vault_secret" "hsm_pin" {
  compartment_id = var.oci_compartment_ocid
  vault_id       = oci_kms_vault.tranc3.id
  key_id         = oci_kms_key.tranc3.id
  secret_name    = "tranc3-hsm-pin"
  description    = "PKCS#11 HSM token PIN"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.hsm_pin)
  }

  freeform_tags = local.common_tags
}

resource "oci_vault_secret" "crush_signing_key" {
  compartment_id = var.oci_compartment_ocid
  vault_id       = oci_kms_vault.tranc3.id
  key_id         = oci_kms_key.tranc3.id
  secret_name    = "tranc3-crush-signing-key"
  description    = "CRUSH map signing key for integrity verification"

  secret_content {
    content_type = "BASE64"
    content      = base64encode("placeholder-crush-signing-key")
  }

  freeform_tags = local.common_tags
}

# ── Vault Key ────────────────────────────────────────────────
# HSM-backed encryption key for data at rest

resource "oci_kms_key" "tranc3" {
  compartment_id      = var.oci_compartment_ocid
  display_name        = "tranc3-encryption-key-${var.environment}"
  management_endpoint = oci_kms_vault.tranc3.management_endpoint

  key_shape {
    algorithm = "AES"
    length    = 32
  }

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "sid"
    "Name"             = "tranc3-encryption-key"
  })
}

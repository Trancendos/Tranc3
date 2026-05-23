# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — Terraform Outputs
# ──────────────────────────────────────────────────────────────

# ── Compute Instance Outputs ─────────────────────────────────

output "nanoservice_instance_ocid" {
  description = "OCID of the nanoservice compute instance"
  value       = oci_core_instance.nanoservice.id
}

output "nanoservice_public_ip" {
  description = "Public IP address of the nanoservice instance"
  value       = oci_core_instance.nanoservice.public_ip
}

output "nanoservice_private_ip" {
  description = "Private IP address of the nanoservice instance"
  value       = oci_core_instance.nanoservice.private_ip
}

output "ceph_node_instance_ocid" {
  description = "OCID of the Ceph/MicroCeph compute instance"
  value       = oci_core_instance.ceph_node.id
}

output "ceph_node_public_ip" {
  description = "Public IP address of the Ceph node"
  value       = oci_core_instance.ceph_node.public_ip
}

output "ceph_node_private_ip" {
  description = "Private IP address of the Ceph node"
  value       = oci_core_instance.ceph_node.private_ip
}

output "k3s_edge_instance_ocid" {
  description = "OCID of the K3s edge compute instance"
  value       = oci_core_instance.k3s_edge.id
}

output "k3s_edge_public_ip" {
  description = "Public IP address of the K3s edge node"
  value       = oci_core_instance.k3s_edge.public_ip
}

output "k3s_edge_private_ip" {
  description = "Private IP address of the K3s edge node"
  value       = oci_core_instance.k3s_edge.private_ip
}

# ── Network Outputs ──────────────────────────────────────────

output "vcn_id" {
  description = "OCID of the Tranc3 VCN"
  value       = oci_core_vcn.tranc3.id
}

output "vcn_cidr" {
  description = "CIDR block of the Tranc3 VCN"
  value       = oci_core_vcn.tranc3.cidr_blocks[0]
}

output "public_subnet_id" {
  description = "OCID of the public subnet"
  value       = oci_core_subnet.public.id
}

output "private_subnet_id" {
  description = "OCID of the private subnet"
  value       = oci_core_subnet.private.id
}

output "ceph_subnet_id" {
  description = "OCID of the Ceph cluster subnet"
  value       = oci_core_subnet.ceph.id
}

output "nat_gateway_id" {
  description = "OCID of the NAT Gateway"
  value       = var.enable_nat_gateway ? oci_core_nat_gateway.tranc3[0].id : null
}

output "service_gateway_id" {
  description = "OCID of the Service Gateway"
  value       = var.enable_service_gateway ? oci_core_service_gateway.tranc3[0].id : null
}

# ── Storage Outputs ──────────────────────────────────────────

output "object_storage_namespace" {
  description = "OCI Object Storage namespace"
  value       = data.oci_objectstorage_namespace.ns.namespace
}

output "tranc3_hot_bucket" {
  description = "Name of the hot tier OCI Object Storage bucket"
  value       = oci_objectstorage_bucket.hot.name
}

output "tranc3_cold_bucket" {
  description = "Name of the cold tier OCI Object Storage bucket"
  value       = oci_objectstorage_bucket.cold.name
}

output "tranc3_archive_bucket" {
  description = "Name of the archive tier OCI Object Storage bucket"
  value       = oci_objectstorage_bucket.archive.name
}

# ── Vault Outputs ────────────────────────────────────────────

output "vault_ocid" {
  description = "OCID of the OCI KMS Vault"
  value       = oci_kms_vault.tranc3.id
}

output "vault_crypto_endpoint" {
  description = "Crypto endpoint of the OCI KMS Vault"
  value       = oci_kms_vault.tranc3.crypto_endpoint
}

# ── Free-Tier Utilization Summary ────────────────────────────

output "free_tier_utilization" {
  description = "Summary of Always Free tier resource utilization"
  value = {
    compute = {
      total_ocpus   = var.nanoservice_ocpus + var.ceph_node_ocpus + var.k3s_edge_ocpus
      limit_ocpus   = var.total_ocpu_limit
      total_memory  = var.nanoservice_memory_gbs + var.ceph_node_memory_gbs + var.k3s_edge_memory_gbs
      limit_memory  = var.total_memory_limit_gb
    }
    storage = {
      block_volume_total_gb = var.nanoservice_boot_volume_gbs + var.ceph_boot_volume_gbs + var.k3s_boot_volume_gbs
      block_volume_limit_gb = var.total_block_volume_limit_gb
      object_storage_limit  = var.object_storage_limit_gb
    }
    networking = {
      vcn_cidr       = var.vcn_cidr
      public_subnet  = var.public_subnet_cidr
      private_subnet = var.private_subnet_cidr
      ceph_subnet    = var.ceph_subnet_cidr
    }
  }
}

# ── Connection Information ───────────────────────────────────

output "nanoservice_endpoint" {
  description = "HTTP endpoint for the nanoservice"
  value       = "http://${oci_core_instance.nanoservice.public_ip}:8080"
}

output "ceph_rgw_endpoint" {
  description = "S3-compatible endpoint for Ceph RGW"
  value       = "http://${oci_core_instance.ceph_node.private_ip}:7480"
}

output "k3s_kubeconfig_hint" {
  description = "Hint for configuring kubectl for K3s"
  value       = "scp ubuntu@${oci_core_instance.k3s_edge.public_ip}:/etc/rancher/k3s/k3s.yaml ./k3s.yaml"
}

# ── System Configuration Summary ─────────────────────────────

output "system_configuration" {
  description = "Active system configuration summary"
  value = {
    system_mode         = var.system_mode
    crush_default_rule  = var.crush_default_rule
    hsm_provider        = var.hsm_provider
    idle_defense        = var.idle_defense_enabled
    region              = var.oci_region
    environment         = var.environment
  }
}

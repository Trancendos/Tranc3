# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — OCI Always Free Compute Instances
# Nanoservice, Ceph Node, K3s Edge
# Oracle Cloud Always Free Tier
# ──────────────────────────────────────────────────────────────
# A1 Flex (ARM) instances on Always Free:
#   - 4 OCPU total, 24 GB RAM total across all A1 instances
#   - Up to 200 GB block volume total
#   - 2 Micro AMD instances also available (0.48 OCPU, 1 GB RAM each)
#
# Reclamation Defense: OCI reclaims idle Always Free compute
# instances if CPU, memory, and network utilization remain
# below 20% for 7 consecutive days. Our idle-defense system
# generates periodic CPU bursts to prevent this.
# ──────────────────────────────────────────────────────────────

# ── Nanoservice Instance ────────────────────────────────────
# Runs the Rust nanoservice binary with Tokio async runtime.
# Endpoints: /healthz, /readyz, /metrics, /v1/write, /v1/read,
#            /v1/crush/map, /v1/capacity, /v1/fallback/status

resource "oci_core_instance" "nanoservice" {
  compartment_id      = var.oci_compartment_ocid
  availability_domain = data.oci_identity_availability_domain.ad.name
  display_name        = local.nanoservice_name
  shape               = var.nanoservice_shape

  shape_config {
    ocpus      = var.nanoservice_ocpus
    memory_in_gbs = var.nanoservice_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_a1.images[0].id
    boot_volume_size_in_gbs = var.nanoservice_boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.private.id
    display_name     = "nanoservice-vnic"
    assign_public_ip = false
    hostname_label   = "nanoservice"
    nsg_ids          = [oci_core_network_security_group.nanoservice.id]
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(templatefile(
      "${path.module}/cloud-init/nanoservice.yaml.tpl",
      {
        environment            = var.environment
        system_mode            = var.system_mode
        crush_default_rule     = var.crush_default_rule
        hsm_provider           = var.hsm_provider
        hsm_pin                = var.hsm_pin
        idle_defense_enabled   = var.idle_defense_enabled
        idle_defense_cron      = var.idle_defense_burst_cron
        idle_defense_duration  = var.idle_defense_burst_duration_seconds
        idle_defense_cpu_target = var.idle_defense_cpu_target_percent
        ceph_private_ip        = var.ceph_node_private_ip
        k3s_private_ip         = var.k3s_edge_private_ip
        oci_region             = var.oci_region
        object_namespace       = data.oci_objectstorage_namespace.ns.namespace
      }
    ))
  }

  # Prevent destruction of Always Free instances
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [source_details[0].source_id]
  }

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"      = "aid"
    "tranc3.io/instance-type" = "nanoservice"
    "Name"                  = local.nanoservice_name
  })

  timeouts {
    create = "30m"
    update = "30m"
    delete = "20m"
  }
}

# ── Ceph/MicroCeph Node ─────────────────────────────────────
# Single-node MicroCeph deployment for object/block storage.
# Provides S3-compatible RGW endpoint, RBD for K8s PVs,
# and CRUSH-aware data placement.

resource "oci_core_instance" "ceph_node" {
  compartment_id      = var.oci_compartment_ocid
  availability_domain = data.oci_identity_availability_domain.ad.name
  display_name        = local.ceph_node_name
  shape               = var.ceph_node_shape

  shape_config {
    ocpus      = var.ceph_node_ocpus
    memory_in_gbs = var.ceph_node_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_a1.images[0].id
    boot_volume_size_in_gbs = var.ceph_boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.ceph.id
    display_name     = "ceph-vnic"
    assign_public_ip = false
    hostname_label   = "ceph-node"
    nsg_ids          = [oci_core_network_security_group.ceph.id]
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(templatefile(
      "${path.module}/cloud-init/ceph-node.yaml.tpl",
      {
        environment            = var.environment
        system_mode            = var.system_mode
        ceph_cluster_network   = var.ceph_subnet_cidr
        nanoservice_private_ip = var.nanoservice_private_ip
        k3s_private_ip         = var.k3s_edge_private_ip
        crush_default_rule     = var.crush_default_rule
        hsm_provider           = var.hsm_provider
      }
    ))
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [source_details[0].source_id]
  }

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"      = "aid"
    "tranc3.io/instance-type" = "ceph_node"
    "Name"                  = local.ceph_node_name
  })

  timeouts {
    create = "30m"
    update = "30m"
    delete = "20m"
  }
}

# ── K3s Edge Node ───────────────────────────────────────────
# Lightweight Kubernetes for edge computing workloads.
# Runs Tranc3 operator with PID/AID/SID/NID CRDs.

resource "oci_core_instance" "k3s_edge" {
  compartment_id      = var.oci_compartment_ocid
  availability_domain = data.oci_identity_availability_domain.ad.name
  display_name        = local.k3s_edge_name
  shape               = var.k3s_edge_shape

  shape_config {
    ocpus      = var.k3s_edge_ocpus
    memory_in_gbs = var.k3s_edge_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_a1.images[0].id
    boot_volume_size_in_gbs = var.k3s_boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    display_name     = "k3s-vnic"
    assign_public_ip = true
    hostname_label   = "k3s-edge"
    nsg_ids          = [oci_core_network_security_group.k3s.id]
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(templatefile(
      "${path.module}/cloud-init/k3s-edge.yaml.tpl",
      {
        environment            = var.environment
        system_mode            = var.system_mode
        nanoservice_private_ip = var.nanoservice_private_ip
        ceph_private_ip        = var.ceph_node_private_ip
        crush_default_rule     = var.crush_default_rule
        hsm_provider           = var.hsm_provider
      }
    ))
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [source_details[0].source_id]
  }

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"      = "aid"
    "tranc3.io/instance-type" = "k3s_edge"
    "Name"                  = local.k3s_edge_name
  })

  timeouts {
    create = "30m"
    update = "30m"
    delete = "20m"
  }
}

# ── OS Image Data Source ─────────────────────────────────────

data "oci_core_images" "ubuntu_a1" {
  compartment_id           = var.oci_compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# ── Bastion / Public IP for Nanoservice ──────────────────────
# Reserved public IP for nanoservice (optional — uses private IP by default)

resource "oci_core_public_ip" "nanoservice" {
  count          = 0  # Set to 1 to assign a public IP to the nanoservice
  compartment_id = var.oci_compartment_ocid
  display_name   = "tranc3-nanoservice-pip-${var.environment}"
  lifetime       = "RESERVED"

  freeform_tags = local.common_tags
}

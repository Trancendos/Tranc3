# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — Citadel Primary Compute Instance
# Oracle Cloud Always Free Tier — VM.Standard.A1.Flex
#
# ⚠ ALWAYS FREE BUDGET NOTICE ⚠
# This Citadel instance consumes ALL 4 OCPU and ALL 24 GB RAM
# of the Oracle Cloud A1 Flex Always Free allocation.
# The other A1 instances (nanoservice, ceph_node, k3s_edge)
# defined in oci-free-tier.tf must have their OCPUs/RAM set to
# 0 or be left unprovisioned when Citadel is active — you cannot
# exceed 4 OCPU / 24 GB across all A1 instances combined.
#
# RECOMMENDATION: Use Citadel as the SOLE A1 instance.
# Comment out oci_core_instance.nanoservice, .ceph_node, and
# .k3s_edge in oci-free-tier.tf before applying this module.
# ──────────────────────────────────────────────────────────────

# ── Reserved Public IP ────────────────────────────────────────
# A reserved IP survives instance recreation and lets DNS stay stable.

resource "oci_core_public_ip" "citadel" {
  compartment_id = var.oci_compartment_ocid
  display_name   = "tranc3-citadel-pip-${var.environment}"
  lifetime       = "RESERVED"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"      = "aid"
    "tranc3.io/instance-type" = "citadel"
    "Name"                  = "tranc3-citadel-pip"
  })
}

# ── Citadel Network Security Group ───────────────────────────

resource "oci_core_network_security_group" "citadel" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-citadel-nsg-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"      = "aid"
    "tranc3.io/instance-type" = "citadel"
    "Name"                  = "tranc3-citadel-nsg"
  })
}

# SSH — allow from everywhere (key-only; fail2ban enforces brute-force limit)
resource "oci_core_network_security_group_security_rule" "citadel_ssh" {
  network_security_group_id = oci_core_network_security_group.citadel.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  description               = "SSH access (key-only; fail2ban active)"

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

# HTTP — allow from everywhere (Traefik → Let's Encrypt + redirect to HTTPS)
resource "oci_core_network_security_group_security_rule" "citadel_http" {
  network_security_group_id = oci_core_network_security_group.citadel.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  description               = "HTTP — Traefik ACME challenge + redirect"

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

# HTTPS — allow from everywhere
resource "oci_core_network_security_group_security_rule" "citadel_https" {
  network_security_group_id = oci_core_network_security_group.citadel.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  description               = "HTTPS — Traefik TLS termination"

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# Traefik dashboard — restricted to admin CIDR
resource "oci_core_network_security_group_security_rule" "citadel_traefik_dashboard" {
  network_security_group_id = oci_core_network_security_group.citadel.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.admin_cidr_block
  source_type               = "CIDR_BLOCK"
  description               = "Traefik dashboard — admin CIDR only"

  tcp_options {
    destination_port_range {
      min = 8888
      max = 8888
    }
  }
}

# Prometheus node-exporter — VCN internal only
resource "oci_core_network_security_group_security_rule" "citadel_node_exporter" {
  network_security_group_id = oci_core_network_security_group.citadel.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"
  description               = "Prometheus node-exporter — VCN scrape"

  tcp_options {
    destination_port_range {
      min = 9100
      max = 9100
    }
  }
}

# All egress allowed
resource "oci_core_network_security_group_security_rule" "citadel_egress" {
  network_security_group_id = oci_core_network_security_group.citadel.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Unrestricted egress"
}

# ── Citadel Security List update (add HTTP/HTTPS to public SL) ─
# The existing oci_core_security_list.public only opens :8080.
# Citadel lives in the same public subnet so we need 80/443 there too.
# We add dedicated NSG rules above — those override / supplement the SL.

# ── Citadel Compute Instance ─────────────────────────────────

resource "oci_core_instance" "citadel" {
  compartment_id      = var.oci_compartment_ocid
  availability_domain = data.oci_identity_availability_domain.ad.name
  display_name        = "aid-citadel-${var.environment}"
  shape               = "VM.Standard.A1.Flex"

  # ⚠ Uses the FULL Always Free A1 allocation (4 OCPU / 24 GB).
  # Do NOT run other A1 instances alongside this one.
  shape_config {
    ocpus         = var.citadel_ocpus
    memory_in_gbs = var.citadel_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_a1.images[0].id
    boot_volume_size_in_gbs = var.citadel_boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    display_name     = "citadel-vnic"
    assign_public_ip = false  # public IP assigned via oci_core_public_ip.citadel below
    hostname_label   = "citadel"
    nsg_ids          = [oci_core_network_security_group.citadel.id]
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile(
      "${path.module}/cloud-init/citadel.yaml.tpl",
      {
        domain               = var.domain
        environment          = var.environment
        system_mode          = var.system_mode
        admin_cidr_block     = var.admin_cidr_block
        ssh_authorized_keys  = var.ssh_public_key
        github_repo_url      = var.github_repo_url
        git_branch           = var.git_branch
        idle_defense_enabled = var.idle_defense_enabled
      }
    ))
  }

  # ── Protected: never destroy the primary Citadel instance ──
  lifecycle {
    prevent_destroy = true
    # Image OCIDs change with patch releases; ignore so plan doesn't show drift
    ignore_changes = [source_details[0].source_id]
  }

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity"      = "aid"
    "tranc3.io/instance-type" = "citadel"
    "tranc3.io/role"        = "primary"
    "Name"                  = "aid-citadel-${var.environment}"
  })

  timeouts {
    create = "30m"
    update = "30m"
    delete = "20m"
  }
}

# ── Assign reserved public IP to Citadel VNIC ────────────────

resource "oci_core_public_ip_assignment" "citadel" {
  # Wait for instance to exist before assigning the IP
  depends_on     = [oci_core_instance.citadel]
  public_ip_id   = oci_core_public_ip.citadel.id
  private_ip_id  = data.oci_core_private_ips.citadel_vnic.private_ips[0].id
}

data "oci_core_vnic_attachments" "citadel" {
  compartment_id = var.oci_compartment_ocid
  instance_id    = oci_core_instance.citadel.id
}

data "oci_core_private_ips" "citadel_vnic" {
  subnet_id = oci_core_subnet.public.id
  vnic_id   = data.oci_core_vnic_attachments.citadel.vnic_attachments[0].vnic_id
}

# ── Always Free Precondition ─────────────────────────────────

check "citadel_a1_budget" {
  assert {
    condition = (
      var.citadel_ocpus <= 4 &&
      var.citadel_memory_gbs <= 24 &&
      var.citadel_boot_volume_gbs <= 200
    )
    error_message = "Citadel exceeds Always Free A1 limits: max 4 OCPU, 24 GB RAM, 200 GB boot volume."
  }
}

# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — OCI Network Infrastructure
# VCN, Subnets, Security Lists, NSGs, Gateways
# Oracle Cloud Always Free Tier
# ──────────────────────────────────────────────────────────────

# ── VCN ──────────────────────────────────────────────────────

resource "oci_core_vcn" "tranc3" {
  compartment_id = var.oci_compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "tranc3-vcn-${var.environment}"
  dns_label      = var.vcn_dns_label

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-vcn"
  })
}

# ── Internet Gateway ─────────────────────────────────────────

resource "oci_core_internet_gateway" "tranc3" {
  count          = var.enable_internet_gateway ? 1 : 0
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-igw-${var.environment}"
  enabled        = true

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-igw"
  })
}

# ── NAT Gateway ──────────────────────────────────────────────

resource "oci_core_nat_gateway" "tranc3" {
  count          = var.enable_nat_gateway ? 1 : 0
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-nat-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-nat"
  })
}

# ── Service Gateway ──────────────────────────────────────────

resource "oci_core_service_gateway" "tranc3" {
  count          = var.enable_service_gateway ? 1 : 0
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-sgw-${var.environment}"

  services {
    service_id = data.oci_core_services.oci_services.services[0].id
  }

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-sgw"
  })
}

data "oci_core_services" "oci_services" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

# ── Security Lists ───────────────────────────────────────────

# Public security list — allows SSH, HTTP, nanoservice ports
resource "oci_core_security_list" "public" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-public-sl-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-public-sl"
  })

  # Allow SSH from anywhere (restrict in production)
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Allow nanoservice HTTP from anywhere
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 8080
      max = 8080
    }
  }

  # Allow nanoservice metrics from VCN only
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 9090
      max = 9090
    }
  }

  # Allow K3s API from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 6443
      max = 6443
    }
  }

  # Allow K3s agent traffic from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 10250
      max = 10250
    }
  }

  # Allow all egress
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    stateless   = false
  }
}

# Private security list — allows only VCN-internal traffic
resource "oci_core_security_list" "private" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-private-sl-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-private-sl"
  })

  # Allow all traffic from VCN
  ingress_security_rules {
    protocol  = "all"
    source    = var.vcn_cidr
    stateless = false
  }

  # Allow all egress
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    stateless   = false
  }
}

# Ceph security list — Ceph cluster network
resource "oci_core_security_list" "ceph" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-ceph-sl-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-ceph-sl"
  })

  # Allow Ceph monitors (6789, 3300) from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 6789
      max = 6789
    }
  }

  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 3300
      max = 3300
    }
  }

  # Allow Ceph OSDs (6800-7300) from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 6800
      max = 7300
    }
  }

  # Allow Ceph RGW (7480) from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 7480
      max = 7480
    }
  }

  # Allow Ceph Manager dashboard (8443) from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 8443
      max = 8443
    }
  }

  # Allow SSH from VCN
  ingress_security_rules {
    protocol  = "6"
    source    = var.vcn_cidr
    stateless = false

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Allow all egress
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    stateless   = false
  }
}

# ── Subnets ──────────────────────────────────────────────────

# Public subnet — nanoservice and K3s edge
resource "oci_core_subnet" "public" {
  compartment_id    = var.oci_compartment_ocid
  vcn_id            = oci_core_vcn.tranc3.id
  cidr_block        = var.public_subnet_cidr
  display_name      = "tranc3-public-subnet-${var.environment}"
  dns_label         = "pubsub"

  security_list_ids = [oci_core_security_list.public.id]

  route_table_id    = oci_core_route_table.public.id
  dhcp_options_id   = oci_core_vcn.tranc3.default_dhcp_options_id

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-public-subnet"
  })
}

# Private subnet — nanoservice internal
resource "oci_core_subnet" "private" {
  compartment_id    = var.oci_compartment_ocid
  vcn_id            = oci_core_vcn.tranc3.id
  cidr_block        = var.private_subnet_cidr
  display_name      = "tranc3-private-subnet-${var.environment}"
  dns_label         = "privsub"

  security_list_ids = [oci_core_security_list.private.id]

  route_table_id    = oci_core_route_table.private.id
  dhcp_options_id   = oci_core_vcn.tranc3.default_dhcp_options_id

  prohibit_public_ip_on_vnic = true

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-private-subnet"
  })
}

# Ceph subnet — storage cluster network
resource "oci_core_subnet" "ceph" {
  compartment_id    = var.oci_compartment_ocid
  vcn_id            = oci_core_vcn.tranc3.id
  cidr_block        = var.ceph_subnet_cidr
  display_name      = "tranc3-ceph-subnet-${var.environment}"
  dns_label         = "cephsub"

  security_list_ids = [oci_core_security_list.ceph.id]

  route_table_id    = oci_core_route_table.private.id
  dhcp_options_id   = oci_core_vcn.tranc3.default_dhcp_options_id

  prohibit_public_ip_on_vnic = true

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-ceph-subnet"
  })
}

# ── Route Tables ─────────────────────────────────────────────

# Public route table — traffic to internet via IGW
resource "oci_core_route_table" "public" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-public-rt-${var.environment}"

  dynamic "route_rules" {
    for_each = var.enable_internet_gateway ? [1] : []
    content {
      network_entity_id = oci_core_internet_gateway.tranc3[0].id
      destination       = "0.0.0.0/0"
      destination_type  = "CIDR_BLOCK"
    }
  }

  freeform_tags = local.common_tags
}

# Private route table — traffic to internet via NAT
resource "oci_core_route_table" "private" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-private-rt-${var.environment}"

  dynamic "route_rules" {
    for_each = var.enable_nat_gateway ? [1] : []
    content {
      network_entity_id = oci_core_nat_gateway.tranc3[0].id
      destination       = "0.0.0.0/0"
      destination_type  = "CIDR_BLOCK"
    }
  }

  # Service gateway route for OCI services
  dynamic "route_rules" {
    for_each = var.enable_service_gateway ? [1] : []
    content {
      network_entity_id = oci_core_service_gateway.tranc3[0].id
      destination       = data.oci_core_services.oci_services.services[0].cidr_block
      destination_type  = "SERVICE_CIDR_BLOCK"
    }
  }

  freeform_tags = local.common_tags
}

# ── Network Security Groups (NSGs) ──────────────────────────

# NSG for nanoservice instance
resource "oci_core_network_security_group" "nanoservice" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-nanoservice-nsg-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-nanoservice-nsg"
  })
}

resource "oci_core_network_security_group_security_rule" "nanoservice_http_ingress" {
  network_security_group_id = oci_core_network_security_group.nanoservice.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

resource "oci_core_network_security_group_security_rule" "nanoservice_metrics_ingress" {
  network_security_group_id = oci_core_network_security_group.nanoservice.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 9090
      max = 9090
    }
  }
}

# NSG for Ceph node
resource "oci_core_network_security_group" "ceph" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-ceph-nsg-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-ceph-nsg"
  })
}

resource "oci_core_network_security_group_security_rule" "ceph_rgw_ingress" {
  network_security_group_id = oci_core_network_security_group.ceph.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 7480
      max = 7480
    }
  }
}

resource "oci_core_network_security_group_security_rule" "ceph_mon_ingress" {
  network_security_group_id = oci_core_network_security_group.ceph.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 6789
      max = 6789
    }
  }
}

# NSG for K3s edge node
resource "oci_core_network_security_group" "k3s" {
  compartment_id = var.oci_compartment_ocid
  vcn_id         = oci_core_vcn.tranc3.id
  display_name   = "tranc3-k3s-nsg-${var.environment}"

  freeform_tags = merge(local.common_tags, {
    "tranc3.io/entity" = "nid"
    "Name"             = "tranc3-k3s-nsg"
  })
}

resource "oci_core_network_security_group_security_rule" "k3s_api_ingress" {
  network_security_group_id = oci_core_network_security_group.k3s.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 6443
      max = 6443
    }
  }
}

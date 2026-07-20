terraform {
  required_version = ">= 1.6"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 8.0"
    }
  }
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "oci" {
  region = var.region
  # Credentials read from ~/.oci/config or OCI_* environment variables
}

# ── Data Sources ─────────────────────────────────────────────────────────────

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_core_images" "ubuntu_22" {
  compartment_id           = var.compartment_id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
  filter {
    name   = "display_name"
    values = [".*aarch64.*"]
    regex  = true
  }
}

# ── VCN & Networking ─────────────────────────────────────────────────────────

resource "oci_core_vcn" "trancendos" {
  compartment_id = var.compartment_id
  display_name   = "trancendos-vcn"
  cidr_blocks    = ["10.0.0.0/16"]
  dns_label      = "trancendos"
}

resource "oci_core_internet_gateway" "trancendos" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.trancendos.id
  display_name   = "trancendos-igw"
  enabled        = true
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.trancendos.id
  display_name   = "trancendos-public-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.trancendos.id
  }
}

resource "oci_core_security_list" "trancendos" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.trancendos.id
  display_name   = "trancendos-security-list"

  # Allow all egress
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
    stateless   = false
  }

  # SSH
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 22
      max = 22
    }
  }

  # HTTP
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 80
      max = 80
    }
  }

  # HTTPS
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 443
      max = 443
    }
  }

  # ICMP ping
  ingress_security_rules {
    protocol  = "1"
    source    = "0.0.0.0/0"
    stateless = false
    icmp_options {
      type = 3
      code = 4
    }
  }
}

resource "oci_core_subnet" "public" {
  compartment_id      = var.compartment_id
  vcn_id              = oci_core_vcn.trancendos.id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "trancendos-public-subnet"
  cidr_block          = "10.0.1.0/24"
  route_table_id      = oci_core_route_table.public.id
  security_list_ids   = [oci_core_security_list.trancendos.id]
  dns_label           = "public"
  prohibit_public_ip_on_vnic = false
}

# ── Compute Instance (Ampere A1 — Always Free) ────────────────────────────────

resource "oci_core_instance" "trancendos" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.compartment_id
  display_name        = "trancendos-production"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gb
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_22.images[0].id
    boot_volume_size_in_gbs = 50
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    hostname_label   = "trancendos"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(file("${path.module}/cloud-init.sh"))
  }

  freeform_tags = {
    project     = "trancendos"
    environment = "production"
    cost        = "always-free"
  }
}

# ── Block Volume (150 GB — Always Free allocation) ────────────────────────────

resource "oci_core_volume" "data" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.compartment_id
  display_name        = "trancendos-data"
  size_in_gbs         = var.block_volume_size_gb
  freeform_tags = {
    project = "trancendos"
  }
}

resource "oci_core_volume_attachment" "data" {
  attachment_type = "paravirtualized"
  instance_id     = oci_core_instance.trancendos.id
  volume_id       = oci_core_volume.data.id
  display_name    = "trancendos-data-attachment"
  is_pv_encryption_in_transit_enabled = true
}

# ── Object Storage Bucket (20 GB free) ───────────────────────────────────────

resource "oci_objectstorage_bucket" "artifacts" {
  compartment_id = var.compartment_id
  namespace      = var.object_storage_namespace
  name           = "trancendos-artifacts"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Enabled"
  freeform_tags = {
    project = "trancendos"
  }
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "instance_public_ip" {
  description = "Public IP of the Trancendos production instance"
  value       = oci_core_instance.trancendos.public_ip
}

output "instance_id" {
  description = "OCI instance OCID"
  value       = oci_core_instance.trancendos.id
}

output "ssh_connection" {
  description = "SSH connection command"
  value       = "ssh ubuntu@${oci_core_instance.trancendos.public_ip}"
}

output "artifacts_bucket" {
  description = "Object storage bucket name"
  value       = oci_objectstorage_bucket.artifacts.name
}

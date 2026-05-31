variable "region" {
  description = "OCI region (e.g. uk-london-1, eu-frankfurt-1, us-ashburn-1)"
  type        = string
  default     = "uk-london-1"
}

variable "compartment_id" {
  description = "OCI compartment OCID (root compartment = tenancy OCID)"
  type        = string
}

variable "object_storage_namespace" {
  description = "OCI object storage namespace (from: oci os ns get)"
  type        = string
  default     = ""
}

variable "ssh_public_key" {
  description = "SSH public key for instance access (contents of ~/.ssh/id_ed25519.pub)"
  type        = string
  sensitive   = true
}

variable "instance_ocpus" {
  description = "Number of OCPUs for the Ampere A1 instance (max 4 on free tier)"
  type        = number
  default     = 4
}

variable "instance_memory_gb" {
  description = "Memory in GB for the Ampere A1 instance (max 24 GB on free tier)"
  type        = number
  default     = 24
}

variable "block_volume_size_gb" {
  description = "Block volume size in GB (free tier: 200 GB total across all volumes)"
  type        = number
  default     = 150
}

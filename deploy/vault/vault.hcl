ui            = true
disable_mlock = false

# Traefik terminates external TLS; Vault stays on the internal Docker network.
# tls_disable = true is acceptable — traffic never leaves the host.
# To enable mTLS, mount /vault/tls and uncomment the tls_* lines.
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
  # tls_cert_file      = "/vault/tls/vault.crt"
  # tls_key_file       = "/vault/tls/vault.key"
  # tls_client_ca_file = "/vault/tls/ca.crt"
}

# File backend — sufficient for single-node Citadel with regular snapshots.
# Upgrade path: swap "file" → "raft" (integrated HA) when adding a standby.
storage "file" {
  path = "/vault/data"
}

api_addr     = "http://tranc3-vault:8200"
cluster_addr = "http://tranc3-vault:8201"

# Exposes /v1/sys/metrics for Prometheus scraping (see monitoring/prometheus.yml)
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = true
}

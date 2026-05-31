ui = true
disable_mlock = false

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

storage "file" {
  path = "/vault/data"
}

api_addr     = "http://tranc3-vault:8200"
cluster_addr = "http://tranc3-vault:8201"

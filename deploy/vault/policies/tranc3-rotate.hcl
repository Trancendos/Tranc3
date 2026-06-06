# Policy: tranc3-rotate
# Used exclusively by rotate-secrets.sh — write the rotation paths only.

path "secret/data/tranc3/app/credentials" {
  capabilities = ["create", "read", "update"]
}

path "secret/data/tranc3/app/keys" {
  capabilities = ["create", "read", "update"]
}

path "secret/data/tranc3/workers/*" {
  capabilities = ["read", "update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

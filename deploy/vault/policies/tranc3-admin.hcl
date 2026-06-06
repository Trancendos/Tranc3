# Policy: tranc3-admin
# Used by vault-sync-secrets.sh and ops tooling.
# Full CRUD on the tranc3 KV tree; no sys/ or auth/ admin access.

path "secret/data/tranc3/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/tranc3/*" {
  capabilities = ["list", "read", "delete"]
}

path "secret/delete/tranc3/*" {
  capabilities = ["update"]
}

path "secret/destroy/tranc3/*" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "sys/mounts" {
  capabilities = ["read"]
}

path "sys/audit" {
  capabilities = ["read", "sudo"]
}

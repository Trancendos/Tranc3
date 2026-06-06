# Policy: tranc3-app
# All platform workers that only need to READ secrets.
# Token stored in VAULT_TOKEN env var inside each container.

path "secret/data/tranc3/app/*" {
  capabilities = ["read"]
}

path "secret/data/tranc3/workers/*" {
  capabilities = ["read"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

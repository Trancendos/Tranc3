# Vault Runbook — Tranc3 Citadel

HashiCorp Vault on the Citadel. Single-node file-backed storage.  
5 Shamir key shares, 3-of-5 threshold required to unseal.

---

## Quick Reference

| Task | Command |
|---|---|
| First-time init | `./scripts/vault-init.sh [--load-env .env.production]` |
| Unseal after reboot | `./scripts/vault-unseal.sh --from-file` |
| Unseal (manual keys) | `./scripts/vault-unseal.sh` |
| Check Vault status | `./scripts/vault-unseal.sh --status` |
| Push .env → Vault | `./scripts/vault-sync-secrets.sh --push --env-file .env.production` |
| Pull Vault → .env | `./scripts/vault-sync-secrets.sh --pull` |
| List secrets | `./scripts/vault-sync-secrets.sh --list` |
| Rotate all secrets | `./scripts/rotate-secrets.sh --all` |
| Rotate specific keys | `./scripts/rotate-secrets.sh --keys SECRET_KEY,JWT_SECRET` |
| Generate + push | `./scripts/generate_production_env.sh --force --push-to-vault` |
| View unseal keys | `./scripts/vault-unseal.sh --decrypt-keys` |
| View tokens | `./scripts/vault-unseal.sh --decrypt-tokens` |

---

## First-Time Setup

### 1. Start Vault

```bash
docker compose -f docker-compose.production.yml up -d vault
# Wait ~5 seconds for it to start
docker compose logs vault
```

### 2. Generate secrets

```bash
./scripts/generate_production_env.sh
# This writes .env.production (mode 600) with real random keys
```

### 3. Initialise Vault

```bash
./scripts/vault-init.sh --load-env .env.production
```

You will be prompted for an **encryption passphrase** (≥ 16 chars).  
This passphrase protects the Shamir keys file. **Store it in your password manager immediately.**

The script:
- Runs `vault operator init -key-shares=5 -key-threshold=3`
- Encrypts keys to `deploy/vault/vault-keys.enc` (AES-256-CBC, PBKDF2 600k iterations)
- Auto-unseals Vault with keys 1–3
- Enables KV v2, audit log, and ACL policies
- Creates three service tokens and encrypts them to `deploy/vault/vault-tokens.enc`
- Patches `VAULT_TOKEN` into `.env.production`
- Pushes all secrets into Vault KV

### 4. Back up the key files (CRITICAL)

```bash
# Copy to at least 2 offline locations (USB drive, encrypted cloud backup):
cp deploy/vault/vault-keys.enc   /media/usb/tranc3-vault-keys.enc
cp deploy/vault/vault-tokens.enc /media/usb/tranc3-vault-tokens.enc

# Then DELETE vault-keys.enc from the server:
shred -u deploy/vault/vault-keys.enc
```

`vault-tokens.enc` can stay on the server (tokens can be regenerated with the root token).  
`vault-keys.enc` **must not** remain on the server — if an attacker gets both the file and the server, they can unseal Vault.

---

## Unsealing After a Restart

Vault starts **sealed** after every restart. No secrets can be read until it is unsealed.

### Option A — From encrypted file (recommended)

```bash
./scripts/vault-unseal.sh --from-file
# Enter your encryption passphrase when prompted
# Uses keys 1, 2, 3 automatically
```

### Option B — Manual key entry

```bash
./scripts/vault-unseal.sh
# Enter any 3 of the 5 unseal keys when prompted
```

### Option C — From a remote key holder

If you have distributed keys to 3 different people:

```bash
# Each person runs on their machine to get their key:
./scripts/vault-unseal.sh --decrypt-keys   # then they read their key and tell you

# Then on the server:
./scripts/vault-unseal.sh   # enter the 3 keys interactively
```

---

## Shamir Key Distribution (Production Security Model)

For a production deployment, distribute the 5 keys:

| Key | Holder |
|---|---|
| Key 1 | Server admin (you) |
| Key 2 | Secondary admin / trusted colleague |
| Key 3 | Offline backup (USB in physical safe) |
| Key 4 | Emergency contact |
| Key 5 | Encrypted cloud backup |

Any 3 of the 5 can unseal. If you lose 3 or more keys permanently, the vault is unrecoverable.

---

## KV Secret Layout

```
secret/tranc3/app/credentials   — SECRET_KEY, JWT_SECRET, INTERNAL_SECRET
secret/tranc3/app/keys          — MASTER_KEY_SEED, VAULT_MASTER_KEY, AUDIT_SIGNING_KEY
secret/tranc3/app/database      — DATABASE_URL, REDIS_URL, REDIS_PASSWORD
secret/tranc3/app/services      — all inter-service URLs, VAULT_TOKEN
secret/tranc3/app/config        — non-secret config (ENVIRONMENT, LOG_LEVEL, etc.)
secret/tranc3/app/integrations  — optional cloud API keys (STRIPE, OPENROUTER, etc.)
```

Read a secret:
```bash
export VAULT_TOKEN=<app-or-admin-token>
vault kv get secret/tranc3/app/credentials
vault kv get -field=SECRET_KEY secret/tranc3/app/credentials
```

---

## Rotation Schedule

| Secret | Rotate every | Command |
|---|---|---|
| `SECRET_KEY` | 90 days | `./scripts/rotate-secrets.sh --keys SECRET_KEY` |
| `JWT_SECRET` | 90 days | `./scripts/rotate-secrets.sh --keys JWT_SECRET` |
| `INTERNAL_SECRET` | 90 days | `./scripts/rotate-secrets.sh --keys INTERNAL_SECRET` |
| `MASTER_KEY_SEED` | 180 days | `./scripts/rotate-secrets.sh --keys MASTER_KEY_SEED` |
| `VAULT_MASTER_KEY` | 180 days | `./scripts/rotate-secrets.sh --keys VAULT_MASTER_KEY` |
| `AUDIT_SIGNING_KEY` | 365 days | `./scripts/rotate-secrets.sh --keys AUDIT_SIGNING_KEY` |

**After rotating `JWT_SECRET`:** all active user sessions are immediately invalidated. Users will need to log in again. Schedule this during a maintenance window or low-traffic period.

**After rotating `MASTER_KEY_SEED` or `VAULT_MASTER_KEY`:** the vault-service worker derives its AES encryption key from these values. Existing secrets stored in vault-service's SQLite database will be inaccessible until the worker restarts and re-derives the key. If you have stored secrets using the old key, you must re-encrypt them before rotating.

---

## Service Tokens

Three tokens are created during init:

| Token | Policy | Use |
|---|---|---|
| `VAULT_APP_TOKEN` | `tranc3-app` | All platform workers — read-only on `secret/tranc3/*` |
| `VAULT_ADMIN_TOKEN` | `tranc3-admin` | `vault-sync-secrets.sh` — full CRUD |
| `VAULT_ROTATE_TOKEN` | `tranc3-rotate` | `rotate-secrets.sh` — write rotation paths only |

Tokens have a 30-day TTL and are renewable. To renew:
```bash
export VAULT_TOKEN=<token>
vault token renew
```

To see which token is in `.env.production`:
```bash
grep VAULT_TOKEN .env.production
```

To regenerate tokens (requires root token or admin token):
```bash
./scripts/vault-unseal.sh --decrypt-tokens   # get root token
export VAULT_TOKEN=<root-token>
vault token create -policy=tranc3-app -display-name=tranc3-app-token -period=720h -renewable=true
```

---

## Audit Log

The audit log is written to `/vault/logs/audit.log` inside the container (mounted as `vault-logs` Docker volume).

```bash
# Tail audit log
docker compose exec vault tail -f /vault/logs/audit.log

# Verify audit is enabled
vault audit list
```

Enable if it wasn't set up during init:
```bash
vault audit enable file file_path=/vault/logs/audit.log
```

---

## Disaster Recovery

### Scenario: Server destroyed, Vault data volume lost

1. Provision a new Citadel server
2. Start Vault: `docker compose up -d vault`
3. Copy `vault-keys.enc` and `vault-tokens.enc` from your offline backup
4. Run `./scripts/vault-init.sh` — it will detect Vault is uninitialised and re-init
5. Re-push secrets: `./scripts/vault-sync-secrets.sh --push --env-file .env.production`

### Scenario: Lost encryption passphrase

If you lose the passphrase that protects `vault-keys.enc`, you cannot decrypt the Shamir keys.  
To recover: you need the unseal keys in plaintext (distributed copies held by key holders).  
Collect 3 of the 5 keys, then use `vault-unseal.sh` interactively.

### Scenario: Vault sealed and key file deleted

If `vault-keys.enc` was deleted without backup AND Vault is sealed:  
The vault cannot be unsealed automatically. You need ≥ 3 key holders to provide their keys interactively.

---

## Prometheus Metrics

Vault exposes `/v1/sys/metrics` for Prometheus scraping.  
The telemetry block in `vault.hcl` enables this with a 30-second retention window.

Prometheus config (`monitoring/prometheus.yml`) should include:

```yaml
- job_name: vault
  metrics_path: /v1/sys/metrics
  params:
    format: [prometheus]
  bearer_token: <VAULT_APP_TOKEN>
  static_configs:
    - targets: ['tranc3-vault:8200']
```

#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# vault-init.sh — One-time Vault initialisation for the Citadel
#
# What this does:
#   1. Waits for Vault to be reachable
#   2. Initialises with 5 Shamir key shares, threshold 3
#   3. Encrypts keys + root token → deploy/vault/vault-keys.enc  (AES-256-CBC)
#   4. Auto-unseals using the generated keys
#   5. Enables KV v2 at secret/
#   6. Enables file audit log
#   7. Writes ACL policies (tranc3-app, tranc3-admin, tranc3-rotate)
#   8. Creates three service tokens, encrypts → deploy/vault/vault-tokens.enc
#   9. Patches VAULT_TOKEN into .env.production (app token)
#  10. Optionally pushes .env.production into Vault KV
#
# Usage:
#   ./scripts/vault-init.sh [--load-env .env.production]
#
# Prerequisites:
#   vault CLI on PATH, OR set VAULT_BIN to the full path
#   docker compose -f docker-compose.production.yml up -d vault
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_BIN="${VAULT_BIN:-vault}"
KEYS_ENC="deploy/vault/vault-keys.enc"
TOKENS_ENC="deploy/vault/vault-tokens.enc"
POLICY_DIR="deploy/vault/policies"
LOAD_ENV=""

for arg in "$@"; do
  case "$arg" in
    --load-env=*) LOAD_ENV="${arg#--load-env=}" ;;
    --load-env)   shift; LOAD_ENV="${1:-}" ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "[vault-init] $*"; }
err() { echo "[vault-init] ERROR: $*" >&2; exit 1; }

encrypt_to_file() {
  local plaintext="$1" outfile="$2" passphrase="$3"
  printf '%s' "$plaintext" \
    | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -pass "pass:$passphrase" \
    | base64 > "$outfile"
  chmod 600 "$outfile"
}

wait_for_vault() {
  log "Waiting for Vault at $VAULT_ADDR (up to 120 s)..."
  for i in $(seq 1 24); do
    code=$(curl -s -o /dev/null -w "%{http_code}" "$VAULT_ADDR/v1/sys/health" 2>/dev/null || echo 000)
    # 200=ok, 429=standby, 501=not-init, 503=sealed — all mean the process is up
    if [[ "$code" =~ ^(200|429|472|473|501|503)$ ]]; then
      log "Vault reachable (HTTP $code)."; return
    fi
    log "  Attempt $i/24 — HTTP $code — retrying in 5 s..."
    sleep 5
  done
  err "Vault unreachable after 120 s. Is the container running?"
}

# ── Already initialised? ──────────────────────────────────────────────────────
wait_for_vault

INIT_STATUS=$(curl -sf "$VAULT_ADDR/v1/sys/init" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('initialized','false'))" 2>/dev/null \
  || echo "false")

if [[ "$INIT_STATUS" == "true" ]]; then
  log "Vault already initialised."
  SEALED=$("$VAULT_BIN" status -format=json 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed','true'))" 2>/dev/null \
    || echo "true")
  if [[ "$SEALED" == "true" ]]; then
    log "Vault is sealed — run: ./scripts/vault-unseal.sh"
  else
    log "Vault is unsealed and ready."
  fi
  exit 0
fi

# ── Passphrase prompt ─────────────────────────────────────────────────────────
cat <<'BANNER'

  ┌──────────────────────────────────────────────────────────────────────┐
  │          VAULT INITIALISATION — READ BEFORE CONTINUING               │
  │                                                                      │
  │  You will choose an ENCRYPTION PASSPHRASE to protect the Shamir      │
  │  unseal keys and root token written to:                              │
  │                                                                      │
  │    deploy/vault/vault-keys.enc                                       │
  │    deploy/vault/vault-tokens.enc                                     │
  │                                                                      │
  │  Store this passphrase OFFLINE (password manager + paper safe).      │
  │  Without it you cannot unseal Vault after a server restart.          │
  │  Back the .enc files up to ≥ 2 offline locations, then DELETE        │
  │  vault-keys.enc from the server:  shred -u deploy/vault/vault-keys.enc │
  └──────────────────────────────────────────────────────────────────────┘

BANNER

read -r -s -p "  Encryption passphrase (≥ 16 chars): " PASSPHRASE; echo
read -r -s -p "  Confirm passphrase:                  " PASSPHRASE2; echo

[[ "$PASSPHRASE" == "$PASSPHRASE2" ]] || err "Passphrases do not match."
[[ ${#PASSPHRASE} -ge 16 ]]           || err "Passphrase must be ≥ 16 characters."

# ── Initialise ────────────────────────────────────────────────────────────────
log "Initialising Vault (5 shares, threshold 3)..."
INIT_JSON=$("$VAULT_BIN" operator init -key-shares=5 -key-threshold=3 -format=json)

ROOT_TOKEN=$(printf '%s' "$INIT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['root_token'])")
readarray -t UNSEAL_KEYS < <(printf '%s' "$INIT_JSON" \
  | python3 -c "import sys,json; [print(k) for k in json.load(sys.stdin)['unseal_keys_b64']]")

# ── Encrypt Shamir keys ───────────────────────────────────────────────────────
KEYS_PLAIN=$(cat <<EOF
# Tranc3 Citadel — Vault Shamir Unseal Keys
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# 3-of-5 keys required to unseal.
# KEEP OFFLINE. DELETE vault-keys.enc FROM SERVER AFTER BACKUP.

UNSEAL_KEY_1=${UNSEAL_KEYS[0]}
UNSEAL_KEY_2=${UNSEAL_KEYS[1]}
UNSEAL_KEY_3=${UNSEAL_KEYS[2]}
UNSEAL_KEY_4=${UNSEAL_KEYS[3]}
UNSEAL_KEY_5=${UNSEAL_KEYS[4]}
ROOT_TOKEN=${ROOT_TOKEN}
EOF
)
encrypt_to_file "$KEYS_PLAIN" "$KEYS_ENC" "$PASSPHRASE"
log "Shamir keys encrypted → $KEYS_ENC"

# ── Unseal ────────────────────────────────────────────────────────────────────
log "Unsealing Vault..."
export VAULT_TOKEN="$ROOT_TOKEN"
for i in 0 1 2; do
  "$VAULT_BIN" operator unseal "${UNSEAL_KEYS[$i]}" > /dev/null
done
log "Vault unsealed."

# ── KV v2 ─────────────────────────────────────────────────────────────────────
log "Enabling KV v2 at secret/..."
"$VAULT_BIN" secrets enable -path=secret kv-v2 2>/dev/null || log "  (KV already enabled)"

# ── Audit log ─────────────────────────────────────────────────────────────────
log "Enabling file audit log..."
"$VAULT_BIN" audit enable file file_path=/vault/logs/audit.log 2>/dev/null || log "  (audit already enabled)"

# ── ACL policies ─────────────────────────────────────────────────────────────
log "Writing ACL policies..."
for hcl in "$POLICY_DIR"/*.hcl; do
  name=$(basename "$hcl" .hcl)
  "$VAULT_BIN" policy write "$name" "$hcl"
  log "  policy: $name"
done

# ── Service tokens ────────────────────────────────────────────────────────────
log "Creating service tokens..."
make_token() {
  local policy=$1 name=$2
  "$VAULT_BIN" token create -policy="$policy" -display-name="$name" \
    -period=720h -renewable=true -format=json \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['auth']['client_token'])"
}

APP_TOKEN=$(make_token    tranc3-app    tranc3-app-token)
ADMIN_TOKEN=$(make_token  tranc3-admin  tranc3-admin-token)
ROTATE_TOKEN=$(make_token tranc3-rotate tranc3-rotate-token)

TOKENS_PLAIN=$(cat <<EOF
# Tranc3 Citadel — Vault Service Tokens
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# All tokens: 30-day TTL, renewable.

VAULT_ROOT_TOKEN=${ROOT_TOKEN}
VAULT_APP_TOKEN=${APP_TOKEN}
VAULT_ADMIN_TOKEN=${ADMIN_TOKEN}
VAULT_ROTATE_TOKEN=${ROTATE_TOKEN}
EOF
)
encrypt_to_file "$TOKENS_PLAIN" "$TOKENS_ENC" "$PASSPHRASE"
log "Service tokens encrypted → $TOKENS_ENC"

# ── Patch VAULT_TOKEN into .env.production ────────────────────────────────────
for env_file in .env.production .env; do
  [[ -f "$env_file" ]] || continue
  if grep -q "^VAULT_TOKEN=" "$env_file"; then
    sed -i "s|^VAULT_TOKEN=.*|VAULT_TOKEN=${APP_TOKEN}|" "$env_file"
  else
    printf '\nVAULT_TOKEN=%s\n' "$APP_TOKEN" >> "$env_file"
  fi
  chmod 600 "$env_file"
  log "VAULT_TOKEN patched into $env_file"
done

# ── Optionally push .env.production into Vault KV ────────────────────────────
if [[ -n "$LOAD_ENV" ]]; then
  if [[ -f "$LOAD_ENV" ]]; then
    log "Loading $LOAD_ENV into Vault KV..."
    VAULT_TOKEN="$ADMIN_TOKEN" \
      "$ROOT/scripts/vault-sync-secrets.sh" --push --env-file "$LOAD_ENV"
  else
    log "WARNING: --load-env file not found: $LOAD_ENV — skipping."
  fi
fi

# ── Scrub secrets from env ────────────────────────────────────────────────────
unset VAULT_TOKEN ROOT_TOKEN APP_TOKEN ADMIN_TOKEN ROTATE_TOKEN
unset INIT_JSON KEYS_PLAIN TOKENS_PLAIN PASSPHRASE PASSPHRASE2
unset UNSEAL_KEYS

cat <<'DONE'

  ┌──────────────────────────────────────────────────────────────────────┐
  │  VAULT INITIALISATION COMPLETE                                       │
  │                                                                      │
  │  IMMEDIATE ACTIONS:                                                  │
  │  1. Copy vault-keys.enc and vault-tokens.enc to ≥ 2 offline devices  │
  │  2. Delete vault-keys.enc from the server:                           │
  │       shred -u deploy/vault/vault-keys.enc                          │
  │  3. Push app secrets into Vault:                                     │
  │       ./scripts/vault-sync-secrets.sh --push --env-file .env.production │
  │  4. On every reboot, unseal with:                                    │
  │       ./scripts/vault-unseal.sh                                      │
  └──────────────────────────────────────────────────────────────────────┘

DONE

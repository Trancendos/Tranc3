#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# vault-sync-secrets.sh — Push .env.production → Vault KV, or Pull → .env
#
# Usage:
#   # Push all secrets from .env.production into Vault:
#   ./scripts/vault-sync-secrets.sh --push [--env-file .env.production]
#
#   # Pull secrets from Vault and regenerate .env.production:
#   ./scripts/vault-sync-secrets.sh --pull [--env-file .env.production]
#
#   # List all secret paths in Vault:
#   ./scripts/vault-sync-secrets.sh --list
#
# Environment:
#   VAULT_ADDR  (default: http://127.0.0.1:8200)
#   VAULT_TOKEN — must have tranc3-admin policy for --push, tranc3-app for --pull
#
# KV layout in Vault:
#   secret/tranc3/app/credentials  — SECRET_KEY, JWT_SECRET, INTERNAL_SECRET
#   secret/tranc3/app/keys         — MASTER_KEY_SEED, VAULT_MASTER_KEY, AUDIT_SIGNING_KEY
#   secret/tranc3/app/database     — DATABASE_URL, REDIS_URL, REDIS_PASSWORD
#   secret/tranc3/app/services     — all service URLs
#   secret/tranc3/app/config       — non-secret config (ENVIRONMENT, LOG_LEVEL, etc.)
#   secret/tranc3/app/integrations — optional cloud keys (STRIPE, OPENROUTER, etc.)
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_BIN="${VAULT_BIN:-vault}"
ENV_FILE=".env.production"
MODE=""

for arg in "$@"; do
  case "$arg" in
    --push)           MODE="push" ;;
    --pull)           MODE="pull" ;;
    --list)           MODE="list" ;;
    --env-file=*)     ENV_FILE="${arg#--env-file=}" ;;
    --env-file)       shift; ENV_FILE="${1:-}" ;;
  esac
done

[[ -n "$MODE" ]] || { echo "Usage: $0 --push|--pull|--list [--env-file FILE]"; exit 1; }

log() { echo "[vault-sync] $*"; }
err() { echo "[vault-sync] ERROR: $*" >&2; exit 1; }

# Require VAULT_TOKEN
[[ -n "${VAULT_TOKEN:-}" ]] || err "VAULT_TOKEN not set. Run: export VAULT_TOKEN=<token>"

# Check Vault is unsealed
SEALED=$("$VAULT_BIN" status -format=json 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed','true'))" 2>/dev/null \
  || echo "true")
[[ "$SEALED" == "false" ]] || err "Vault is sealed. Run: ./scripts/vault-unseal.sh"

# ── List mode ─────────────────────────────────────────────────────────────────
if [[ "$MODE" == "list" ]]; then
  log "Secret paths under secret/tranc3/:"
  "$VAULT_BIN" kv list secret/tranc3/app/ 2>/dev/null || log "  (no secrets yet)"
  exit 0
fi

# ── Push: .env.production → Vault KV ─────────────────────────────────────────
if [[ "$MODE" == "push" ]]; then
  [[ -f "$ENV_FILE" ]] || err "$ENV_FILE not found."
  log "Pushing $ENV_FILE → Vault KV..."

  # Parse env file into associative array (skip comments and blank lines)
  declare -A ENV_VARS
  while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    ENV_VARS["$key"]="$val"
  done < <(grep -v '^#' "$ENV_FILE" | grep '=')

  # Helper: push a group of keys to a Vault path
  kv_put() {
    local path="$1"; shift
    local args=()
    for key in "$@"; do
      [[ -n "${ENV_VARS[$key]+_}" ]] && args+=("${key}=${ENV_VARS[$key]}")
    done
    [[ ${#args[@]} -gt 0 ]] || return 0
    "$VAULT_BIN" kv put "secret/tranc3/${path}" "${args[@]}" > /dev/null
    log "  ✓ secret/tranc3/${path} (${#args[@]} fields)"
  }

  kv_put "app/credentials" \
    SECRET_KEY JWT_SECRET INTERNAL_SECRET

  kv_put "app/keys" \
    MASTER_KEY_SEED VAULT_MASTER_KEY AUDIT_SIGNING_KEY

  kv_put "app/database" \
    DATABASE_URL REDIS_URL REDIS_PASSWORD OUTLINE_DB_PASSWORD

  kv_put "app/services" \
    TRANC3_BACKEND_URL TRANC3_NANO_URL AUTH_SERVICE_URL USERS_SERVICE_URL \
    PRODUCTS_SERVICE_URL ORDERS_SERVICE_URL PAYMENTS_SERVICE_URL \
    INFINITY_WS_URL INFINITY_AUTH_URL INFINITY_AI_URL TRANC3_AI_SERVICE_URL \
    VAULT_ADDR VAULT_TOKEN

  kv_put "app/config" \
    ENVIRONMENT DEBUG PORT LOG_LEVEL JWT_ALGORITHM ACCESS_TOKEN_EXPIRE_MINUTES \
    CORS_ORIGINS FRONTEND_URL VITE_API_URL ALLOWED_ORIGINS \
    OLLAMA_URL OLLAMA_MODEL EMBED_MODEL \
    ADAPTIVE_ROTATION_ENABLED ADAPTIVE_ROTATION_CHAIN ADAPTIVE_COOLDOWN_SECONDS \
    PROACTIVE_ORCHESTRATOR_ENABLED PROACTIVE_INTERVAL_SECONDS ENABLE_SWARM \
    PROMETHEUS_ENABLED OTEL_EXPORTER_OTLP_ENDPOINT \
    ENTITY_OVERRIDES_DB INFINITY_ADMIN_DB_PATH ENTITY_OVERRIDES_CACHE_TTL

  kv_put "app/integrations" \
    OPENROUTER_API_KEY HF_API_KEY GROQ_API_KEY GEMINI_API_KEY \
    CEREBRAS_API_KEY SAMBANOVA_API_KEY \
    STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET

  log "Push complete."
  exit 0
fi

# ── Pull: Vault KV → .env.production ─────────────────────────────────────────
if [[ "$MODE" == "pull" ]]; then
  [[ ! -f "$ENV_FILE" ]] || { log "WARNING: $ENV_FILE exists — use --force or rename first."; exit 1; }

  log "Pulling secrets from Vault → $ENV_FILE..."

  get_field() {
    local path="$1" field="$2"
    "$VAULT_BIN" kv get -field="$field" "secret/tranc3/${path}" 2>/dev/null || echo ""
  }

  # Pull credential group
  SECRET_KEY=$(get_field app/credentials SECRET_KEY)
  JWT_SECRET=$(get_field app/credentials JWT_SECRET)
  INTERNAL_SECRET=$(get_field app/credentials INTERNAL_SECRET)
  MASTER_KEY_SEED=$(get_field app/keys MASTER_KEY_SEED)
  VAULT_MASTER_KEY=$(get_field app/keys VAULT_MASTER_KEY)
  AUDIT_SIGNING_KEY=$(get_field app/keys AUDIT_SIGNING_KEY)
  DATABASE_URL=$(get_field app/database DATABASE_URL)
  REDIS_URL=$(get_field app/database REDIS_URL)
  REDIS_PASSWORD=$(get_field app/database REDIS_PASSWORD)
  OUTLINE_DB_PASSWORD=$(get_field app/database OUTLINE_DB_PASSWORD)
  VAULT_TOKEN=$(get_field app/services VAULT_TOKEN)

  [[ -n "$SECRET_KEY" ]] || err "Could not read SECRET_KEY from Vault. Check VAULT_TOKEN permissions."

  cat > "$ENV_FILE" <<EOF
# Pulled from Vault by vault-sync-secrets.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT COMMIT.

ENVIRONMENT=production
DEBUG=false
PORT=8000
LOG_LEVEL=INFO

SECRET_KEY=${SECRET_KEY}
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

DATABASE_URL=${DATABASE_URL}
REDIS_URL=${REDIS_URL}
REDIS_PASSWORD=${REDIS_PASSWORD}
OUTLINE_DB_PASSWORD=${OUTLINE_DB_PASSWORD}

INTERNAL_SECRET=${INTERNAL_SECRET}
MASTER_KEY_SEED=${MASTER_KEY_SEED}
VAULT_MASTER_KEY=${VAULT_MASTER_KEY}
AUDIT_SIGNING_KEY=${AUDIT_SIGNING_KEY}

VAULT_ADDR=http://tranc3-vault:8200
VAULT_TOKEN=${VAULT_TOKEN}
EOF

  chmod 600 "$ENV_FILE"
  log "Wrote $ENV_FILE (mode 600). Add remaining config from .env.example if needed."
  exit 0
fi

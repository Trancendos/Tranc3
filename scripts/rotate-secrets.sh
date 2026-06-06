#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# rotate-secrets.sh — Rotate cryptographic secrets for the Tranc3 platform
#
# Rotation policy:
#   SECRET_KEY, JWT_SECRET  — rotate every 90 days (invalidates all sessions)
#   INTERNAL_SECRET         — rotate every 90 days (shared service header)
#   MASTER_KEY_SEED         — rotate every 180 days (re-encrypts vault-service data)
#   AUDIT_SIGNING_KEY       — rotate every 365 days (breaks audit chain before date)
#   VAULT_MASTER_KEY        — rotate every 180 days (re-derives AES key in vault-service)
#
# What this script does:
#   1. Generates new values for the requested keys
#   2. Writes new values to Vault KV (requires VAULT_TOKEN with tranc3-rotate policy)
#   3. Patches .env.production with the new values
#   4. Prints a checklist of manual follow-up steps (service restarts, JWT invalidation)
#
# Usage:
#   ./scripts/rotate-secrets.sh [--all] [--keys SECRET_KEY,JWT_SECRET] [--dry-run]
#
# Examples:
#   ./scripts/rotate-secrets.sh --all                   # rotate everything
#   ./scripts/rotate-secrets.sh --keys SECRET_KEY,JWT_SECRET
#   ./scripts/rotate-secrets.sh --all --dry-run         # preview only
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_BIN="${VAULT_BIN:-vault}"
ENV_FILE=".env.production"
DRY_RUN=false
ROTATE_ALL=false
KEYS_ARG=""

for arg in "$@"; do
  case "$arg" in
    --all)         ROTATE_ALL=true ;;
    --dry-run)     DRY_RUN=true ;;
    --keys=*)      KEYS_ARG="${arg#--keys=}" ;;
    --keys)        shift; KEYS_ARG="${1:-}" ;;
    --env-file=*)  ENV_FILE="${arg#--env-file=}" ;;
  esac
done

[[ "$ROTATE_ALL" == true || -n "$KEYS_ARG" ]] \
  || { echo "Usage: $0 --all | --keys KEY1,KEY2 [--dry-run]"; exit 1; }

log()  { echo "[rotate-secrets] $*"; }
info() { echo "  $*"; }
err()  { echo "[rotate-secrets] ERROR: $*" >&2; exit 1; }

gen_hex() { python3 -c "import secrets; print(secrets.token_hex(32))"; }

# Determine which keys to rotate
declare -A ROTATABLE=(
  [SECRET_KEY]="app/credentials"
  [JWT_SECRET]="app/credentials"
  [INTERNAL_SECRET]="app/credentials"
  [MASTER_KEY_SEED]="app/keys"
  [VAULT_MASTER_KEY]="app/keys"
  [AUDIT_SIGNING_KEY]="app/keys"
)

if [[ "$ROTATE_ALL" == true ]]; then
  ROTATE_KEYS=("${!ROTATABLE[@]}")
else
  IFS=',' read -ra ROTATE_KEYS <<< "$KEYS_ARG"
fi

# Validate requested keys
for k in "${ROTATE_KEYS[@]}"; do
  [[ -n "${ROTATABLE[$k]+_}" ]] \
    || err "Unknown key: '$k'. Valid: ${!ROTATABLE[*]}"
done

log "Keys to rotate: ${ROTATE_KEYS[*]}"
log "Dry run: $DRY_RUN"

# Check Vault if not dry-run
if [[ "$DRY_RUN" == false ]]; then
  [[ -n "${VAULT_TOKEN:-}" ]] || err "VAULT_TOKEN not set."
  SEALED=$("$VAULT_BIN" status -format=json 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed','true'))" 2>/dev/null \
    || echo "true")
  [[ "$SEALED" == "false" ]] || err "Vault is sealed. Run: ./scripts/vault-unseal.sh"
fi

[[ -f "$ENV_FILE" ]] || err "$ENV_FILE not found. Run generate_production_env.sh first."

# ── Generate new values ───────────────────────────────────────────────────────
declare -A NEW_VALS
for k in "${ROTATE_KEYS[@]}"; do
  NEW_VALS["$k"]=$(gen_hex)
  log "  Generated new $k"
done

if [[ "$DRY_RUN" == true ]]; then
  log "Dry run — no changes written."
  for k in "${ROTATE_KEYS[@]}"; do
    info "$k = ${NEW_VALS[$k]}"
  done
  exit 0
fi

# ── Write to Vault KV (group by path to minimise round-trips) ────────────────
declare -A PATH_UPDATES
for k in "${ROTATE_KEYS[@]}"; do
  path="${ROTATABLE[$k]}"
  PATH_UPDATES["$path"]+="${k} "
done

for vault_path in "${!PATH_UPDATES[@]}"; do
  read -ra keys_in_path <<< "${PATH_UPDATES[$vault_path]}"

  # Read existing fields at this path first (preserve non-rotated keys)
  existing_json=$("$VAULT_BIN" kv get -format=json "secret/tranc3/${vault_path}" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('data',{}).get('data',{})))" \
    || echo "{}")

  # Build kv put args: existing fields overridden with new values
  declare -a put_args=()
  while IFS='=' read -r ek ev; do
    [[ -n "$ek" ]] || continue
    put_args+=("${ek}=${ev}")
  done < <(printf '%s' "$existing_json" \
    | python3 -c "import sys,json; [print(f'{k}={v}') for k,v in json.load(sys.stdin).items()]")

  for k in "${keys_in_path[@]}"; do
    # Replace or append
    filtered=()
    found=false
    for a in "${put_args[@]}"; do
      if [[ "${a%%=*}" == "$k" ]]; then
        filtered+=("${k}=${NEW_VALS[$k]}")
        found=true
      else
        filtered+=("$a")
      fi
    done
    [[ "$found" == true ]] || filtered+=("${k}=${NEW_VALS[$k]}")
    put_args=("${filtered[@]}")
  done

  "$VAULT_BIN" kv put "secret/tranc3/${vault_path}" "${put_args[@]}" > /dev/null
  log "  Updated Vault secret/tranc3/${vault_path}"
  unset put_args
done

# ── Patch .env.production ─────────────────────────────────────────────────────
log "Patching $ENV_FILE..."
for k in "${ROTATE_KEYS[@]}"; do
  if grep -q "^${k}=" "$ENV_FILE"; then
    sed -i "s|^${k}=.*|${k}=${NEW_VALS[$k]}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$k" "${NEW_VALS[$k]}" >> "$ENV_FILE"
  fi
done
chmod 600 "$ENV_FILE"
log "Patched $ENV_FILE."

# ── Rotation checklist ────────────────────────────────────────────────────────
cat <<CHECKLIST

  ┌──────────────────────────────────────────────────────────────────────┐
  │  ROTATION COMPLETE — REQUIRED FOLLOW-UP ACTIONS                      │
  ├──────────────────────────────────────────────────────────────────────┤
CHECKLIST

for k in "${ROTATE_KEYS[@]}"; do
  case "$k" in
    SECRET_KEY)
      echo "  │  SECRET_KEY rotated — restart tranc3-backend:"
      echo "  │    docker compose restart tranc3-backend"
      ;;
    JWT_SECRET)
      echo "  │  JWT_SECRET rotated — ALL active sessions INVALIDATED."
      echo "  │  Users must log in again. Restart: infinity-auth, tranc3-backend"
      echo "  │    docker compose restart infinity-auth tranc3-backend"
      ;;
    INTERNAL_SECRET)
      echo "  │  INTERNAL_SECRET rotated — restart all workers that use X-Internal-Secret:"
      echo "  │    docker compose restart tranc3-backend users-service gateway-service"
      ;;
    MASTER_KEY_SEED|VAULT_MASTER_KEY)
      echo "  │  $k rotated — vault-service must re-derive its AES key."
      echo "  │  Existing encrypted secrets in vault-service SQLite are NOT re-encrypted"
      echo "  │  automatically. Run: vault-service /admin/rekey after restart."
      echo "  │    docker compose restart vault-service"
      ;;
    AUDIT_SIGNING_KEY)
      echo "  │  AUDIT_SIGNING_KEY rotated — audit log chain before $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "  │  will not verify against the new key. Archive old logs before restarting."
      echo "  │    docker compose restart tranc3-backend"
      ;;
  esac
done

cat <<CHECKLIST
  └──────────────────────────────────────────────────────────────────────┘

  Record this rotation in your change log with date: $(date -u +%Y-%m-%dT%H:%M:%SZ)

CHECKLIST

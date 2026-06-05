#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# vault-unseal.sh — Interactive and automated Vault unseal for Tranc3 Citadel
#
# MODES
#   (default)          Interactive: prompts for 3 unseal keys at the terminal
#   --from-file        Decrypt vault-keys.enc with passphrase; use keys 1-3
#   --key-index N,M,P  Use specific key indices from the decrypted file (1-5)
#   --watch            Daemon: poll Vault every N seconds; auto-unseal on seal
#   --verify           After unsealing, verify Vault is fully operational
#   --snapshot         Trigger a Vault raft snapshot before unsealing
#   --token-renew      Renew service tokens (app + admin) after unsealing
#   --decrypt-keys     Print decrypted keys file to stdout and exit
#   --decrypt-tokens   Print decrypted tokens file to stdout and exit
#   --status           Print Vault status (JSON or human) and exit
#
# FLAGS (combinable with modes)
#   --json             Emit structured JSON on stdout (for Ansible/CI)
#   --wait             Wait up to --timeout seconds for Vault to start
#   --timeout N        Seconds to wait (default: 120)
#   --poll-interval N  Seconds between polls in --watch mode (default: 30)
#   --keys-file PATH   Path to encrypted keys file (default: deploy/vault/vault-keys.enc)
#   --tokens-file PATH Path to encrypted tokens file (default: deploy/vault/vault-tokens.enc)
#   --audit-log PATH   Append unseal events to this file (default: logs/vault-unseal.log)
#   --no-audit         Disable local audit logging
#
# EXIT CODES
#   0  Vault unsealed (or was already unsealed)
#   1  Error / unexpected failure
#   2  Vault sealed and no action taken (e.g. --status with sealed Vault)
#   3  Vault not reachable (timeout)
#   4  Wrong passphrase or corrupted key file
#   5  Vault not initialised
#
# ENVIRONMENT
#   VAULT_ADDR      Vault API address (default: http://127.0.0.1:8200)
#   VAULT_BIN       Path to vault binary (default: vault)
#   VAULT_TOKEN     Used for --token-renew and --verify (optional)
#   UNSEAL_PASSPHRASE  If set, skips passphrase prompt (for non-interactive use)
#
# EXAMPLES
#   # First unseal after a reboot (interactive passphrase):
#   ./scripts/vault-unseal.sh --from-file --verify
#
#   # Non-interactive (CI/Ansible — passphrase from env):
#   UNSEAL_PASSPHRASE="$SECRET" ./scripts/vault-unseal.sh --from-file --wait --json
#
#   # Watch mode: runs in background, re-unseals whenever Vault restarts:
#   ./scripts/vault-unseal.sh --watch --from-file --poll-interval 30 &
#
#   # Check status only:
#   ./scripts/vault-unseal.sh --status --json
#
#   # Use specific key indices (e.g. keys 2, 4, 5):
#   ./scripts/vault-unseal.sh --from-file --key-index 2,4,5
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── Defaults ──────────────────────────────────────────────────────────────────
export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_BIN="${VAULT_BIN:-vault}"
KEYS_FILE="deploy/vault/vault-keys.enc"
TOKENS_FILE="deploy/vault/vault-tokens.enc"
AUDIT_LOG="logs/vault-unseal.log"
TIMEOUT=120
POLL_INTERVAL=30
KEY_INDICES=(1 2 3)   # default: use keys 1, 2, 3

# Mode flags
MODE="interactive"
OPT_WAIT=false
OPT_VERIFY=false
OPT_SNAPSHOT=false
OPT_TOKEN_RENEW=false
OPT_JSON=false
OPT_NO_AUDIT=false

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-file)       MODE="from-file" ;;
    --watch)           MODE="watch" ;;
    --decrypt-keys)    MODE="decrypt-keys" ;;
    --decrypt-tokens)  MODE="decrypt-tokens" ;;
    --status)          MODE="status" ;;
    --verify)          OPT_VERIFY=true ;;
    --snapshot)        OPT_SNAPSHOT=true ;;
    --token-renew)     OPT_TOKEN_RENEW=true ;;
    --wait)            OPT_WAIT=true ;;
    --json)            OPT_JSON=true ;;
    --no-audit)        OPT_NO_AUDIT=false ;;
    --timeout)         shift; TIMEOUT="${1:?--timeout requires a value}" ;;
    --timeout=*)       TIMEOUT="${1#--timeout=}" ;;
    --poll-interval)   shift; POLL_INTERVAL="${1:?--poll-interval requires a value}" ;;
    --poll-interval=*) POLL_INTERVAL="${1#--poll-interval=}" ;;
    --keys-file)       shift; KEYS_FILE="${1:?--keys-file requires a value}" ;;
    --keys-file=*)     KEYS_FILE="${1#--keys-file=}" ;;
    --tokens-file)     shift; TOKENS_FILE="${1:?--tokens-file requires a value}" ;;
    --tokens-file=*)   TOKENS_FILE="${1#--tokens-file=}" ;;
    --audit-log)       shift; AUDIT_LOG="${1:?--audit-log requires a value}" ;;
    --audit-log=*)     AUDIT_LOG="${1#--audit-log=}" ;;
    --key-index)       shift
                       IFS=',' read -ra KEY_INDICES <<< "${1:?--key-index requires a value}"
                       ;;
    --key-index=*)     IFS=',' read -ra KEY_INDICES <<< "${1#--key-index=}" ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

# ── Helpers ───────────────────────────────────────────────────────────────────
_ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log() {
  local msg="[vault-unseal] $*"
  echo "$msg"
  if [[ "$OPT_NO_AUDIT" == false ]]; then
    mkdir -p "$(dirname "$AUDIT_LOG")"
    echo "$(_ts) $msg" >> "$AUDIT_LOG" 2>/dev/null || true
  fi
}

err() {
  local msg="[vault-unseal] ERROR: $*"
  echo "$msg" >&2
  if [[ "$OPT_NO_AUDIT" == false ]]; then
    mkdir -p "$(dirname "$AUDIT_LOG")"
    echo "$(_ts) $msg" >> "$AUDIT_LOG" 2>/dev/null || true
  fi
}

# Emit JSON result to stdout (for --json flag); always exit after
emit_json() {
  local status="$1" sealed="$2" message="$3"
  printf '{"timestamp":"%s","status":"%s","sealed":%s,"vault_addr":"%s","message":"%s"}\n' \
    "$(_ts)" "$status" "$sealed" "$VAULT_ADDR" "$message"
}

# Get Vault sealed status: prints "true" or "false", or "unreachable"
vault_sealed() {
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$VAULT_ADDR/v1/sys/health" 2>/dev/null || echo 000)
  case "$code" in
    200|429) echo "false" ;;   # active / standby — unsealed
    503)     echo "true"  ;;   # sealed
    000|*)   echo "unreachable" ;;
  esac
}

# Get full Vault status JSON
vault_status_json() {
  "$VAULT_BIN" status -format=json 2>/dev/null || echo '{"error":"vault status failed"}'
}

# Check if initialised
vault_initialised() {
  curl -sf "$VAULT_ADDR/v1/sys/init" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('initialized','false'))" 2>/dev/null \
    || echo "false"
}

# Wait for Vault process to be reachable
wait_for_vault() {
  local deadline=$(( $(date +%s) + TIMEOUT ))
  log "Waiting for Vault at $VAULT_ADDR (timeout: ${TIMEOUT}s)..."
  while true; do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "$VAULT_ADDR/v1/sys/health" 2>/dev/null || echo 000)
    # 200=active 429=standby 501=uninitialised 503=sealed — all mean process is up
    if [[ "$code" =~ ^(200|429|472|473|501|503)$ ]]; then
      log "Vault reachable (HTTP $code)."
      return 0
    fi
    if (( $(date +%s) >= deadline )); then
      err "Vault not reachable after ${TIMEOUT}s."
      [[ "$OPT_JSON" == true ]] && emit_json "error" "true" "Vault unreachable after ${TIMEOUT}s"
      exit 3
    fi
    sleep 5
  done
}

# Decrypt the AES-256-CBC key file
decrypt_file() {
  local infile="$1" passphrase="$2"
  base64 -d "$infile" \
    | openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "pass:$passphrase" 2>/dev/null \
    || { err "Decryption failed — wrong passphrase or corrupted file."; exit 4; }
}

# Extract a named field from decrypted content (e.g. UNSEAL_KEY_2)
extract_field() {
  local content="$1" field="$2"
  printf '%s' "$content" | grep "^${field}=" | head -1 | cut -d= -f2-
}

# Get passphrase: from env if set, otherwise prompt
get_passphrase() {
  if [[ -n "${UNSEAL_PASSPHRASE:-}" ]]; then
    printf '%s' "$UNSEAL_PASSPHRASE"
    return
  fi
  local pw
  read -r -s -p "Passphrase to decrypt $KEYS_FILE: " pw </dev/tty; echo >/dev/tty
  printf '%s' "$pw"
}

# Apply one unseal key with retry
apply_unseal_key() {
  local key="$1" label="$2"
  local attempt=0
  while (( attempt < 3 )); do
    if "$VAULT_BIN" operator unseal "$key" > /dev/null 2>&1; then
      return 0
    fi
    (( attempt++ ))
    [[ $attempt -lt 3 ]] && sleep 2
  done
  err "Failed to apply $label after 3 attempts."
  return 1
}

# Renew a token, ignoring failures (token may have expired)
renew_token() {
  local name="$1" token="$2"
  if VAULT_TOKEN="$token" "$VAULT_BIN" token renew > /dev/null 2>&1; then
    log "  Renewed token: $name"
  else
    log "  WARNING: Could not renew $name token (may be expired or insufficient permission)"
  fi
}

# ── Snapshot ──────────────────────────────────────────────────────────────────
take_snapshot() {
  if [[ -z "${VAULT_TOKEN:-}" ]]; then
    log "WARNING: VAULT_TOKEN not set — skipping snapshot."
    return
  fi
  local snap_dir="deploy/vault/snapshots"
  mkdir -p "$snap_dir"
  local snap_file="${snap_dir}/vault-snapshot-$(_ts | tr ':' '-').snap"
  if "$VAULT_BIN" operator raft snapshot save "$snap_file" > /dev/null 2>&1; then
    log "Snapshot saved: $snap_file"
    # Keep only the last 10 snapshots
    ls -t "${snap_dir}"/*.snap 2>/dev/null | tail -n +11 | xargs -r rm --
  else
    log "WARNING: Snapshot failed (Vault may use file storage, not raft — this is expected)"
  fi
}

# ── Verify ────────────────────────────────────────────────────────────────────
verify_vault() {
  log "Verifying Vault health..."

  # 1. Status check
  local sealed
  sealed=$(vault_sealed)
  if [[ "$sealed" != "false" ]]; then
    err "Verify: Vault reports sealed=$sealed after unseal attempt."
    return 1
  fi
  log "  ✓ Vault is unsealed"

  # 2. Token self-lookup (requires VAULT_TOKEN)
  if [[ -n "${VAULT_TOKEN:-}" ]]; then
    if "$VAULT_BIN" token lookup > /dev/null 2>&1; then
      log "  ✓ Token valid"
    else
      log "  WARNING: Token lookup failed (token may be expired)"
    fi
  fi

  # 3. KV mount reachable
  if "$VAULT_BIN" secrets list 2>/dev/null | grep -q "^secret/"; then
    log "  ✓ KV v2 mount at secret/ accessible"
  else
    log "  WARNING: KV mount not found or not accessible with current token"
  fi

  # 4. Audit log enabled
  if [[ -n "${VAULT_TOKEN:-}" ]]; then
    if "$VAULT_BIN" audit list 2>/dev/null | grep -q "file"; then
      log "  ✓ File audit log enabled"
    else
      log "  WARNING: File audit log not enabled. Run: vault audit enable file file_path=/vault/logs/audit.log"
    fi
  fi

  log "Verification complete."
}

# ── Core unseal logic (used by interactive, from-file, and watch modes) ───────
do_unseal_from_file() {
  local passphrase="$1"
  [[ -f "$KEYS_FILE" ]] || { err "Keys file not found: $KEYS_FILE"; exit 4; }

  local decrypted
  decrypted=$(decrypt_file "$KEYS_FILE" "$passphrase")

  local keys=()
  for idx in "${KEY_INDICES[@]}"; do
    local key
    key=$(extract_field "$decrypted" "UNSEAL_KEY_${idx}")
    [[ -n "$key" ]] || { err "UNSEAL_KEY_${idx} not found in decrypted file."; exit 4; }
    keys+=("$key")
  done

  log "Applying ${#keys[@]} unseal keys (indices: ${KEY_INDICES[*]})..."
  local i=1
  for key in "${keys[@]}"; do
    apply_unseal_key "$key" "key ${KEY_INDICES[$((i-1))]}"
    log "  Applied key $i/${#keys[@]}"
    (( i++ ))
  done

  # Scrub
  unset decrypted keys key passphrase
}

do_unseal_interactive() {
  local count=${#KEY_INDICES[@]}
  log "Enter $count unseal keys (need ${count}-of-5 threshold)."
  log "Tip: decrypt your key file first with --decrypt-keys"
  echo

  local i=1
  while (( i <= count )); do
    local key
    read -r -s -p "  Unseal key $i/$count: " key </dev/tty; echo >/dev/tty
    [[ -n "$key" ]] || { echo "  (empty — try again)"; continue; }
    apply_unseal_key "$key" "key $i"
    log "  Applied key $i/$count"
    unset key
    (( i++ ))
  done
}

do_token_renew() {
  [[ -f "$TOKENS_FILE" ]] || { log "WARNING: $TOKENS_FILE not found — skipping token renewal."; return; }
  local passphrase
  passphrase=$(get_passphrase)
  local decrypted
  decrypted=$(decrypt_file "$TOKENS_FILE" "$passphrase")

  local app_token admin_token
  app_token=$(extract_field    "$decrypted" "VAULT_APP_TOKEN")
  admin_token=$(extract_field  "$decrypted" "VAULT_ADMIN_TOKEN")

  [[ -n "$app_token"   ]] && renew_token "tranc3-app"   "$app_token"
  [[ -n "$admin_token" ]] && renew_token "tranc3-admin" "$admin_token"

  unset decrypted passphrase app_token admin_token
}

# ── MODE: status ──────────────────────────────────────────────────────────────
if [[ "$MODE" == "status" ]]; then
  if [[ "$OPT_JSON" == true ]]; then
    vault_status_json
  else
    "$VAULT_BIN" status || true
  fi
  sealed=$(vault_sealed)
  [[ "$sealed" == "false" ]] && exit 0
  [[ "$sealed" == "true"  ]] && exit 2
  exit 3
fi

# ── MODE: decrypt-keys ────────────────────────────────────────────────────────
if [[ "$MODE" == "decrypt-keys" ]]; then
  [[ -f "$KEYS_FILE" ]] || { err "$KEYS_FILE not found."; exit 4; }
  PW=$(get_passphrase)
  decrypt_file "$KEYS_FILE" "$PW"
  exit 0
fi

# ── MODE: decrypt-tokens ─────────────────────────────────────────────────────
if [[ "$MODE" == "decrypt-tokens" ]]; then
  [[ -f "$TOKENS_FILE" ]] || { err "$TOKENS_FILE not found."; exit 4; }
  PW=$(get_passphrase)
  decrypt_file "$TOKENS_FILE" "$PW"
  exit 0
fi

# ── All unseal modes: wait + init check ──────────────────────────────────────
[[ "$OPT_WAIT" == true ]] && wait_for_vault

# Verify reachable without full wait
code=$(curl -s -o /dev/null -w "%{http_code}" "$VAULT_ADDR/v1/sys/health" 2>/dev/null || echo 000)
if [[ "$code" == "000" ]]; then
  if [[ "$OPT_WAIT" == false ]]; then
    err "Vault not reachable at $VAULT_ADDR. Add --wait to retry."
    [[ "$OPT_JSON" == true ]] && emit_json "error" "true" "Vault not reachable"
    exit 3
  fi
  wait_for_vault
fi

# Check initialised
if [[ "$(vault_initialised)" != "true" ]]; then
  err "Vault is not initialised. Run: ./scripts/vault-init.sh"
  [[ "$OPT_JSON" == true ]] && emit_json "error" "true" "Vault not initialised"
  exit 5
fi

# ── MODE: watch ───────────────────────────────────────────────────────────────
if [[ "$MODE" == "watch" ]]; then
  log "Watch mode: polling every ${POLL_INTERVAL}s. Press Ctrl-C to stop."

  # For watch mode, get passphrase once upfront
  WATCH_PASSPHRASE=$(get_passphrase)

  unseal_count=0
  while true; do
    sealed=$(vault_sealed)
    case "$sealed" in
      false)
        : # already unsealed, nothing to do
        ;;
      true)
        log "Vault is sealed — unsealing..."
        do_unseal_from_file "$WATCH_PASSPHRASE"
        sealed_after=$(vault_sealed)
        if [[ "$sealed_after" == "false" ]]; then
          (( unseal_count++ ))
          log "Unseal #${unseal_count} complete at $(_ts)"
          [[ "$OPT_VERIFY"      == true ]] && verify_vault
          [[ "$OPT_TOKEN_RENEW" == true ]] && do_token_renew
        else
          err "Unseal attempt failed — Vault still sealed."
        fi
        ;;
      unreachable)
        log "Vault unreachable — waiting for container to start..."
        ;;
    esac
    sleep "$POLL_INTERVAL"
  done
fi

# ── Already unsealed? ─────────────────────────────────────────────────────────
SEALED=$(vault_sealed)
if [[ "$SEALED" == "false" ]]; then
  log "Vault is already unsealed."
  [[ "$OPT_JSON" == true ]] && emit_json "ok" "false" "Already unsealed"
  [[ "$OPT_VERIFY"      == true ]] && verify_vault
  [[ "$OPT_TOKEN_RENEW" == true ]] && do_token_renew
  exit 0
fi

if [[ "$SEALED" == "unreachable" ]]; then
  err "Vault not reachable."
  [[ "$OPT_JSON" == true ]] && emit_json "error" "true" "Vault not reachable"
  exit 3
fi

# ── Optional pre-unseal snapshot ─────────────────────────────────────────────
[[ "$OPT_SNAPSHOT" == true ]] && take_snapshot

# ── MODE: from-file ───────────────────────────────────────────────────────────
if [[ "$MODE" == "from-file" ]]; then
  PASSPHRASE=$(get_passphrase)
  do_unseal_from_file "$PASSPHRASE"
  unset PASSPHRASE
fi

# ── MODE: interactive (default) ──────────────────────────────────────────────
if [[ "$MODE" == "interactive" ]]; then
  do_unseal_interactive
fi

# ── Post-unseal: confirm, verify, renew ──────────────────────────────────────
SEALED_AFTER=$(vault_sealed)
if [[ "$SEALED_AFTER" != "false" ]]; then
  err "Vault is still sealed after applying keys. Check that your keys are correct."
  [[ "$OPT_JSON" == true ]] && emit_json "error" "true" "Still sealed after unseal attempt"
  exit 1
fi

log "Vault unsealed successfully at $(_ts)"
[[ "$OPT_VERIFY"      == true ]] && verify_vault
[[ "$OPT_TOKEN_RENEW" == true ]] && do_token_renew

if [[ "$OPT_JSON" == true ]]; then
  emit_json "ok" "false" "Unsealed successfully"
fi

exit 0

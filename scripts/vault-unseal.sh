#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# vault-unseal.sh — Unseal Vault after a restart
#
# Modes:
#   ./scripts/vault-unseal.sh                   # interactive: prompts for 3 keys
#   ./scripts/vault-unseal.sh --from-file       # decrypt vault-keys.enc and use keys 1-3
#   ./scripts/vault-unseal.sh --decrypt-keys    # print decrypted keys file to stdout
#   ./scripts/vault-unseal.sh --decrypt-tokens  # print decrypted tokens file to stdout
#   ./scripts/vault-unseal.sh --status          # just print Vault status
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_BIN="${VAULT_BIN:-vault}"
KEYS_ENC="deploy/vault/vault-keys.enc"
TOKENS_ENC="deploy/vault/vault-tokens.enc"
MODE="interactive"

for arg in "$@"; do
  case "$arg" in
    --from-file)      MODE="from-file" ;;
    --decrypt-keys)   MODE="decrypt-keys" ;;
    --decrypt-tokens) MODE="decrypt-tokens" ;;
    --status)         MODE="status" ;;
  esac
done

log() { echo "[vault-unseal] $*"; }
err() { echo "[vault-unseal] ERROR: $*" >&2; exit 1; }

decrypt_file() {
  local infile="$1" passphrase="$2"
  base64 -d "$infile" \
    | openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "pass:$passphrase"
}

# ── Status mode ───────────────────────────────────────────────────────────────
if [[ "$MODE" == "status" ]]; then
  "$VAULT_BIN" status || true
  exit 0
fi

# ── Check if already unsealed ─────────────────────────────────────────────────
SEALED=$("$VAULT_BIN" status -format=json 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed','true'))" 2>/dev/null \
  || echo "true")

if [[ "$SEALED" == "false" ]]; then
  log "Vault is already unsealed."
  exit 0
fi

# ── Decrypt-only modes ────────────────────────────────────────────────────────
if [[ "$MODE" == "decrypt-keys" ]]; then
  [[ -f "$KEYS_ENC" ]] || err "$KEYS_ENC not found."
  read -r -s -p "Passphrase: " PW; echo
  decrypt_file "$KEYS_ENC" "$PW"
  exit 0
fi

if [[ "$MODE" == "decrypt-tokens" ]]; then
  [[ -f "$TOKENS_ENC" ]] || err "$TOKENS_ENC not found."
  read -r -s -p "Passphrase: " PW; echo
  decrypt_file "$TOKENS_ENC" "$PW"
  exit 0
fi

# ── Unseal from encrypted file ────────────────────────────────────────────────
if [[ "$MODE" == "from-file" ]]; then
  [[ -f "$KEYS_ENC" ]] || err "$KEYS_ENC not found. Provide keys manually."
  read -r -s -p "Passphrase to decrypt $KEYS_ENC: " PASSPHRASE; echo

  DECRYPTED=$(decrypt_file "$KEYS_ENC" "$PASSPHRASE")

  KEY1=$(printf '%s' "$DECRYPTED" | grep "^UNSEAL_KEY_1=" | cut -d= -f2-)
  KEY2=$(printf '%s' "$DECRYPTED" | grep "^UNSEAL_KEY_2=" | cut -d= -f2-)
  KEY3=$(printf '%s' "$DECRYPTED" | grep "^UNSEAL_KEY_3=" | cut -d= -f2-)

  [[ -n "$KEY1" && -n "$KEY2" && -n "$KEY3" ]] \
    || err "Could not extract keys — wrong passphrase or corrupted file?"

  log "Unsealing with keys 1, 2, 3..."
  "$VAULT_BIN" operator unseal "$KEY1" > /dev/null
  "$VAULT_BIN" operator unseal "$KEY2" > /dev/null
  "$VAULT_BIN" operator unseal "$KEY3" > /dev/null

  unset PASSPHRASE DECRYPTED KEY1 KEY2 KEY3
  log "Vault unsealed."
  "$VAULT_BIN" status
  exit 0
fi

# ── Interactive unseal (default) ──────────────────────────────────────────────
log "Vault is sealed. Enter 3 unseal keys (3-of-5 threshold)."
log "Keys are in vault-keys.enc — decrypt with: --decrypt-keys"
echo

for i in 1 2 3; do
  read -r -s -p "  Unseal key $i/3: " KEY; echo
  "$VAULT_BIN" operator unseal "$KEY" > /dev/null
  unset KEY
done

log "Vault unsealed."
"$VAULT_BIN" status

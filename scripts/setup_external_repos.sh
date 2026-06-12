#!/usr/bin/env bash
# scripts/setup_external_repos.sh
# Wire Magna-Carta and CranBania as git submodules, then configure env vars.
# Run once after initial clone: bash scripts/setup_external_repos.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Trancendos External Repo Setup ==="
echo ""

# ── Magna Carta ───────────────────────────────────────────────────────────────
MC_TARGET="compliance/magna-carta"
MC_URL="https://github.com/Trancendos/Magna-Carta.git"

if [ -d "$MC_TARGET/.git" ] || git submodule status "$MC_TARGET" &>/dev/null 2>&1; then
  echo "[Magna-Carta] Already registered — pulling latest..."
  git submodule update --remote "$MC_TARGET" || git -C "$MC_TARGET" pull origin main
else
  echo "[Magna-Carta] Adding submodule at $MC_TARGET ..."
  mkdir -p "$(dirname "$MC_TARGET")"
  git submodule add "$MC_URL" "$MC_TARGET"
fi
echo "[Magna-Carta] ✓ $MC_TARGET"

# ── CranBania ─────────────────────────────────────────────────────────────────
CB_TARGET="workers/cranbania"
CB_URL="https://github.com/Trancendos/CranBania.git"

if [ -d "$CB_TARGET/.git" ] || git submodule status "$CB_TARGET" &>/dev/null 2>&1; then
  echo "[CranBania]   Already registered — pulling latest..."
  git submodule update --remote "$CB_TARGET" || git -C "$CB_TARGET" pull origin main
else
  echo "[CranBania]   Adding submodule at $CB_TARGET ..."
  # Remove any stub files tracked in the index (Dockerfile/README were added as plain files
  # in this PR; git submodule add requires the path to be absent from the git index).
  if git ls-files --error-unmatch "$CB_TARGET" &>/dev/null 2>&1; then
    echo "[CranBania]   Removing tracked stub files from index before submodule init..."
    git rm -rf --cached "$CB_TARGET" || true
  fi
  rm -rf "$CB_TARGET"
  git submodule add "$CB_URL" "$CB_TARGET"
fi
echo "[CranBania]   ✓ $CB_TARGET"

# ── .env wiring check ─────────────────────────────────────────────────────────
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  echo ""
  echo "=== Checking .env for Magna Carta settings ==="
  if ! grep -q "MAGNA_CARTA_CONFIG_PATH" "$ENV_FILE"; then
    # Ensure trailing newline before appending so values aren't concatenated onto existing lines
    [ -n "$(tail -c1 "$ENV_FILE")" ] && printf '\n' >> "$ENV_FILE"
    echo "MAGNA_CARTA_ENABLED=false" >> "$ENV_FILE"
    echo "MAGNA_CARTA_CONFIG_PATH=./compliance/magna-carta/config/magna_carta_config.json" >> "$ENV_FILE"
    echo "MAGNA_CARTA_REGISTER_PATH=./compliance/magna-carta/compliance/magna_carta_register.yaml" >> "$ENV_FILE"
    echo "MAGNA_CARTA_AUDIT=true" >> "$ENV_FILE"
    echo "[.env] Magna Carta vars appended."
  else
    echo "[.env] Magna Carta vars already present."
  fi
else
  echo ""
  echo "No .env found — copy .env.example to .env and fill in values."
  echo "Magna Carta vars are pre-populated in .env.example."
fi

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. To activate Magna Carta: set MAGNA_CARTA_ENABLED=true in .env"
echo "  2. To run compliance check with MC rows:"
echo "     python -m src.compliance.checker --magna-carta compliance/magna-carta/compliance/magna_carta_register.yaml"
echo "  3. To build CranBania / The Town Hall:"
echo "     docker-compose -f docker-compose.production.yml build cranbania"
echo "  4. To run the full stack including The Town Hall:"
echo "     docker-compose -f docker-compose.production.yml up -d cranbania"
echo ""

#!/usr/bin/env bash
# scripts/push_cranbania_upstream.sh
# Push the CranBania submodule to github.com/Trancendos/CranBania
# and update the submodule pointer in the Tranc3 main repo.
#
# Usage:
#   GH_PAT=<token> bash scripts/push_cranbania_upstream.sh
#   or: bash scripts/push_cranbania_upstream.sh  (uses existing git credential helper)
#
# What it does:
#   1. Pushes workers/cranbania main branch to GitHub via HTTPS + PAT
#   2. Stages the new submodule pointer in the parent repo
#   3. Creates a commit + pushes to the current branch of Tranc3

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUBMODULE_DIR="$REPO_ROOT/workers/cranbania"
REMOTE_URL="https://github.com/Trancendos/CranBania.git"

# ── Auth ─────────────────────────────────────────────────────────────────────
if [ -n "${GH_PAT:-}" ]; then
  AUTHED_URL="https://${GH_PAT}@github.com/Trancendos/CranBania.git"
else
  AUTHED_URL="$REMOTE_URL"
fi

# ── Preflight ─────────────────────────────────────────────────────────────────
if ! git -C "$SUBMODULE_DIR" rev-parse HEAD &>/dev/null; then
  echo "❌  workers/cranbania is not a valid git repo. Run: git submodule update --init"
  exit 1
fi

AHEAD=$(git -C "$SUBMODULE_DIR" rev-list origin/main..HEAD --count 2>/dev/null || echo "?")
if [ "$AHEAD" = "0" ]; then
  echo "✅  workers/cranbania is already up to date with origin/main — nothing to push."
  exit 0
fi

echo "ℹ  workers/cranbania is $AHEAD commit(s) ahead of origin/main."
echo "   Pushing to $REMOTE_URL …"

# ── Push submodule ────────────────────────────────────────────────────────────
git -C "$SUBMODULE_DIR" push "$AUTHED_URL" HEAD:main

PUSHED_SHA=$(git -C "$SUBMODULE_DIR" rev-parse HEAD)
PUSHED_SHORT=$(git -C "$SUBMODULE_DIR" rev-parse --short HEAD)
echo "✅  Pushed CranBania @ $PUSHED_SHORT"

# ── Update parent repo submodule pointer ──────────────────────────────────────
cd "$REPO_ROOT"
git add workers/cranbania

if git diff --cached --quiet; then
  echo "✅  Tranc3 submodule pointer already at $PUSHED_SHORT — no commit needed."
else
  git commit -m "chore(submodule): advance CranBania to ${PUSHED_SHORT}

Pushed CranBania/main to github.com/Trancendos/CranBania.
Full SHA: ${PUSHED_SHA}

https://claude.ai/code"
  echo "✅  Committed submodule update in Tranc3."
fi

echo ""
echo "Done. Next steps:"
echo "  git push  (to push the Tranc3 submodule-pointer commit)"

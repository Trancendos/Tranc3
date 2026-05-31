#!/usr/bin/env bash
# Tranc3 Citadel — one-click gate + deploy (Linux / macOS / Git Bash)
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/citadel_deploy_all.py "$@"

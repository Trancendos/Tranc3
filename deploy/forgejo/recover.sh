#!/usr/bin/env bash
# deploy/forgejo/recover.sh
# The Workshop (Forgejo) recovery + self-heal — run ON the trancendos.com server.
#
# Use when https://trancendos.com/the-workshop is unreachable (e.g. Cloudflare
# HTTP 522 = origin didn't respond). Unlike bootstrap.sh (first-time install),
# this is a fast, idempotent diagnose-and-restart for an already-provisioned
# host. It walks the request path Cloudflare -> nginx/Caddy -> Forgejo container
# from the inside out, restarts whatever layer is down, and clearly reports what
# it healed vs. what needs a human (host down, DNS, or Cloudflare-side).
#
# Usage:
#   bash deploy/forgejo/recover.sh          # diagnose + heal
#   bash deploy/forgejo/recover.sh --check  # diagnose only, change nothing
#
# Exit codes: 0 = Workshop reachable locally after run; 1 = still down (see report).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
INTERNAL="http://127.0.0.1:3456"          # Forgejo published port (see compose)
HEALTH="${INTERNAL}/-/health"
PROXY_LOCAL="http://127.0.0.1/the-workshop/"  # through the local reverse proxy
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[recover]${NC} $*"; }
ok()   { echo -e "${GREEN}[recover] ✓${NC} $*"; }
warn() { echo -e "${YELLOW}[recover] ⚠${NC} $*"; }
err()  { echo -e "${RED}[recover] ✗${NC} $*" >&2; }

HEALED=()
NEEDS_HUMAN=()

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# ── Layer 0: Docker daemon ───────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  err "docker is not installed on this host."
  NEEDS_HUMAN+=("Install Docker + docker compose, then run deploy/forgejo/bootstrap.sh")
  printf '\n'; err "Cannot proceed without Docker."; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  warn "Docker daemon not responding."
  if [[ $CHECK_ONLY -eq 0 ]]; then
    log "Starting docker…"
    sudo systemctl start docker 2>/dev/null && sudo systemctl enable docker 2>/dev/null \
      && ok "docker started" && HEALED+=("docker daemon started + enabled on boot") \
      || NEEDS_HUMAN+=("Could not start docker — check: systemctl status docker")
  else
    NEEDS_HUMAN+=("Docker daemon down — start with: sudo systemctl start docker")
  fi
fi

# ── Layer 1: containers up ───────────────────────────────────────────────────
running() { docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }
if running the-workshop && running the-workshop-runner; then
  ok "Containers already running (the-workshop, the-workshop-runner)."
else
  warn "One or both Workshop containers are not running."
  if [[ $CHECK_ONLY -eq 0 ]]; then
    log "Bringing the stack up (docker compose up -d)…"
    if compose up -d 2>&1 | tail -3; then
      ok "compose up issued"
      HEALED+=("docker compose up -d")
    else
      NEEDS_HUMAN+=("compose up failed — check: docker compose -f $COMPOSE_FILE logs")
    fi
  else
    NEEDS_HUMAN+=("Containers down — start with: docker compose -f $COMPOSE_FILE up -d")
  fi
fi

# ── Layer 2: Forgejo healthy on the published port ───────────────────────────
wait_health() {
  local n=0
  until curl -sf --max-time 5 "$HEALTH" >/dev/null 2>&1; do
    n=$((n + 1)); [[ $n -gt 20 ]] && return 1; printf '.'; sleep 3
  done; echo ""; return 0
}
if curl -sf --max-time 5 "$HEALTH" >/dev/null 2>&1; then
  ok "Forgejo healthy at ${INTERNAL} (/-/health 200)."
else
  warn "Forgejo not answering on ${INTERNAL}."
  if [[ $CHECK_ONLY -eq 0 ]]; then
    log "Waiting up to 60s for Forgejo health…"
    if wait_health; then
      ok "Forgejo became healthy."
      HEALED+=("Forgejo health recovered")
    else
      err "Forgejo still unhealthy. Recent logs:"
      docker logs --tail 30 the-workshop 2>&1 | sed 's/^/    /' || true
      NEEDS_HUMAN+=("Forgejo unhealthy — inspect: docker logs the-workshop (disk full? db lock? bad config?)")
    fi
  else
    NEEDS_HUMAN+=("Forgejo down on ${INTERNAL} — inspect: docker logs the-workshop")
  fi
fi

# ── Layer 3: reverse proxy (nginx / Caddy) ───────────────────────────────────
proxy_unit=""
if systemctl list-unit-files 2>/dev/null | grep -q '^nginx\.service'; then proxy_unit="nginx";
elif systemctl list-unit-files 2>/dev/null | grep -q '^caddy\.service'; then proxy_unit="caddy"; fi

if [[ -n "$proxy_unit" ]]; then
  if systemctl is-active --quiet "$proxy_unit"; then
    ok "Reverse proxy ($proxy_unit) is active."
  else
    warn "Reverse proxy ($proxy_unit) is not active."
    if [[ $CHECK_ONLY -eq 0 ]]; then
      sudo systemctl restart "$proxy_unit" 2>/dev/null \
        && ok "$proxy_unit restarted" && HEALED+=("$proxy_unit restarted") \
        || NEEDS_HUMAN+=("Could not restart $proxy_unit — check: systemctl status $proxy_unit")
    else
      NEEDS_HUMAN+=("$proxy_unit down — start with: sudo systemctl restart $proxy_unit")
    fi
  fi
  # Does the proxy actually route to Forgejo locally?
  if curl -sf --max-time 5 -o /dev/null "$PROXY_LOCAL" 2>/dev/null; then
    ok "Reverse proxy routes to Forgejo locally (${PROXY_LOCAL})."
  else
    warn "Reverse proxy is up but not routing /the-workshop/ to 127.0.0.1:3456."
    NEEDS_HUMAN+=("Proxy not routing — confirm deploy/forgejo/${proxy_unit}-the-workshop.conf is included and reload $proxy_unit")
  fi
else
  warn "No nginx/Caddy service detected on this host."
  NEEDS_HUMAN+=("No reverse proxy found — Cloudflare can't reach Forgejo. Install nginx/Caddy and add deploy/forgejo/nginx-the-workshop.conf (or caddy-the-workshop.conf).")
fi

# ── Report ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}──────── The Workshop recovery report ────────${NC}"
if [[ ${#HEALED[@]} -gt 0 ]]; then
  echo -e "${GREEN}Healed:${NC}"; for h in "${HEALED[@]}"; do echo "  ✓ $h"; done
fi
if [[ ${#NEEDS_HUMAN[@]} -gt 0 ]]; then
  echo -e "${YELLOW}Needs attention:${NC}"; for n in "${NEEDS_HUMAN[@]}"; do echo "  ⚠ $n"; done
fi

if curl -sf --max-time 5 "$HEALTH" >/dev/null 2>&1; then
  echo ""
  ok "Forgejo is reachable locally. If https://trancendos.com/the-workshop is STILL 522:"
  echo "    → the local origin is healthy, so the fault is above the host:"
  echo "      • reverse proxy not routing the subpath (see above), or"
  echo "      • Cloudflare origin/DNS (check the CF dashboard: DNS record, SSL/TLS mode,"
  echo "        and that the origin server's public IP/port 443 is reachable), or"
  echo "      • host firewall blocking 443 from Cloudflare IPs."
  exit 0
else
  echo ""
  err "Forgejo is NOT reachable locally after recovery — resolve the 'Needs attention' items above."
  echo "    Most common causes: host was rebooted (install the systemd unit — see RUNBOOK),"
  echo "    disk full (df -h; docker system df), or a corrupt/locked SQLite db."
  exit 1
fi

#!/usr/bin/env bash
# deploy/forgejo/recover.sh
# The Workshop (Forgejo) recovery + self-heal — run ON the trancendos.com server.
#
# Use when https://trancendos.com/the-workshop is unreachable (e.g. Cloudflare
# HTTP 522 = origin didn't respond). Unlike bootstrap.sh (first-time install),
# this is a fast, idempotent diagnose-and-restart for an already-provisioned host.
#
# TOPOLOGY-AWARE + SAFE. This platform documents TWO Forgejo deployments that
# share the named `forgejo-data` volume:
#   • production  — docker-compose.production.yml, container `trancendos-forgejo`
#                   behind Traefik (`tranc3-traefik`), no host port 3456.
#   • standalone  — deploy/forgejo/docker-compose.yml, container `the-workshop`
#                   on 127.0.0.1:3456 behind nginx/Caddy.
# The script DETECTS which stack is actually deployed and operates only on that
# one. It will **never** `compose up` a second Forgejo against the shared volume:
# if it can't unambiguously identify the deployed stack, it refuses and reports.
#
# Usage:
#   bash deploy/forgejo/recover.sh          # diagnose + self-heal
#   bash deploy/forgejo/recover.sh --check  # diagnose only, change nothing
#
# Exit codes: 0 = Forgejo healthy after run; 1 = still down / needs a human.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[recover]${NC} $*"; }
ok()   { echo -e "${GREEN}[recover] ✓${NC} $*"; }
warn() { echo -e "${YELLOW}[recover] ⚠${NC} $*"; }
err()  { echo -e "${RED}[recover] ✗${NC} $*" >&2; }

HEALED=(); NEEDS_HUMAN=()

# Root already? then no sudo needed (also works inside the systemd unit).
SUDO=""
if [[ ${EUID:-$(id -u)} -ne 0 ]] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

report_and_exit() {
  local code="$1"
  echo ""
  echo -e "${CYAN}──────── The Workshop recovery report ────────${NC}"
  if [[ ${#HEALED[@]} -gt 0 ]]; then
    echo -e "${GREEN}Healed:${NC}"; for h in "${HEALED[@]}"; do echo "  ✓ $h"; done
  fi
  if [[ ${#NEEDS_HUMAN[@]} -gt 0 ]]; then
    echo -e "${YELLOW}Needs attention:${NC}"; for n in "${NEEDS_HUMAN[@]}"; do echo "  ⚠ $n"; done
  fi
  exit "$code"
}

# ── Preflight: required tools ────────────────────────────────────────────────
for tool in docker curl; do
  command -v "$tool" >/dev/null 2>&1 || {
    err "'$tool' is not installed on this host."
    NEEDS_HUMAN+=("Install $tool, then re-run. (Fresh host? use deploy/forgejo/bootstrap.sh)")
    report_and_exit 1
  }
done
docker compose version >/dev/null 2>&1 || {
  err "The 'docker compose' plugin is not available."
  NEEDS_HUMAN+=("Install the docker compose v2 plugin.")
  report_and_exit 1
}

# ── Layer 0: Docker daemon (re-verify after any start attempt) ────────────────
if ! docker info >/dev/null 2>&1; then
  warn "Docker daemon not responding."
  if [[ $CHECK_ONLY -eq 0 ]]; then
    log "Starting docker…"
    $SUDO systemctl start docker 2>/dev/null || true
    $SUDO systemctl enable docker 2>/dev/null || true
    if docker info >/dev/null 2>&1; then
      ok "docker daemon is up"
      HEALED+=("docker daemon started + enabled on boot")
    else
      err "Docker daemon still not usable after start attempt."
      NEEDS_HUMAN+=("Docker daemon won't come up — check: systemctl status docker; journalctl -u docker (bad config / cgroup driver?)")
      report_and_exit 1
    fi
  else
    NEEDS_HUMAN+=("Docker daemon down — start with: sudo systemctl start docker")
    report_and_exit 1
  fi
fi

# ── Topology detection (the safety core) ─────────────────────────────────────
cont_exists()  { docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }
cont_running() { docker ps    --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }
vol_exists()   { docker volume ls --format '{{.Name}}' 2>/dev/null | grep -qx "$1"; }

PROD_FORGEJO="trancendos-forgejo"
STANDALONE_FORGEJO="the-workshop"

prod=0; standalone=0
cont_exists "$PROD_FORGEJO" && prod=1
cont_exists "$STANDALONE_FORGEJO" && standalone=1

if (( prod && standalone )); then
  err "BOTH Forgejo stacks exist ($PROD_FORGEJO and $STANDALONE_FORGEJO)."
  NEEDS_HUMAN+=("Two Forgejo stacks are present on this host — they share the 'forgejo-data' volume and must not both run. Stop the wrong one (docker rm the stale container/stack) before recovering. NOT auto-starting anything.")
  report_and_exit 1
elif (( prod )); then
  TOPO="production"
  COMPOSE_FILE="${REPO_ROOT}/docker-compose.production.yml"
  FORGEJO="$PROD_FORGEJO"
  RUNNER="trancendos-forgejo-runner"
  UP_SERVICES=(traefik forgejo forgejo-runner)
  PROXY_KIND="traefik"; PROXY_CONTAINER="tranc3-traefik"
elif (( standalone )); then
  TOPO="standalone"
  COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
  FORGEJO="$STANDALONE_FORGEJO"
  RUNNER="the-workshop-runner"
  UP_SERVICES=()   # small file — bring the whole thing up
  PROXY_KIND="webserver"; PROXY_CONTAINER=""
else
  # Neither known Forgejo container exists. Do NOT guess-and-start — that is how
  # a second server ends up on the shared volume (the whole point of this guard).
  if vol_exists "forgejo-data"; then
    warn "A 'forgejo-data' volume exists but neither $PROD_FORGEJO nor $STANDALONE_FORGEJO is present."
    NEEDS_HUMAN+=("Forgejo data exists but no known container — NOT auto-starting to avoid a conflicting second server. Bring up the CORRECT stack by hand: production → docker compose -f docker-compose.production.yml up -d traefik forgejo forgejo-runner ; standalone → docker compose -f deploy/forgejo/docker-compose.yml up -d")
  else
    warn "No Forgejo container and no forgejo-data volume — looks like a fresh host."
    NEEDS_HUMAN+=("First-time install: bash deploy/forgejo/bootstrap.sh (standalone), or bring up the Citadel stack (docker-compose.production.yml).")
  fi
  report_and_exit 1
fi
ok "Detected topology: ${TOPO} (forgejo=${FORGEJO}, proxy=${PROXY_KIND})."

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# ── Layer 1: bring the detected stack up (never a different one) ──────────────
if cont_running "$FORGEJO" && cont_running "$RUNNER"; then
  ok "Containers already running (${FORGEJO}, ${RUNNER})."
elif [[ $CHECK_ONLY -eq 1 ]]; then
  NEEDS_HUMAN+=("Containers down — start with: docker compose -f $COMPOSE_FILE up -d ${UP_SERVICES[*]}")
else
  # Preserve the runner's currently-deployed image so `up` can't silently revert
  # the custom flyctl/wrangler runner to the upstream fallback in ${RUNNER_IMAGE:-…}.
  local_img="$(docker inspect -f '{{.Config.Image}}' "$RUNNER" 2>/dev/null || true)"
  if [[ -n "$local_img" ]]; then
    export RUNNER_IMAGE="$local_img"
  elif docker image inspect trancendos/act-runner:latest >/dev/null 2>&1; then
    export RUNNER_IMAGE="trancendos/act-runner:latest"
  fi
  log "Bringing up ${TOPO} stack (docker compose up -d ${UP_SERVICES[*]})…"
  # Capture status separately from output so a compose failure isn't masked by
  # the tail pipe, while still showing the operator a useful tail on failure.
  up_out="$(compose up -d "${UP_SERVICES[@]}" 2>&1)"; up_status=$?
  printf '%s\n' "$up_out" | tail -5
  if [[ $up_status -eq 0 ]]; then
    ok "compose up issued"
    HEALED+=("docker compose up -d (${TOPO})")
  else
    err "compose up failed (exit $up_status)."
    NEEDS_HUMAN+=("compose up failed — full output above; also: docker compose -f $COMPOSE_FILE logs ${FORGEJO}")
  fi
fi

# ── Layer 2: Forgejo health (topology-agnostic — no host-port assumption) ─────
# Prefer the container's own healthcheck status; fall back to hitting the health
# endpoint *inside* the container so it works whether or not a host port exists.
forgejo_healthy() {
  local hs
  hs="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$FORGEJO" 2>/dev/null || true)"
  [[ "$hs" == "healthy" ]] && return 0
  docker exec "$FORGEJO" sh -c \
    'wget -qO- http://localhost:3000/-/health >/dev/null 2>&1 || curl -sf http://localhost:3000/-/health >/dev/null 2>&1' \
    >/dev/null 2>&1
}
if forgejo_healthy; then
  ok "Forgejo (${FORGEJO}) is healthy."
elif [[ $CHECK_ONLY -eq 1 ]]; then
  NEEDS_HUMAN+=("Forgejo unhealthy — inspect: docker logs ${FORGEJO}")
else
  log "Waiting for Forgejo health (~60s)…"
  n=0
  until forgejo_healthy; do
    n=$((n + 1)); [[ $n -ge 20 ]] && break; printf '.'; sleep 3
  done
  echo ""
  if forgejo_healthy; then
    ok "Forgejo became healthy."
    HEALED+=("Forgejo health recovered")
  else
    err "Forgejo still unhealthy. Recent logs:"
    docker logs --tail 30 "$FORGEJO" 2>&1 | sed 's/^/    /' || true
    NEEDS_HUMAN+=("Forgejo unhealthy — inspect: docker logs ${FORGEJO} (disk full? db lock? bad config?)")
  fi
fi

# ── Layer 3: reverse proxy ───────────────────────────────────────────────────
if [[ "$PROXY_KIND" == "traefik" ]]; then
  if cont_running "$PROXY_CONTAINER"; then
    ok "Traefik ($PROXY_CONTAINER) is running."
  else
    warn "Traefik ($PROXY_CONTAINER) is not running."
    if [[ $CHECK_ONLY -eq 0 ]]; then
      compose up -d traefik >/dev/null 2>&1 \
        && ok "Traefik started" && HEALED+=("Traefik restarted") \
        || NEEDS_HUMAN+=("Could not start Traefik — check: docker compose -f $COMPOSE_FILE logs traefik")
    else
      NEEDS_HUMAN+=("Traefik down — start with: docker compose -f $COMPOSE_FILE up -d traefik")
    fi
  fi
else
  # standalone → nginx/Caddy systemd service
  proxy_unit=""
  if systemctl list-unit-files 2>/dev/null | grep -q '^nginx\.service'; then proxy_unit="nginx";
  elif systemctl list-unit-files 2>/dev/null | grep -q '^caddy\.service'; then proxy_unit="caddy"; fi
  if [[ -n "$proxy_unit" ]]; then
    if systemctl is-active --quiet "$proxy_unit"; then
      ok "Reverse proxy ($proxy_unit) is active."
    else
      warn "Reverse proxy ($proxy_unit) is not active."
      if [[ $CHECK_ONLY -eq 0 ]]; then
        $SUDO systemctl restart "$proxy_unit" 2>/dev/null \
          && ok "$proxy_unit restarted" && HEALED+=("$proxy_unit restarted") \
          || NEEDS_HUMAN+=("Could not restart $proxy_unit — check: systemctl status $proxy_unit")
      else
        NEEDS_HUMAN+=("$proxy_unit down — start with: sudo systemctl restart $proxy_unit")
      fi
    fi
  else
    warn "No nginx/Caddy service detected for the standalone stack."
    NEEDS_HUMAN+=("No reverse proxy found — add deploy/forgejo/nginx-the-workshop.conf (or caddy-the-workshop.conf) and reload it.")
  fi
fi

# Does the proxy actually route the subpath to Forgejo? Query /-/health THROUGH
# the proxy over HTTPS with the real Host header and -k, requiring a literal 200.
# (A plain http:// check can false-positive on an http->https 301, which `-f`
# treats as success.)
proxy_code="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 \
  -H 'Host: trancendos.com' 'https://127.0.0.1/the-workshop/-/health' 2>/dev/null || echo 000)"
if [[ "$proxy_code" == "200" ]]; then
  ok "Reverse proxy routes /the-workshop/ to Forgejo (HTTP 200 through the proxy)."
else
  warn "Proxy did not return 200 for /the-workshop/-/health (got ${proxy_code})."
  NEEDS_HUMAN+=("Proxy not routing the subpath — confirm the /the-workshop route/location is present and reload the proxy (${PROXY_KIND}).")
fi

# ── Final verdict ────────────────────────────────────────────────────────────
if forgejo_healthy; then
  echo ""
  ok "Forgejo is healthy locally (${TOPO})."
  if [[ "$proxy_code" != "200" ]]; then
    echo "    → Forgejo is fine but the proxy path isn't returning 200 — fix layer 3 above."
  else
    echo "    → If https://trancendos.com/the-workshop is STILL 522 despite a healthy origin:"
    echo "      the fault is above the host — Cloudflare DNS/SSL-mode/origin-IP, or a host"
    echo "      firewall blocking 443 from Cloudflare IPs. See deploy/forgejo/RUNBOOK.md §7."
  fi
  report_and_exit 0
else
  echo ""
  err "Forgejo is NOT healthy after recovery — resolve the items above."
  echo "    Common causes: disk full (df -h; docker system df), a locked/corrupt SQLite db,"
  echo "    or the host was rebooted without the boot unit (see deploy/forgejo/the-workshop.service)."
  report_and_exit 1
fi

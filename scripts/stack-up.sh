#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# stack-up.sh — Bring up the Citadel Docker Compose stack and validate all
#               P0/P1 workers respond correctly to /health
#
# USAGE
#   ./scripts/stack-up.sh [OPTIONS]
#
# OPTIONS
#   --build            Build images before starting (default: skip if present)
#   --pull             Pull latest base images before building
#   --profile PROFILE  Service profile: core (default), p0, p1, full
#   --validate-only    Skip compose up — only run health validation
#   --no-validate      Skip health validation (just start the stack)
#   --timeout N        Seconds to wait for all services (default: 600)
#   --json             Emit JSON health report to stdout at the end
#   --log-failures     Capture and print docker logs for failed containers
#   --restart-failed   Attempt docker compose restart on containers that fail health
#   --env-file PATH    .env file to pass to compose (default: .env.production)
#   --dry-run          Print what would be done without doing it
#
# PROFILES
#   p0     tranc3-backend + tranc3-ai + infinity-ws + infinity-auth
#          (minimum — two P0 workers + core infra)
#   core   p0 + all P1 workers + valkey + traefik + vault  (DEFAULT)
#   full   core + all P2 workers + all platform tooling
#
# EXIT CODES
#   0  All services in selected profile are healthy
#   1  One or more P0 services unhealthy
#   2  One or more P1 services unhealthy, all P0 healthy
#   3  Startup error (compose failed, env missing, etc.)
#
# EXAMPLES
#   # Standard deploy:
#   ./scripts/stack-up.sh
#
#   # Rebuild images, full profile, capture logs on failure:
#   ./scripts/stack-up.sh --build --profile full --log-failures
#
#   # CI: non-interactive, JSON output, fail if any P0 unhealthy:
#   ./scripts/stack-up.sh --timeout 300 --json --log-failures
#
#   # Just run the health check against an already-running stack:
#   ./scripts/stack-up.sh --validate-only
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE=".env.production"
PROFILE="core"
TIMEOUT=600
OPT_BUILD=false
OPT_PULL=false
OPT_VALIDATE_ONLY=false
OPT_NO_VALIDATE=false
OPT_JSON=false
OPT_LOG_FAILURES=false
OPT_RESTART_FAILED=false
OPT_DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)           OPT_BUILD=true ;;
    --pull)            OPT_PULL=true ;;
    --validate-only)   OPT_VALIDATE_ONLY=true ;;
    --no-validate)     OPT_NO_VALIDATE=true ;;
    --json)            OPT_JSON=true ;;
    --log-failures)    OPT_LOG_FAILURES=true ;;
    --restart-failed)  OPT_RESTART_FAILED=true ;;
    --dry-run)         OPT_DRY_RUN=true ;;
    --timeout)         shift; TIMEOUT="${1:?--timeout requires a value}" ;;
    --timeout=*)       TIMEOUT="${1#--timeout=}" ;;
    --profile)         shift; PROFILE="${1:?--profile requires a value}" ;;
    --profile=*)       PROFILE="${1#--profile=}" ;;
    --env-file)        shift; ENV_FILE="${1:?--env-file requires a value}" ;;
    --env-file=*)      ENV_FILE="${1#--env-file=}" ;;
    *) echo "Unknown option: $1" >&2; exit 3 ;;
  esac
  shift
done

# ── Colours ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_GREEN="\033[0;32m"; C_RED="\033[0;31m"; C_YELLOW="\033[1;33m"
  C_BLUE="\033[0;34m"; C_CYAN="\033[0;36m"; C_BOLD="\033[1m"; C_RESET="\033[0m"
else
  C_GREEN=""; C_RED=""; C_YELLOW=""; C_BLUE=""; C_CYAN=""; C_BOLD=""; C_RESET=""
fi

log()  { echo -e "${C_BLUE}[stack-up]${C_RESET} $*"; }
ok()   { echo -e "${C_GREEN}[stack-up] ✓${C_RESET} $*"; }
warn() { echo -e "${C_YELLOW}[stack-up] ⚠${C_RESET} $*"; }
err()  { echo -e "${C_RED}[stack-up] ✗${C_RESET} $*" >&2; }
step() { echo -e "\n${C_BOLD}${C_CYAN}══ $* ══${C_RESET}"; }
ts()   { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

dry() {
  if [[ "$OPT_DRY_RUN" == true ]]; then
    echo -e "${C_YELLOW}[DRY-RUN]${C_RESET} $*"
    return 0
  fi
  eval "$*"
}

# ── Service registry ──────────────────────────────────────────────────────────
# Format: "name|port|health_path|priority|container_name"
declare -a P0_SERVICES=(
  "tranc3-backend|8000|/health|P0|tranc3-backend"
  "tranc3-ai|8001|/health|P0|tranc3-ai-worker"
  "infinity-ws|8004|/health|P0|infinity-ws-worker"
  "infinity-auth|8005|/health|P0|infinity-auth-worker"
)

declare -a P1_SERVICES=(
  "users-service|8006|/health|P1|users-service-worker"
  "monitoring|8007|/health|P1|monitoring-worker"
  "notifications|8008|/health|P1|notifications-worker"
  "infinity-ai|8009|/health|P1|infinity-ai-worker"
  "infinity-admin|8044|/health|P1|infinity-admin-worker"
  "infinity-portal|8042|/health|P1|infinity-portal-worker"
  "infinity-one|8043|/health|P1|infinity-one-worker"
  "infinity-shards|8045|/health|P1|infinity-shards-worker"
  "infinity-bridge|8070|/health|P1|infinity-bridge-worker"
  "hive-service|8060|/health|P1|hive-service-worker"
)

declare -a INFRA_SERVICES=(
  "valkey|6379||INF|tranc3-valkey"
  "vault|8200|/v1/sys/health|INF|tranc3-vault"
  "traefik|80|/ping|INF|tranc3-traefik"
)

# ── Profile → service lists ───────────────────────────────────────────────────
case "$PROFILE" in
  p0)
    COMPOSE_SERVICES=(tranc3-backend tranc3-ai-worker infinity-ws-worker infinity-auth-worker
                      tranc3-valkey tranc3-vault tranc3-traefik)
    VALIDATE_GROUPS=("P0")
    ;;
  core)
    COMPOSE_SERVICES=(
      tranc3-backend tranc3-ai-worker infinity-void-worker trancendos-api-gateway-worker
      infinity-ws-worker infinity-auth-worker
      users-service-worker monitoring-worker notifications-worker infinity-ai-worker
      infinity-admin-worker infinity-portal-worker infinity-one-worker
      infinity-shards-worker infinity-bridge-worker hive-service-worker
      tranc3-valkey tranc3-vault tranc3-traefik tranc3-ollama
      tranc3-prometheus tranc3-grafana
    )
    VALIDATE_GROUPS=("P0" "P1")
    ;;
  full)
    COMPOSE_SERVICES=()  # empty = all services in compose file
    VALIDATE_GROUPS=("P0" "P1")
    ;;
  *)
    err "Unknown profile: $PROFILE. Use: p0, core, full"
    exit 3
    ;;
esac

# ── Pre-flight checks ─────────────────────────────────────────────────────────
step "Pre-flight"

[[ -f "$COMPOSE_FILE" ]] || { err "Not found: $COMPOSE_FILE"; exit 3; }

if [[ "$OPT_VALIDATE_ONLY" == false ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE not found — generating..."
    dry "./scripts/generate_production_env.sh"
  else
    ok "$ENV_FILE present"
  fi

  # Quick sanity: check required keys are non-empty
  missing_keys=()
  for key in SECRET_KEY JWT_SECRET; do
    val=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
    [[ -z "$val" || "$val" == "LOAD_FROM_VAULT" ]] && missing_keys+=("$key")
  done
  if [[ ${#missing_keys[@]} -gt 0 ]]; then
    err "Empty required env vars in $ENV_FILE: ${missing_keys[*]}"
    err "Run: ./scripts/generate_production_env.sh --force"
    exit 3
  fi
  ok "Required env vars present"

  if command -v docker &>/dev/null; then
    docker info &>/dev/null || { err "Docker daemon not running."; exit 3; }
    ok "Docker daemon reachable"
  else
    err "docker not found on PATH"
    exit 3
  fi
fi

# ── Pull / Build ──────────────────────────────────────────────────────────────
if [[ "$OPT_VALIDATE_ONLY" == false ]]; then
  if [[ "$OPT_PULL" == true ]]; then
    step "Pull base images"
    if [[ ${#COMPOSE_SERVICES[@]} -gt 0 ]]; then
      dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE pull ${COMPOSE_SERVICES[*]}" || true
    else
      dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE pull" || true
    fi
  fi

  if [[ "$OPT_BUILD" == true ]]; then
    step "Build images"
    if [[ ${#COMPOSE_SERVICES[@]} -gt 0 ]]; then
      dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE build ${COMPOSE_SERVICES[*]}"
    else
      dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE build"
    fi
  fi

  # ── Start infrastructure tier first ────────────────────────────────────────
  step "Start infrastructure (valkey, vault, traefik, ollama)"
  dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d \
    tranc3-valkey tranc3-vault tranc3-traefik tranc3-ollama"

  log "Waiting 8s for infrastructure to be ready..."
  [[ "$OPT_DRY_RUN" == false ]] && sleep 8

  # ── Vault unseal check ──────────────────────────────────────────────────────
  if [[ "$OPT_DRY_RUN" == false ]]; then
    vault_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8200/v1/sys/health" 2>/dev/null || echo 000)
    case "$vault_code" in
      200|429)
        ok "Vault: unsealed"
        ;;
      503)
        warn "Vault is sealed — attempting auto-unseal..."
        if [[ -f "deploy/vault/vault-keys.enc" && -n "${UNSEAL_PASSPHRASE:-}" ]]; then
          UNSEAL_PASSPHRASE="$UNSEAL_PASSPHRASE" ./scripts/vault-unseal.sh --from-file --wait || \
            warn "Auto-unseal failed — run: ./scripts/vault-unseal.sh --from-file"
        else
          warn "Set UNSEAL_PASSPHRASE and ensure deploy/vault/vault-keys.enc exists for auto-unseal."
          warn "Run manually: ./scripts/vault-unseal.sh --from-file"
        fi
        ;;
      501)
        warn "Vault not initialised — run: ./scripts/vault-init.sh --load-env $ENV_FILE"
        ;;
      *)
        warn "Vault not reachable (HTTP $vault_code) — workers will start without Vault secrets"
        ;;
    esac
  fi

  # ── Start platform workers ──────────────────────────────────────────────────
  step "Start platform workers (profile: $PROFILE)"
  if [[ ${#COMPOSE_SERVICES[@]} -gt 0 ]]; then
    dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d ${COMPOSE_SERVICES[*]}"
  else
    dry "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d"
  fi
fi

# ── Health validation ─────────────────────────────────────────────────────────
if [[ "$OPT_NO_VALIDATE" == true ]]; then
  ok "Stack started. Health validation skipped (--no-validate)."
  exit 0
fi

step "Health validation (timeout: ${TIMEOUT}s)"

# Collect all services to check based on profile
declare -a SERVICES_TO_CHECK=()
for group in "${VALIDATE_GROUPS[@]}"; do
  case "$group" in
    P0) SERVICES_TO_CHECK+=("${P0_SERVICES[@]}") ;;
    P1) SERVICES_TO_CHECK+=("${P1_SERVICES[@]}") ;;
  esac
done

# Track results
declare -A RESULTS      # name → "healthy|unhealthy|timeout|unreachable"
declare -A RESULT_BODY  # name → response body snippet
declare -A RESULT_CODE  # name → HTTP status code
declare -A RESULT_MS    # name → response time ms

probe_service() {
  local name="$1" port="$2" path="$3"
  local url="http://127.0.0.1:${port}${path}"
  local start_ms end_ms elapsed_ms
  start_ms=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))")

  local http_code body
  if command -v curl &>/dev/null; then
    body=$(curl -sf --max-time 5 -w "\n__HTTP_CODE__:%{http_code}" "$url" 2>/dev/null || echo "__HTTP_CODE__:000")
    http_code=$(printf '%s' "$body" | grep "__HTTP_CODE__:" | tail -1 | cut -d: -f2)
    body=$(printf '%s' "$body" | grep -v "__HTTP_CODE__:" | head -3 | tr '\n' ' ')
  else
    http_code=$(python3 -c "
import urllib.request, sys
try:
  r = urllib.request.urlopen('$url', timeout=5)
  print(r.status)
except Exception as e:
  print(0)
" 2>/dev/null || echo 0)
    body=""
  fi

  end_ms=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))")
  elapsed_ms=$(( end_ms - start_ms ))

  RESULT_CODE["$name"]="$http_code"
  RESULT_BODY["$name"]="$body"
  RESULT_MS["$name"]="$elapsed_ms"

  if [[ "$http_code" =~ ^(200|201|204)$ ]]; then
    RESULTS["$name"]="healthy"
    return 0
  elif [[ "$http_code" == "000" || "$http_code" == "0" ]]; then
    RESULTS["$name"]="unreachable"
    return 1
  else
    RESULTS["$name"]="unhealthy"
    return 1
  fi
}

# Wait loop: poll all services until all healthy or timeout
deadline=$(( $(date +%s) + TIMEOUT ))
all_healthy=false
declare -a still_waiting=()

# Initialise all as "waiting"
for svc_def in "${SERVICES_TO_CHECK[@]}"; do
  IFS='|' read -r name port path priority container <<< "$svc_def"
  RESULTS["$name"]="waiting"
  still_waiting+=("$svc_def")
done

log "Waiting for ${#SERVICES_TO_CHECK[@]} services to become healthy..."
last_report=$(date +%s)

while true; do
  now=$(date +%s)

  declare -a still_waiting_next=()
  for svc_def in "${still_waiting[@]}"; do
    IFS='|' read -r name port path priority container <<< "$svc_def"
    if probe_service "$name" "$port" "$path"; then
      ok "$(printf '%-30s' "$name") ${C_GREEN}healthy${C_RESET} (HTTP ${RESULT_CODE[$name]}, ${RESULT_MS[$name]}ms)"
    else
      still_waiting_next+=("$svc_def")
    fi
  done
  still_waiting=("${still_waiting_next[@]+"${still_waiting_next[@]}"}")

  if [[ ${#still_waiting[@]} -eq 0 ]]; then
    all_healthy=true
    break
  fi

  if (( now >= deadline )); then
    # Mark remaining as timed out
    for svc_def in "${still_waiting[@]}"; do
      IFS='|' read -r name port path priority container <<< "$svc_def"
      RESULTS["$name"]="timeout"
    done
    break
  fi

  # Progress report every 30 seconds
  if (( now - last_report >= 30 )); then
    waiting_names=()
    for svc_def in "${still_waiting[@]}"; do
      IFS='|' read -r name _ _ _ _ <<< "$svc_def"
      waiting_names+=("$name")
    done
    warn "Still waiting ($(( deadline - now ))s remaining): ${waiting_names[*]}"
    last_report=$now
  fi

  sleep 5
done

# ── Capture logs for failed containers ────────────────────────────────────────
if [[ "$OPT_LOG_FAILURES" == true || "$OPT_RESTART_FAILED" == true ]]; then
  for svc_def in "${SERVICES_TO_CHECK[@]}"; do
    IFS='|' read -r name port path priority container <<< "$svc_def"
    status="${RESULTS[$name]:-timeout}"
    if [[ "$status" != "healthy" ]]; then
      if [[ "$OPT_LOG_FAILURES" == true ]]; then
        echo ""
        echo -e "${C_RED}── Logs: $container (last 30 lines) ──${C_RESET}"
        docker compose -f "$COMPOSE_FILE" logs --no-color --tail=30 "$container" 2>/dev/null || \
          docker logs --tail=30 "$container" 2>/dev/null || \
          echo "  (no logs available)"
        echo ""
      fi
      if [[ "$OPT_RESTART_FAILED" == true ]]; then
        warn "Restarting $container..."
        docker compose -f "$COMPOSE_FILE" restart "$container" 2>/dev/null || true
      fi
    fi
  done
fi

# ── Final scorecard ───────────────────────────────────────────────────────────
step "Health Scorecard"

p0_pass=0; p0_fail=0
p1_pass=0; p1_fail=0
declare -a failed_p0=() failed_p1=()
report_lines=()

for svc_def in "${SERVICES_TO_CHECK[@]}"; do
  IFS='|' read -r name port path priority container <<< "$svc_def"
  status="${RESULTS[$name]:-timeout}"
  code="${RESULT_CODE[$name]:-?}"
  ms="${RESULT_MS[$name]:-?}"
  body="${RESULT_BODY[$name]:-}"

  case "$status" in
    healthy)
      icon="${C_GREEN}✓${C_RESET}"
      ;;
    unhealthy)
      icon="${C_RED}✗${C_RESET}"
      ;;
    timeout)
      icon="${C_RED}⏱${C_RESET}"
      code="TMO"
      ;;
    unreachable)
      icon="${C_RED}✗${C_RESET}"
      code="ERR"
      ;;
    *)
      icon="${C_YELLOW}?${C_RESET}"
      ;;
  esac

  line=$(printf "  %b %-30s %s  HTTP %-3s  %sms  %s" \
    "$icon" "$name" "$priority" "$code" "$ms" "$(printf '%s' "$body" | cut -c1-60)")
  echo -e "$line"
  report_lines+=("$name|$priority|$status|$code|$ms")

  if [[ "$priority" == "P0" ]]; then
    [[ "$status" == "healthy" ]] && (( p0_pass++ )) || { (( p0_fail++ )); failed_p0+=("$name"); }
  elif [[ "$priority" == "P1" ]]; then
    [[ "$status" == "healthy" ]] && (( p1_pass++ )) || { (( p1_fail++ )); failed_p1+=("$name"); }
  fi
done

total_pass=$(( p0_pass + p1_pass ))
total_fail=$(( p0_fail + p1_fail ))
total=$(( total_pass + total_fail ))

echo ""
echo -e "${C_BOLD}  Summary${C_RESET}"
echo -e "  P0: ${C_GREEN}${p0_pass} healthy${C_RESET} / ${C_RED}${p0_fail} failed${C_RESET}  │  P1: ${C_GREEN}${p1_pass} healthy${C_RESET} / ${C_RED}${p1_fail} failed${C_RESET}  │  Total: ${total_pass}/${total}"
echo ""

# ── JSON output ───────────────────────────────────────────────────────────────
if [[ "$OPT_JSON" == true ]]; then
  python3 - <<PYJSON
import json, sys

services = []
for line in """$(printf '%s\n' "${report_lines[@]}")""".strip().splitlines():
    if not line: continue
    parts = line.split('|')
    if len(parts) >= 5:
        services.append({
            "name": parts[0],
            "priority": parts[1],
            "status": parts[2],
            "http_code": parts[3],
            "response_ms": parts[4],
        })

report = {
    "timestamp": "$(ts)",
    "profile": "$PROFILE",
    "p0": {"healthy": $p0_pass, "failed": $p0_fail, "failed_names": $(python3 -c "import json; print(json.dumps('${failed_p0[*]:-}'.split()))")},
    "p1": {"healthy": $p1_pass, "failed": $p1_fail, "failed_names": $(python3 -c "import json; print(json.dumps('${failed_p1[*]:-}'.split()))")},
    "total": {"healthy": $total_pass, "failed": $total_fail},
    "services": services,
}
print(json.dumps(report, indent=2))
PYJSON
fi

# ── Save report to file ───────────────────────────────────────────────────────
REPORT_DIR="logs"
mkdir -p "$REPORT_DIR"
REPORT_FILE="${REPORT_DIR}/stack-health-$(date -u +%Y%m%d-%H%M%S).txt"
{
  echo "Citadel Stack Health Report — $(ts)"
  echo "Profile: $PROFILE  Timeout: ${TIMEOUT}s"
  echo ""
  printf '%s\n' "${report_lines[@]}"
  echo ""
  echo "P0: ${p0_pass}/${#P0_SERVICES[@]} healthy | P1: ${p1_pass}/${#P1_SERVICES[@]} healthy"
} > "$REPORT_FILE"
log "Report saved: $REPORT_FILE"

# ── Exit code ─────────────────────────────────────────────────────────────────
if [[ $p0_fail -gt 0 ]]; then
  err "FAILED: ${p0_fail} P0 service(s) unhealthy: ${failed_p0[*]}"
  err "These are critical — the platform cannot function without them."
  exit 1
fi

if [[ $p1_fail -gt 0 ]]; then
  warn "DEGRADED: ${p1_fail} P1 service(s) unhealthy: ${failed_p1[*]}"
  warn "Core platform is operational but some features are unavailable."
  exit 2
fi

ok "All ${total_pass} services in profile '${PROFILE}' are healthy."
exit 0

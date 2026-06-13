#!/usr/bin/env bash
# check_stack.sh — Bootstrap validation for Trancendos platform
#
# Pings every P0 and P1 service /health endpoint and exits non-zero
# if any P0 service is unreachable or unhealthy.
# P1 failures are reported as warnings but do not fail the script.
#
# Usage:
#   ./scripts/check_stack.sh                  # ping localhost ports
#   BASE_URL=http://192.168.1.10 ./scripts/check_stack.sh
#   TIMEOUT=10 ./scripts/check_stack.sh
#
# Exit codes:
#   0 — all P0 services healthy (P1 may have warnings)
#   1 — one or more P0 services down or unhealthy
#
# Environment variables:
#   BASE_URL     Base URL prefix (default: http://localhost)
#   TIMEOUT      curl timeout in seconds (default: 5)
#   VERBOSE      Set to 1 for full response bodies (default: 0)

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
TIMEOUT="${TIMEOUT:-5}"
VERBOSE="${VERBOSE:-0}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Service registry ───────────────────────────────────────────────────────────
# Format: "priority|name|port|path"
SERVICES=(
    # P0 — critical; failure = exit 1
    "P0|tranc3-backend|8000|/health"
    "P0|infinity-ws (The Nexus)|8004|/health"
    "P0|infinity-auth (Infinity)|8005|/health"
    # P1 — important; failure = warning only
    "P1|infinity-portal-service|8042|/health"
    "P1|infinity-one-service|8043|/health"
    "P1|infinity-admin-service|8044|/health"
    "P1|infinity-shards-service|8045|/health"
    "P1|infinity-bridge-service|8070|/health"
    "P1|cranbania (Town Hall)|8071|/health"
    "P1|users-service|8006|/health"
    "P1|monitoring|8007|/health"
    "P1|notifications|8008|/health"
    "P1|infinity-ai|8009|/health"
)

# ── Helpers ────────────────────────────────────────────────────────────────────

_check() {
    local priority="$1" name="$2" port="$3" path="$4"
    local url="${BASE_URL}:${port}${path}"
    local http_code body

    if [ "$VERBOSE" = "1" ]; then
        body=$(curl -sf --max-time "$TIMEOUT" -w "\n%{http_code}" "$url" 2>/dev/null || echo -e "\nERR")
        http_code=$(echo "$body" | tail -1)
        body=$(echo "$body" | head -n -1)
    else
        http_code=$(curl -so /dev/null --max-time "$TIMEOUT" -w "%{http_code}" "$url" 2>/dev/null || echo "ERR")
    fi

    if [ "$http_code" = "200" ]; then
        printf "${GREEN}  ✓${RESET}  [${BOLD}%s${RESET}] %-40s %s\n" "$priority" "$name" "${url}"
        return 0
    else
        if [ "$priority" = "P0" ]; then
            printf "${RED}  ✗${RESET}  [${BOLD}%s${RESET}] %-40s %s  (HTTP %s)\n" "$priority" "$name" "${url}" "$http_code"
        else
            printf "${YELLOW}  ⚠${RESET}  [${BOLD}%s${RESET}] %-40s %s  (HTTP %s)\n" "$priority" "$name" "${url}" "$http_code"
        fi
        if [ "$VERBOSE" = "1" ] && [ -n "${body:-}" ]; then
            echo "         └─ $body"
        fi
        return 1
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────

echo ""
printf "${CYAN}${BOLD}Trancendos Stack — Health Check${RESET}\n"
printf "${CYAN}Base: %s   Timeout: %ss${RESET}\n\n" "$BASE_URL" "$TIMEOUT"

p0_fail=0
p1_fail=0
p0_pass=0
p1_pass=0

for entry in "${SERVICES[@]}"; do
    IFS='|' read -r priority name port path <<< "$entry"
    if _check "$priority" "$name" "$port" "$path"; then
        if [ "$priority" = "P0" ]; then p0_pass=$((p0_pass + 1)); else p1_pass=$((p1_pass + 1)); fi
    else
        if [ "$priority" = "P0" ]; then p0_fail=$((p0_fail + 1)); else p1_fail=$((p1_fail + 1)); fi
    fi
done

echo ""
printf "${BOLD}Summary:${RESET}\n"
printf "  P0: %d/%d healthy\n" "$p0_pass" "$((p0_pass + p0_fail))"
printf "  P1: %d/%d healthy\n" "$p1_pass" "$((p1_pass + p1_fail))"
echo ""

if [ "$p0_fail" -gt 0 ]; then
    printf "${RED}${BOLD}FAIL${RESET} — %d P0 service(s) down. Stack is NOT ready.\n\n" "$p0_fail"
    exit 1
fi

if [ "$p1_fail" -gt 0 ]; then
    printf "${YELLOW}${BOLD}WARN${RESET} — All P0 healthy; %d P1 service(s) degraded.\n\n" "$p1_fail"
    exit 0
fi

printf "${GREEN}${BOLD}OK${RESET} — All P0 and P1 services healthy.\n\n"
exit 0

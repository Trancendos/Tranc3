#!/usr/bin/env bash
# scripts/security_scan.sh
# Local security scan — mirrors .forgejo/workflows/security-scan.yml (subset).
# Run from project root: bash scripts/security_scan.sh

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BANDIT_PATHS="src/ api.py workers/infinity-auth workers/infinity-ws workers/api-gateway"

PASS=0; FAIL=0; WARN=0
_ok()   { echo "  ✓  $*"; ((PASS++)) || true; }
_fail() { echo "  ✗  $*"; ((FAIL++)) || true; }
_warn() { echo "  ⚠  $*"; ((WARN++)) || true; }
_sec()  { echo; echo "── $* ──────────────────────────────────"; }

_sec "1. pip-audit (CVE scan — CI warn-only)"
if command -v pip-audit &>/dev/null; then
    pip-audit --requirement requirements.txt --progress-spinner off && _ok "pip-audit completed" \
    || _warn "pip-audit reported CVEs (CI: continue-on-error)"
else
    _warn "pip-audit not installed (pip install pip-audit)"
fi

_sec "2. bandit (Python SAST — CI GATE)"
if command -v bandit &>/dev/null; then
    bandit -r $BANDIT_PATHS \
      --severity-level medium --confidence-level medium -q \
    && _ok "Bandit CI scope passed" \
    || _fail "Bandit medium+ issues (match security-scan.yml)"
else
    _warn "bandit not installed (pip install bandit)"
fi

_sec "3. ruff (CI warn-only)"
if command -v ruff &>/dev/null; then
    ruff check src/ api.py --select E,F,W --ignore E501 --exit-zero -q \
    && _ok "ruff check completed (warn-only)" \
    || _warn "ruff reported issues"
else
    _warn "ruff not installed"
fi

_sec "4. semgrep (CI GATE on ERROR)"
if command -v semgrep &>/dev/null; then
    semgrep --config auto --config p/fastapi --config p/python \
      --config p/owasp-top-ten --config p/sql-injection --config p/jwt \
      --severity ERROR --quiet src/ \
    && _ok "semgrep ERROR severity clean" \
    || _fail "semgrep ERROR findings"
else
    _warn "semgrep not installed (pip install semgrep)"
fi

_sec "5. gitleaks (secret detection)"
if command -v gitleaks &>/dev/null; then
    gitleaks detect --source . --log-level warn \
    && _ok "No secrets detected" \
    || _fail "Potential secrets detected — review output"
else
    _warn "gitleaks not installed"
fi

_sec "6. npm audit (Node.js / CF Workers — matches security-scan.yml levels)"
_npm_audit_dir() {
    local wdir="$1"
    local level="$2"
    if [ ! -f "$wdir/package.json" ]; then
        return
    fi
    pushd "$wdir" >/dev/null
    if [ -f package-lock.json ]; then
        npm ci --prefer-offline 2>/dev/null || npm install --prefer-offline
    else
        npm install --prefer-offline
    fi
    npm audit --audit-level="$level" --prefer-offline 2>/dev/null \
    && _ok "$wdir: npm audit ($level) clean" \
    || _warn "$wdir: npm audit ($level) reported issues"
    popd >/dev/null
}
_npm_audit_dir cloudflare/tranc3-ai moderate
_npm_audit_dir cloudflare/infinity-void moderate
_npm_audit_dir cloudflare/trancendos-api-gateway high
_npm_audit_dir tranc3-bots moderate

_sec "7. trivy (config + fs — CI warn on config HIGH/CRITICAL)"
if command -v trivy &>/dev/null; then
    mkdir -p logs
    trivy config --severity HIGH,CRITICAL --format json --output logs/trivy-config-results.json . || true
    trivy config --severity HIGH,CRITICAL --exit-code 1 . \
    && _ok "trivy config: no HIGH/CRITICAL misconfigs" \
    || _warn "trivy config: HIGH/CRITICAL misconfigs (CI warns)"
    trivy fs --severity HIGH,CRITICAL --format json --output logs/trivy-fs-results.json . || true
    _ok "trivy fs scan completed (see logs/trivy-fs-results.json)"
else
    _warn "trivy not installed (see security-scan.yml install step)"
fi

echo
echo "══════════════════════════════════════════"
echo "  Security scan complete"
echo "  ✓ Pass: $PASS  ✗ Fail: $FAIL  ⚠ Warn: $WARN"
echo "══════════════════════════════════════════"

[ "$FAIL" -eq 0 ] || exit 1

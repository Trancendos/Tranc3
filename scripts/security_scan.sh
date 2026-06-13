#!/usr/bin/env bash
# scripts/security_scan.sh
# Local security scan — mirrors what The Workshop (Forgejo) runs in CI.
# Run from project root: bash scripts/security_scan.sh
#
# Requires: pip install pip-audit bandit safety
# Optional: pip install semgrep; install gitleaks from GitHub releases

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PASS=0; FAIL=0; WARN=0
_ok()   { echo "  ✓  $*"; ((PASS++)) || true; }
_fail() { echo "  ✗  $*"; ((FAIL++)) || true; }
_warn() { echo "  ⚠  $*"; ((WARN++)) || true; }
_sec()  { echo; echo "── $* ──────────────────────────────────"; }

_sec "1. pip-audit (CVE scan)"
if command -v pip-audit &>/dev/null; then
    pip-audit --requirement requirements.txt --progress-spinner off && _ok "No known CVEs in requirements.txt" \
    || _fail "CVEs detected — check output above"
else
    _warn "pip-audit not installed (pip install pip-audit)"
fi

_sec "2. bandit (Python SAST)"
if command -v bandit &>/dev/null; then
    bandit -r src/ -ll -ii -q && _ok "No high-severity issues found" \
    || _fail "Bandit found high-severity/confidence issues"
else
    _warn "bandit not installed (pip install bandit)"
fi

_sec "3. safety (dependency CVE database)"
if command -v safety &>/dev/null; then
    safety check --file requirements.txt -q && _ok "safety check passed" \
    || _warn "safety found issues (may include false positives)"
else
    _warn "safety not installed (pip install safety)"
fi

_sec "4. semgrep (OWASP semantic rules)"
if command -v semgrep &>/dev/null; then
    semgrep --config "p/owasp-top-ten" --config "p/sql-injection" \
            --severity ERROR --quiet src/ \
    && _ok "No semgrep OWASP issues" \
    || _fail "semgrep found issues"
else
    _warn "semgrep not installed (pip install semgrep)"
fi

_sec "5. gitleaks (secret detection)"
if command -v gitleaks &>/dev/null; then
    gitleaks detect --source . --log-level warn \
    && _ok "No secrets detected" \
    || _fail "Potential secrets detected — review output"
else
    _warn "gitleaks not installed (https://github.com/gitleaks/gitleaks/releases)"
fi

_sec "6. npm audit (Node.js / CF Workers)"
for wdir in cloudflare/tranc3-ai cloudflare/infinity-void web; do
    if [ -f "$wdir/package.json" ]; then
        pushd "$wdir" >/dev/null
        npm audit --audit-level=high --prefer-offline 2>/dev/null \
        && _ok "$wdir: no high-severity npm issues" \
        || _warn "$wdir: npm audit found issues"
        popd >/dev/null
    fi
done

_sec "7. Python syntax check (all src/*.py)"
python3 -m compileall src/ -q && _ok "All Python files compile cleanly" \
|| _fail "Syntax errors detected"

echo
echo "══════════════════════════════════════════"
echo "  Security scan complete"
echo "  ✓ Pass: $PASS  ✗ Fail: $FAIL  ⚠ Warn: $WARN"
echo "══════════════════════════════════════════"

[ "$FAIL" -eq 0 ] || exit 1

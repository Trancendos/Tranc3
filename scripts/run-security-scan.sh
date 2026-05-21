#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# TRANC3 — Unified Local Security Scanner
# Runs all security tools and generates a consolidated report
# Usage: ./scripts/run-security-scan.sh [--full] [--fix]
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

FULL_SCAN=false
FIX_MODE=false
EXIT_CODE=0

for arg in "$@"; do
    case $arg in
        --full) FULL_SCAN=true ;;
        --fix) FIX_MODE=true ;;
        --help) echo "Usage: $0 [--full] [--fix]"; exit 0 ;;
    esac
done

echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     TRANC3 — Unified Security Scanner               ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Bandit (Python SAST) ──────────────────────────────────────────
echo -e "${YELLOW}[1/6] Running Bandit (Python SAST)...${NC}"
if command -v bandit &>/dev/null; then
    BANDIT_COUNT=$(bandit -r src/ -c pyproject.toml -f json 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('results',[])))" 2>/dev/null || echo "error")
    if [ "$BANDIT_COUNT" = "0" ]; then
        echo -e "  ${GREEN}✅ Bandit: 0 issues found${NC}"
    else
        echo -e "  ${RED}❌ Bandit: $BANDIT_COUNT issues found${NC}"
        EXIT_CODE=1
        if [ "$FIX_MODE" = true ]; then
            echo -e "  ${YELLOW}  Running detailed report...${NC}"
            bandit -r src/ -c pyproject.toml -f txt 2>/dev/null || true
        fi
    fi
else
    echo -e "  ${YELLOW}⚠️  Bandit not installed. Run: pip install bandit[toml]${NC}"
fi

# ─── pip-audit (Dependency CVEs) ───────────────────────────────────
echo -e "${YELLOW}[2/6] Running pip-audit (dependency vulnerabilities)...${NC}"
if command -v pip-audit &>/dev/null; then
    PIP_AUDIT_OUTPUT=$(pip-audit -r requirements.txt --desc 2>&1 || true)
    if echo "$PIP_AUDIT_OUTPUT" | grep -q "No known vulnerabilities"; then
        echo -e "  ${GREEN}✅ pip-audit: No vulnerabilities found${NC}"
    else
        VULN_COUNT=$(echo "$PIP_AUDIT_OUTPUT" | grep -c "^torch\|^sentencepiece\|^numpy\|^cryptography\|^aiohttp" || echo "0")
        echo -e "  ${RED}❌ pip-audit: Vulnerabilities found${NC}"
        echo "$PIP_AUDIT_OUTPUT" | head -20
        EXIT_CODE=1
    fi
else
    echo -e "  ${YELLOW}⚠️  pip-audit not installed. Run: pip install pip-audit${NC}"
fi

# ─── Safety (Dependency Safety) ────────────────────────────────────
echo -e "${YELLOW}[3/6] Running Safety (dependency safety)...${NC}"
if command -v safety &>/dev/null; then
    SAFETY_OUTPUT=$(safety scan -r requirements.txt 2>&1 || true)
    if echo "$SAFETY_OUTPUT" | grep -q "0 vulnerabilities"; then
        echo -e "  ${GREEN}✅ Safety: No vulnerabilities found${NC}"
    else
        echo -e "  ${RED}❌ Safety: Vulnerabilities found${NC}"
        echo "$SAFETY_OUTPUT" | head -10
        EXIT_CODE=1
    fi
else
    echo -e "  ${YELLOW}⚠️  Safety not installed. Run: pip install safety${NC}"
fi

# ─── Gitleaks (Secret Detection) ───────────────────────────────────
echo -e "${YELLOW}[4/6] Running Gitleaks (secret detection)...${NC}"
if command -v gitleaks &>/dev/null; then
    GITLEAKS_OUTPUT=$(gitleaks detect --source . --no-git 2>&1 || true)
    if echo "$GITLEAKS_OUTPUT" | grep -q "no leaks found"; then
        echo -e "  ${GREEN}✅ Gitleaks: No secrets found${NC}"
    else
        echo -e "  ${RED}❌ Gitleaks: Secrets found!${NC}"
        echo "$GITLEAKS_OUTPUT"
        EXIT_CODE=1
    fi
else
    echo -e "  ${YELLOW}⚠️  Gitleaks not installed. See: https://github.com/gitleaks/gitleaks${NC}"
fi

# ─── Trivy (Container/FS Scan) ─────────────────────────────────────
echo -e "${YELLOW}[5/6] Running Trivy (filesystem scan)...${NC}"
if command -v trivy &>/dev/null; then
    TRIVY_OUTPUT=$(trivy fs --severity CRITICAL,HIGH . 2>&1 || true)
    if echo "$TRIVY_OUTPUT" | grep -q "Total: 0"; then
        echo -e "  ${GREEN}✅ Trivy: No critical/high vulnerabilities found${NC}"
    else
        echo -e "  ${RED}❌ Trivy: Critical/high vulnerabilities found${NC}"
        echo "$TRIVY_OUTPUT" | head -20
        EXIT_CODE=1
    fi
else
    echo -e "  ${YELLOW}⚠️  Trivy not installed. See: https://github.com/aquasecurity/trivy${NC}"
fi

# ─── Semgrep (Semantic Analysis) — full scan only ──────────────────
if [ "$FULL_SCAN" = true ]; then
    echo -e "${YELLOW}[6/6] Running Semgrep (semantic code analysis)...${NC}"
    if command -v semgrep &>/dev/null; then
        SEMGREP_OUTPUT=$(semgrep --config auto src/ 2>&1 || true)
        SEMGREP_FINDINGS=$(echo "$SEMGREP_OUTPUT" | grep -c "findings:" || echo "0")
        if [ "$SEMGREP_FINDINGS" = "0" ]; then
            echo -e "  ${GREEN}✅ Semgrep: No findings${NC}"
        else
            echo -e "  ${RED}❌ Semgrep: $SEMGREP_FINDINGS findings${NC}"
            EXIT_CODE=1
        fi
    else
        echo -e "  ${YELLOW}⚠️  Semgrep not installed. Run: pip install semgrep${NC}"
    fi
else
    echo -e "${YELLOW}[6/6] Semgrep: skipped (use --full to enable)${NC}"
fi

# ─── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All security checks passed!${NC}"
else
    echo -e "${RED}❌ Security issues found. See details above.${NC}"
fi
echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"

exit $EXIT_CODE

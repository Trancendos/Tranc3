# Tranc3 — Magna Carta Integration Guide

**Version:** 1.0.0 | **Date:** 2026-06-12
**Owner:** Trancendos Platform Engineering

## 1. Overview

This guide describes how to fully integrate the Magna Carta compliance framework into the Tranc3 platform, including staging enablement, middleware wiring, and compliance checker invocation.

## 2. Quick Start

```bash
# 1. Generate .env with Magna Carta enabled
python scripts/generate_env.py

# 2. Verify MAGNA_CARTA_ENABLED is set
grep MAGNA_CARTA_ENABLED .env
# → MAGNA_CARTA_ENABLED=true  (auto-set when submodule detected)

# 3. Check compliance score
make compliance-merged

# 4. Run full bootstrap
make setup-dev
```

## 3. Middleware Stack Integration

### api.py Wiring (LIFO — last added = outermost)

```python
from src.compliance.magna_carta import MagnaCarta, get_magna_carta
from src.compliance.cab_gate import CABMiddleware
from src.auth.zero_trust import ZeroTrustMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Wire compliance middleware (order matters — LIFO)
# 1. Add ZeroTrust LAST (executes first — populates jwt_claims)
app.add_middleware(ZeroTrustMiddleware)

# 2. Add Magna Carta second-to-last
if settings.magna_carta_enabled:
    mc = get_magna_carta()
    app.add_middleware(BaseHTTPMiddleware, dispatch=mc.check_request)

# 3. Add CAB gate first (executes last — has jwt_claims available)
if settings.cab_gate_enabled:
    app.add_middleware(CABMiddleware)
```

### Environment Variables

```bash
# .env
MAGNA_CARTA_ENABLED=true      # Enable MC runtime rules
CAB_GATE_ENABLED=true          # Enable CAB gate middleware (default: false in dev)
CAB_PROTECTED_PATHS=/admin/,/config/,/deploy/,/workers/
```

## 4. Using the CAB Gate

### Registering a Change

```python
from src.compliance.cab_gate import cab_gate

# Register a change request
change = await cab_gate.register_change(
    title="Update JWT expiry from 1h to 4h",
    description="Security review approved extending session duration",
    change_type="configuration",
    risk_level="low",
    requester="platform-engineer@trancendos.com",
    affected_systems=["infinity-auth"],
)
print(f"Change ID: {change['change_id']}")  # → CAB-A1B2C3D4
```

### Approving a Change

```python
result = await cab_gate.approve_change(
    change_id="CAB-A1B2C3D4",
    approver="cab-chair@trancendos.com",
    notes="Approved at Town Hall 2026-06-12",
)
```

### Making a Mutating Request with CAB Approval

```bash
curl -X PUT https://api.trancendos.com/admin/config/jwt_expiry \
  -H "Authorization: Bearer <jwt>" \
  -H "X-Change-ID: CAB-A1B2C3D4" \
  -H "Content-Type: application/json" \
  -d '{"expiry_seconds": 14400}'
```

Without `X-Change-ID`, the response is:
```json
{
  "error": "CAB_REQUIRED",
  "message": "This operation requires a CAB-approved change ID. Register via /cab/register",
  "status": 403
}
```

## 5. Compliance Checker Integration

### Basic Usage

```python
from src.compliance.checker import load_and_check, REGISTER_PATH

# DEFSTAN only
report = load_and_check(REGISTER_PATH)
print(f"DEFSTAN score: {report.overall_score:.1f}%")

# Full merged check
from src.compliance.checker import load_and_check_merged
from pathlib import Path

mc_path = Path("compliance/magna-carta/compliance/magna_carta_register.yaml")
report = load_and_check_merged(REGISTER_PATH, mc_path)

for area in report.areas:
    print(f"{area.code}: {area.score:.1f}% ({area.compliant}C/{area.partial}P/{area.total}T)")
```

### CI Gate

```python
# Fail CI if Magna Carta score drops below threshold
if report.magna_carta_score < 0.70:
    raise SystemExit(1)
```

## 6. Runtime Rule Reference

| Rule | Trigger | Response on Violation |
|---|---|---|
| MC-RULE-001 | Missing/invalid JWT | 401 Unauthorized |
| MC-RULE-002 | Malformed request boundary | 400 Bad Request |
| MC-RULE-003 | Rate limit exceeded | 429 Too Many Requests |
| MC-RULE-004 | Prohibited AI use | 451 Unavailable For Legal Reasons |
| MC-RULE-005 | Paid API used without opt-in | 403 Forbidden |
| MC-RULE-006 | Unencrypted PII in response | 500 (internal scrub) |
| MC-RULE-007 | Mutating request without CAB | 403 + CAB_REQUIRED |
| MC-RULE-008 | Missing GDPR transparency | 400 (logged, non-blocking) |
| MC-RULE-009 | PHI access without BAA | 403 Forbidden |

## 7. Forgejo CI Integration

Add to `.forgejo/workflows/compliance-check.yml`:

```yaml
compliance-gate:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive
    - run: pip install -r requirements.txt -q
    - run: python -m src.compliance.checker --magna-carta compliance/magna-carta/compliance/magna_carta_register.yaml --ci
```

## 8. Troubleshooting

### "Evidence path not found" for a register item

The checker looks for evidence files relative to the repo root. Create the missing file at the exact path listed in the register evidence array.

### Middleware not executing

Check `MAGNA_CARTA_ENABLED` is `true` (not `"true"` — pydantic-settings handles coercion). Use `make check-env` to validate.

### CAB gate blocking all requests

Verify `X-Change-ID` header is present and the change ID is in `APPROVED` status. Check `data/cab_changes.db` for change state.

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial integration guide |

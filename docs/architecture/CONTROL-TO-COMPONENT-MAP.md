# Control-to-Component Mapping

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Owner:** Trancendos Platform Engineering

This document maps each Magna Carta runtime rule and DEFSTAN control to the specific code component that implements it.

## Magna Carta Runtime Rules

| Rule ID | Rule Name | Component | File Path | Status |
|---|---|---|---|---|
| MC-RULE-001 | JWT Authentication Enforcement | ZeroTrust middleware | `src/auth/zero_trust.py` | ACTIVE |
| MC-RULE-002 | Request Boundary Validation | MagnaCarta middleware | `src/compliance/magna_carta.py` | ACTIVE |
| MC-RULE-003 | Rate Limiting | rate-limit-service | `workers/rate-limit-service/app.py` | ACTIVE |
| MC-RULE-004 | AI Governance Checks | AI governance module | `src/compliance/ai_governance.py` | ACTIVE |
| MC-RULE-005 | Zero-Cost Sovereignty Checks | AI gateway router | `src/ai_gateway/` | ACTIVE |
| MC-RULE-006 | PII/Privacy Detection | MagnaCarta compliance | `src/compliance/magna_carta.py` | ACTIVE |
| MC-RULE-007 | Town Hall CAB Gate | CAB gate middleware | `src/compliance/cab_gate.py` | ACTIVE |
| MC-RULE-008 | GDPR Transparency | Privacy middleware | `src/compliance/magna_carta.py` | ACTIVE |
| MC-RULE-009 | Health Data Controls | Platform entity config | `src/entities/platform.py` | ACTIVE |

## DEFSTAN Control Areas

### IA — Identity & Access

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-IA-001 | MCP server authentication | The Spark | `src/mcp/` |
| REQ-IA-002 | Platform independence | AI gateway fallback | `src/ai_gateway/` |
| REQ-IA-004 | Service mesh health | CircuitBreaker | `src/mesh/` |
| REQ-IA-005 | Event bus integrity | EventBus SQLite | `src/event_bus/` |
| REQ-IA-006 | Digital rights transparency | MagnaCarta + ZeroTrust | `src/compliance/`, `src/auth/` |

### SA — Security Architecture

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-SA-001 | TLS termination | Traefik | `docker-compose.production.yml` |
| REQ-SA-002 | JWT signing | Infinity Auth | `workers/infinity-auth/` |
| REQ-SA-003 | Secret management | Vault service | `workers/vault-service/` |

### QA — Quality Assurance

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-QA-001 | Test coverage >80% | pytest + coverage | `tests/` |
| REQ-QA-007 | Performance regression gate | perf_gate | `src/benchmark/perf_gate.py` |

### MC — Magna Carta

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-MC-001 | JWT authentication enforcement | ZeroTrust | `src/auth/zero_trust.py` |
| REQ-MC-002 | PII/Privacy protection | MagnaCarta | `src/compliance/magna_carta.py` |
| REQ-MC-003 | Rate limiting | rate-limit-service | `workers/rate-limit-service/app.py` |

### AI — AI Governance

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-AI-001 | AI use case governance | AI governance module | `src/compliance/ai_governance.py` |
| REQ-AI-002 | Zero-cost sovereignty | AI gateway | `src/ai_gateway/` |
| REQ-AI-003 | AI transparency headers | TODO — Q3 2026 | `api.py` |

### PRI — Privacy

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-PRI-001 | GDPR DSR process | DSR procedure | `docs/procedures/PROC-DSR-001-Data-Subject-Requests.md` |
| REQ-PRI-002 | Audit logging | Observatory | `workers/monitoring/` |

### SEC — Security

| Control | Description | Implementation | Path |
|---|---|---|---|
| REQ-SEC-001 | Zero Trust architecture | ZeroTrust IAM | `src/auth/zero_trust.py` |
| REQ-SEC-002 | Secret management via The Void | vault-service | `workers/vault-service/` |
| REQ-SEC-003 | Dependency vulnerability scanning | pip-audit + bandit | `.forgejo/workflows/security-scan.yml` |

## Middleware Execution Order (FastAPI LIFO)

```python
# Added last = outermost (executes first)
app.add_middleware(ZeroTrustMiddleware)      # outer — populates jwt_claims
app.add_middleware(MagnaCarta middleware)    # middle — MC rules
app.add_middleware(CABMiddleware)            # inner — CAB gate (has jwt_claims available)
```

## Threat Model Cross-Reference

See `ARCHITECTURE_THREAT_MODEL.md` for STRIDE analysis mapped against these controls.

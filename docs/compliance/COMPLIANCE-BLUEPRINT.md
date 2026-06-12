# Compliance Operating Model — Tranc3 Platform

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Owner:** Trancendos Platform Engineering

## 1. Compliance Architecture Overview

Tranc3 implements compliance as code through a layered model:

```
Layer 4: External Frameworks (ISO 27001, GDPR, HIPAA, FCA, EU AI Act)
           ↓
Layer 3: Magna Carta (9 runtime rules + 11 register requirements)
           ↓
Layer 2: DEFSTAN Register (compliance/register.yaml — 40+ requirements)
           ↓
Layer 1: Runtime Enforcement (middleware stack in api.py)
           ↓
Layer 0: Evidence Repository (this repo — docs/, compliance/, src/)
```

## 2. Register Architecture

| Register | Location | Framework | Items | Checker |
|---|---|---|---|---|
| DEFSTAN | `compliance/register.yaml` | Internal | 40+ | `src/compliance/checker.py` |
| Magna Carta | `compliance/magna-carta/compliance/magna_carta_register.yaml` | MC | 11 | Merged via `load_and_check_merged()` |
| Bridge | `compliance/tranc3_register_bridge.yaml` | Bridge | 11 | Machine-readable |

## 3. Compliance Score Target

| Area | Current | Target | Gap |
|---|---|---|---|
| Overall DEFSTAN | 100% | 100% | None |
| Magna Carta | 21% | 80%+ | Evidence creation programme |
| Combined | TBD | 70%+ | Blocking on MC evidence |

Score = `(COMPLIANT + 0.5 × PARTIAL) / (total − NA − WAIVED) × 100`

## 4. PDCA Compliance Cycle

### Plan (Quarterly)
- Review register for new/changed requirements
- Assess evidence gaps via `make compliance-check`
- Update risk register (`docs/compliance/RISK-REGISTER.md`)
- Assign owners to action tracker items

### Do (Ongoing)
- Implement controls as code
- Create evidence documents
- Run pre-commit security hooks
- Maintain policy library

### Check (Monthly)
- Run `make compliance-merged` for full score
- Review The Observatory audit logs
- Verify CAB gate effectiveness
- Check dependency vulnerability scan results

### Act (Quarterly)
- Remediate findings from Check phase
- Update register statuses
- Escalate overdue items to Town Hall
- Board/management review

## 5. Evidence Quality Standards

| Evidence Type | Requirements | Review Cycle |
|---|---|---|
| Policy | Version-controlled, owner named, review date | Annual |
| Procedure | Step-by-step, tested, linked to policy | Annual |
| Code | Deployed and tested, linked from register | Per-release |
| Configuration | Version-controlled, change-managed | Per-change |
| Audit log | Tamper-evident, retained 3+ years | Continuous |

## 6. Governance Integration

### Town Hall (CranBania — Port 8071)
- All compliance register changes reviewed via CAB
- PRINCE2 stage-gate used for major compliance initiatives
- Kanban board tracks open compliance actions

### Magna Carta Runtime Rules
When `MAGNA_CARTA_ENABLED=true`:
- 9 rules evaluated per request boundary
- Violations logged to The Observatory
- Critical violations return 451/403 immediately

### Automated Gates
| Gate | Trigger | Tool | Location |
|---|---|---|---|
| Pre-commit | Every commit | bandit + semgrep + gitleaks | `.pre-commit-config.yaml` |
| PR gate | Pull request | Forgejo CI | `.forgejo/workflows/security-scan.yml` |
| Compliance check | `make compliance-merged` | checker.py | `src/compliance/checker.py` |
| Performance gate | `make perf-gate` | perf_gate.py | `src/benchmark/perf_gate.py` |

## 7. Roles and Responsibilities

| Role | Responsibility | Owner |
|---|---|---|
| Platform Engineering | Implement controls, maintain register | Trancendos |
| Compliance Owner | Policy review, framework alignment | Trancendos |
| CAB Chair | Approve material changes | Town Hall |
| Data Protection Lead | GDPR/privacy compliance | Trancendos |
| Security Lead | Threat model, pen test programme | Trancendos |

## 8. Exception Management

1. Raise exception request with business justification
2. Document in `docs/compliance/COMPLIANCE-ACTION-TRACKER.md`
3. Risk-assess against register
4. CAB approval required for deviations from MC/DEFSTAN
5. Exception review every 90 days; auto-expire at 1 year

## 9. Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial compliance operating model |

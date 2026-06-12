# Compliance Action Tracker

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Review Cycle:** Monthly
**Owner:** Trancendos Platform Engineering

## Open Actions

| ID | Finding | Source | Owner | Priority | Due Date | Status |
|---|---|---|---|---|---|---|
| ACT-001 | AI transparency headers (X-AI-Generated) not yet implemented | REQ-AI-003 | Platform Eng | P2 | 2026-09-30 | In Progress |
| ACT-002 | GDPR DSR automated workflow not yet deployed | REQ-PRI-001 | Platform Eng | P2 | 2026-09-30 | Planned |
| ACT-003 | Secret management: remaining workers not using vault-service | REQ-SEC-002 | Platform Eng | P2 | 2026-09-30 | In Progress |
| ACT-004 | HIPAA BAA programme — activate when HIPAA_PROFILE enabled | MC-008 | Legal | P3 | 2026-12-31 | Planned |
| ACT-005 | External penetration test (annual) | MC-010 | Security | P2 | 2026-12-31 | Planned |
| ACT-006 | Staff policy attestation (PROC-TRN-001) | MC-010 | HR | P2 | 2026-09-30 | Planned |
| ACT-007 | SOC 2 Type II readiness assessment | MC-010 | Compliance | P3 | 2027-03-31 | Planned |
| ACT-008 | FCA Consumer Duty gap analysis | MC-009 | Legal | P3 | 2026-12-31 | Planned |
| ACT-009 | MAGNA_CARTA_ENABLED staging enablement | MC-011 | Platform Eng | P2 | 2026-09-30 | In Progress |
| ACT-010 | Bias measurement first run (PROC-AI-002) | MC-005 | AI Team | P2 | 2026-09-30 | Planned |
| ACT-011 | Internal audit programme — first audit | MC-010 | Compliance | P2 | 2026-12-31 | Planned |

## Closed Actions

| ID | Finding | Closed Date | Resolution |
|---|---|---|---|
| ACT-C001 | Magna Carta submodule not wired | 2026-06-12 | Submodule added to .gitmodules |
| ACT-C002 | Rate limit service not implemented | 2026-06-12 | workers/rate-limit-service/app.py created |
| ACT-C003 | CAB gate not implemented | 2026-06-12 | src/compliance/cab_gate.py created |
| ACT-C004 | .env generation manual and error-prone | 2026-06-12 | scripts/generate_env.py created |
| ACT-C005 | Compliance register missing MC/AI/PRI/SEC areas | 2026-06-12 | compliance/register.yaml updated |
| ACT-C006 | Policy library incomplete | 2026-06-12 | docs/policies/ baseline created |

## Escalation Log

| Date | Action | Escalation Level | Outcome |
|---|---|---|---|
| 2026-06-12 | ACT-005 (pen test) | Town Hall | Budgeted for Q4 2026 |

## Metrics

| Metric | Value |
|---|---|
| Total open actions | 11 |
| Overdue actions | 0 |
| Average age (open) | 0 days |
| P1 open | 0 |
| P2 open | 7 |
| P3 open | 4 |

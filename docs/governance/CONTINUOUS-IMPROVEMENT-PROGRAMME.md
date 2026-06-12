# Continuous Improvement Programme

**Version:** 1.0.0 | **Date:** 2026-06-12
**Framework:** ISO 27001:2022 Clause 10 · PDCA Cycle · Magna Carta MC-011

## 1. Purpose

This programme operationalises the Plan-Do-Check-Act (PDCA) cycle linking the Tranc3 evidence programme to ongoing platform operations, compliance, and security improvement.

## 2. PDCA Cycle Implementation

### Plan (Quarterly — first week of quarter)

| Activity | Tool | Owner | Output |
|---|---|---|---|
| Compliance register review | `make compliance-merged` | Platform Eng | Score delta report |
| Risk register update | `docs/compliance/RISK-REGISTER.md` | Platform Eng | Updated risk scores |
| Action tracker review | `docs/compliance/COMPLIANCE-ACTION-TRACKER.md` | Platform Eng | Overdue actions flagged |
| Audit programme review | `docs/governance/INTERNAL-AUDIT-PROGRAMME.md` | Compliance | Audit schedule confirmed |
| Threat model review | `ARCHITECTURE_THREAT_MODEL.md` | Security | Updated STRIDE analysis |

### Do (Ongoing — daily/weekly)

| Activity | Frequency | Tool | Owner |
|---|---|---|---|
| Pre-commit security scan | Every commit | `.pre-commit-config.yaml` | Developer |
| Dependency vulnerability check | Weekly (Forgejo CI) | `pip-audit`, `safety` | Forgejo |
| Security scan | Per PR | `bandit`, `semgrep`, `gitleaks` | Forgejo |
| Observatory log review | Daily | Grafana/Loki | Platform Eng |
| CAB change decisions | Per change | `cab_gate.py` | CAB Chair |

### Check (Monthly — first Monday of month)

| Activity | Tool | Owner | Output |
|---|---|---|---|
| Compliance score check | `make compliance-merged` | Platform Eng | Score vs baseline |
| Security incident review | The Observatory | Security | Incident summary |
| CVE review | Forgejo scan results | Platform Eng | Remediation plan |
| Action tracker progress | `COMPLIANCE-ACTION-TRACKER.md` | Platform Eng | Status update |
| Management KPIs | Grafana dashboards | Management | Monthly report |

### Act (Quarterly — management review)

| Activity | Output | Escalation |
|---|---|---|
| Management review | Minutes + decisions | Board if critical |
| ISMS improvement decisions | Action tracker update | Town Hall approval |
| Policy/procedure updates | Version increments | CAB change request |
| Register status updates | Compliance score delta | Published to team |

## 3. Improvement Metrics

| Metric | Baseline | Target (Q4 2026) | Target (Q2 2027) |
|---|---|---|---|
| Magna Carta compliance score | 21% | 80% | 90% |
| DEFSTAN compliance score | 100% | 100% | 100% |
| Open critical/high actions | 0 | 0 | 0 |
| Mean time to remediate (critical CVE) | TBD | <7 days | <5 days |
| Security scan pass rate | TBD | 100% | 100% |

## 4. Improvement Backlog

Track improvements in The Town Hall (CranBania Kanban board):
- Board: `trancendos.com/the-workshop/townhall`
- Column mapping: Backlog → In Plan → Do → Check → Done

## 5. Feedback Channels

| Channel | Purpose | Owner |
|---|---|---|
| GitHub Issues → Forgejo | Technical improvements | Platform Eng |
| Town Hall Kanban | Compliance/governance improvements | Compliance |
| Observatory Alerts | Automated anomaly-driven improvements | Platform Eng |
| Management Review | Strategic improvements | Management |
| Staff feedback | Process improvements | All staff |

## 6. Improvement Record

| Date | Improvement | Trigger | Outcome |
|---|---|---|---|
| 2026-06-12 | Rate-limit-service implementation | Compliance gap (MC-RULE-003) | COMPLIANT |
| 2026-06-12 | CAB gate implementation | Compliance gap (MC-RULE-007) | COMPLIANT |
| 2026-06-12 | Evidence library creation | MC compliance score 21% | Score increase pending |
| 2026-06-12 | generate_env.py automation | Manual .env setup P0 | Fully automated |

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial CIP created |

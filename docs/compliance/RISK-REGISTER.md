# Information Security Risk Register

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Review Cycle:** Quarterly
**Owner:** Trancendos Platform Engineering | **Framework:** ISO 27001:2022 Clause 6.1.2

## Risk Scoring Matrix

**Likelihood:** 1 (Rare) → 5 (Almost Certain)
**Impact:** 1 (Negligible) → 5 (Critical)
**Risk Score** = Likelihood × Impact | **Threshold:** >12 = High, 6–12 = Medium, <6 = Low

## Risk Register

| ID | Risk | Category | L | I | Score | Rating | Controls | Owner | Review Date |
|---|---|---|---|---|---|---|---|---|---|
| RSK-001 | JWT secret compromise → token forgery | Authentication | 2 | 5 | 10 | Medium | JWT_SECRET in Vault; rotation procedure; ZeroTrust validation | Platform Eng | 2026-09-12 |
| RSK-002 | SQLite database corruption → data loss | Data | 2 | 4 | 8 | Medium | WAL mode; automated backup (cron-service); DR drill | Platform Eng | 2026-09-12 |
| RSK-003 | Dependency vulnerability exploitation | Supply Chain | 3 | 4 | 12 | Medium | pip-audit weekly; pre-commit hooks; Forgejo security-scan.yml | Platform Eng | 2026-09-12 |
| RSK-004 | Unapproved AI model introduces bias/risk | AI Governance | 2 | 4 | 8 | Medium | Model change CAB process; bias measurement (Q3 2026) | AI Team | 2026-09-12 |
| RSK-005 | PHI exposure if HIPAA_PROFILE enabled without controls | Privacy | 1 | 5 | 5 | Low | HIPAA_PROFILE disabled by default; BAA programme before activation | Legal | 2026-12-12 |
| RSK-006 | Privileged user abuse → unauthorised config changes | Access Control | 2 | 4 | 8 | Medium | CAB gate; admin role segregation; Observatory audit trail | Platform Eng | 2026-09-12 |
| RSK-007 | DDoS → platform unavailability | Availability | 3 | 3 | 9 | Medium | Traefik rate limiting; rate-limit-service; Cloudflare DDoS (legacy) | Infra | 2026-09-12 |
| RSK-008 | Container escape → host compromise | Infrastructure | 1 | 5 | 5 | Low | Non-root containers; network isolation; Cuckoo sandbox (planned) | Infra | 2026-12-12 |
| RSK-009 | API key exposure in logs/code | Secrets | 3 | 4 | 12 | Medium | gitleaks pre-commit; Vault secret management; log redaction | Platform Eng | 2026-09-12 |
| RSK-010 | AI transparency gap → regulatory action | Compliance | 2 | 3 | 6 | Medium | ai_governance.py; assistive-only policy; X-AI-Generated header (planned) | Compliance | 2026-09-12 |
| RSK-011 | GDPR data subject request overrun SLA | Privacy | 2 | 3 | 6 | Medium | PROC-DSR-001; 30-day SLA; automated DSR workflow (planned) | DPO | 2026-09-12 |
| RSK-012 | Third-party provider outage → service disruption | Supply Chain | 3 | 3 | 9 | Medium | 5-tier AI fallback; alternate PSP; self-hosted critical path | Infra | 2026-09-12 |

## Treatment Actions

| Risk ID | Treatment | Action | Owner | Due Date |
|---|---|---|---|---|
| RSK-001 | Reduce | Implement automated JWT secret rotation | Platform Eng | 2026-09-30 |
| RSK-003 | Reduce | Enable automated dependency PR updates | Platform Eng | 2026-09-30 |
| RSK-004 | Reduce | First bias measurement run | AI Team | 2026-09-30 |
| RSK-009 | Reduce | Vault migration for all remaining hardcoded secrets | Platform Eng | 2026-09-30 |

## Accepted Risks

| Risk ID | Justification | Accepted By | Accepted Date |
|---|---|---|---|
| RSK-005 | HIPAA scope not yet applicable | Trancendos | 2026-06-12 |
| RSK-008 | Low likelihood; mitigated by network isolation | Trancendos | 2026-06-12 |

## Risk Review History

| Date | Reviewer | Changes |
|---|---|---|
| 2026-06-12 | Trancendos | Initial risk register created |

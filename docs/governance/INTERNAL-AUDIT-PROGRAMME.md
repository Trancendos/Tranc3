# Internal Audit Programme

**Version:** 1.0.0 | **Date:** 2026-06-12
**Framework:** ISO 27001:2022 Clause 9.2 | **Owner:** Trancendos Platform Engineering

## 1. Audit Programme Overview

Annual internal audit programme covering all areas of the Tranc3 ISMS and Magna Carta compliance framework. Aligned to ISO 27001 Clause 9.2 and SOC 2 CC4.1.

## 2. Audit Schedule (2026–2027)

| Audit ID | Scope | Planned Date | Lead Auditor | Status |
|---|---|---|---|---|
| AUD-2026-001 | Access Control & Authentication (CC6, IA) | 2026-09-30 | Trancendos | Planned |
| AUD-2026-002 | Change Management & CAB Gate (CC8, MC-003) | 2026-10-31 | Trancendos | Planned |
| AUD-2026-003 | Privacy & Data Rights (GDPR, MC-001) | 2026-11-30 | Trancendos | Planned |
| AUD-2026-004 | AI Governance (EU AI Act, MC-005) | 2026-12-31 | Trancendos | Planned |
| AUD-2027-001 | Full ISMS scope audit | 2027-03-31 | External (TBD) | Planned |

## 3. Audit Methodology

### Pre-Audit
1. Notify auditees 4 weeks in advance
2. Issue audit plan with scope, criteria, evidence requests
3. Review previous audit findings and actions
4. Prepare evidence checklists from `docs/architecture/CONTROL-TO-COMPONENT-MAP.md`

### During Audit
1. Opening meeting — confirm scope, methodology, timeline
2. Evidence collection: code review, config review, log sampling
3. Interview process owners
4. Document findings against criteria
5. Preliminary findings walkthrough

### Post-Audit
1. Issue draft report within 5 business days
2. Auditee response period: 10 business days
3. Issue final report
4. Log findings in `docs/compliance/COMPLIANCE-ACTION-TRACKER.md`
5. Escalate critical findings to Town Hall/management

## 4. Audit Criteria

Primary criteria:
- Tranc3 DEFSTAN register (`compliance/register.yaml`)
- Magna Carta register (`compliance/magna-carta/compliance/magna_carta_register.yaml`)
- ISO 27001:2022 Annex A controls
- GDPR Articles 5, 13, 14, 17, 20, 25, 32

## 5. Evidence Requirements by Control Area

| Area | Key Evidence | Location |
|---|---|---|
| Access Control | JWT validation logs, ZeroTrust config | `src/auth/zero_trust.py`, Observatory |
| Change Management | CAB records, change log | `data/cab_changes.db` |
| Vulnerability Mgmt | Security scan reports | Forgejo CI + `logs/` |
| Incident Response | Incident log | `docs/evidence/` |
| Backup & Recovery | DR drill results | `scripts/dr_restore.py` output |
| Compliance Register | Checker output | `make compliance-merged` |

## 6. Nonconformity Management

| Severity | Definition | Response Time | Escalation |
|---|---|---|---|
| Critical | Control failure with active risk | 48 hours | Town Hall immediately |
| Major | Systematic control breakdown | 30 days | Monthly management review |
| Minor | Isolated control weakness | 90 days | Quarterly review |
| Observation | Improvement opportunity | Next cycle | Annual review |

## 7. Audit Records Retention

Audit reports retained for minimum 3 years per ISO 27001 Clause 9.2(f).

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial internal audit programme |

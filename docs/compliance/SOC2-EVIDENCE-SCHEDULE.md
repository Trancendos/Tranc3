# SOC 2 Type II Evidence Schedule

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Owner:** Trancendos Platform Engineering
**Target Readiness:** Q1 2027 | **Audit Period:** TBD

## Trust Services Criteria Mapping

### CC1 — Control Environment

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC1.1 COSO principles | Policy library, org structure | `docs/compliance/COMPLIANCE-BLUEPRINT.md` | Available |
| CC1.2 Board oversight | Management review minutes | `docs/governance/MANAGEMENT-REVIEW-TEMPLATE.md` | Planned |
| CC1.3 Management structure | Org chart, role definitions | `docs/` | Planned |
| CC1.4 Competence | Training records | PROC-TRN-001 attestation register | Planned |
| CC1.5 Accountability | Performance reviews | HR system | Not started |

### CC2 — Communication & Information

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC2.1 Information quality | Data classification policy | `docs/policies/` | Available |
| CC2.2 Internal communication | Policy dissemination records | PROC-TRN-001 | Planned |
| CC2.3 External communication | Privacy policy, DSR process | POL-PRI-001, PROC-DSR-001 | Available |

### CC3 — Risk Assessment

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC3.1 Risk identification | Risk register | `docs/compliance/RISK-REGISTER.md` | Available |
| CC3.2 Risk analysis | Risk scoring matrix | RISK-REGISTER.md | Available |
| CC3.3 Risk response | Treatment actions | RISK-REGISTER.md + action tracker | Available |
| CC3.4 Change risk assessment | CAB change records | `data/cab_changes.db` | Available |

### CC4 — Monitoring Activities

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC4.1 Monitoring controls | Continuous monitoring evidence | The Observatory dashboards | Available |
| CC4.2 Deficiency evaluation | Compliance check results | `make compliance-merged` output | Available |

### CC5 — Control Activities

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC5.1 Control selection | Control-to-component map | `docs/architecture/CONTROL-TO-COMPONENT-MAP.md` | Available |
| CC5.2 Technology controls | Security scan results | `.forgejo/workflows/security-scan.yml` logs | Available |
| CC5.3 Change management | CAB records | `data/cab_changes.db` + PROC-CHG-001 | Available |

### CC6 — Logical and Physical Access

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC6.1 Logical access security | ZeroTrust IAM implementation | `src/auth/zero_trust.py` | Available |
| CC6.2 New access provisioning | Access request records | Infinity Gate role assignment | Available |
| CC6.3 Role modification | CAB change records | `data/cab_changes.db` | Available |
| CC6.6 External access | API key management | Vault service | Available |
| CC6.7 Access transmission | TLS enforcement | Traefik config | Available |
| CC6.8 Malicious software | Antivirus / pre-commit hooks | `.pre-commit-config.yaml` | Available |

### CC7 — System Operations

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC7.1 Detection of vulnerabilities | Security scan results | Forgejo CI reports | Available |
| CC7.2 Monitoring alerts | Prometheus alert rules | `workers/monitoring/` | Available |
| CC7.3 Incident response | Incident log | `docs/evidence/` | Planned |
| CC7.4 Business continuity | DR drill results | `scripts/dr_restore.py` | Available |

### CC8 — Change Management

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC8.1 Change authorisation | CAB records | `src/compliance/cab_gate.py` | Available |

### CC9 — Risk Mitigation

| Criteria | Evidence Required | Source | Status |
|---|---|---|---|
| CC9.1 Vendor risk | Supplier register | `docs/compliance/FCA-ALIGNMENT.md` | Available |
| CC9.2 Business associates | BAA register | `docs/compliance/HIPAA-ALIGNMENT.md` | Available |

## Availability Criteria

| Criteria | Evidence | Source | Status |
|---|---|---|---|
| A1.1 Capacity management | Resource monitoring | Prometheus dashboards | Available |
| A1.2 Recovery testing | DR drill records | `scripts/dr_restore.py` | Available |

## Evidence Collection Schedule

| Quarter | Activity | Responsible |
|---|---|---|
| Q3 2026 | First evidence collection run | Platform Eng |
| Q4 2026 | Gap remediation | Platform Eng |
| Q1 2027 | Pre-audit readiness review | Compliance |
| Q2 2027 | External audit (if pursued) | External auditor |

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial SOC 2 evidence schedule |

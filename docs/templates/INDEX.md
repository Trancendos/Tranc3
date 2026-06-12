# Template Library Index

**Version:** 1.0.0 | **Date:** 2026-06-12
**Owner:** Trancendos Platform Engineering

## Contract Templates

| Template | Purpose | Location |
|---|---|---|
| Data Processing Agreement (DPA) | GDPR Art. 28 controller-processor | `docs/templates/contracts/DPA-TEMPLATE.md` |
| Business Associate Agreement (BAA) | HIPAA §164.314 | `docs/templates/contracts/BAA-TEMPLATE.md` |
| Confidentiality Agreement | Staff/contractor NDA | `docs/templates/contracts/NDA-TEMPLATE.md` |
| Supplier Security Questionnaire | Vendor assessment | `docs/templates/contracts/SUPPLIER-SECURITY-QUESTIONNAIRE.md` |

## Governance Templates

| Template | Purpose | Location |
|---|---|---|
| Management Review Minutes | ISO 27001 Clause 9.3 | `docs/governance/MANAGEMENT-REVIEW-TEMPLATE.md` |
| Change Request Form | CAB/Town Hall gate | `docs/procedures/PROC-CHG-001-Change-Request.md` |
| Incident Report | Security incident | `docs/templates/governance/INCIDENT-REPORT-TEMPLATE.md` |
| Risk Assessment | New system/change | `docs/templates/governance/RISK-ASSESSMENT-TEMPLATE.md` |

## Compliance Templates

| Template | Purpose | Location |
|---|---|---|
| Data Subject Request | GDPR DSR processing | `docs/procedures/PROC-DSR-001-Data-Subject-Requests.md` |
| Policy Attestation | Annual sign-off | `docs/evidence/POLICY-ATTESTATION-REGISTER.md` |
| Audit Report | Internal audit findings | `docs/templates/compliance/AUDIT-REPORT-TEMPLATE.md` |
| Nonconformity Record | Audit finding tracking | `docs/templates/compliance/NCR-TEMPLATE.md` |

## Engineering Templates

| Template | Purpose | Location |
|---|---|---|
| Worker Bootstrap | New FastAPI worker scaffold | `scripts/new_worker.py` (TBD) |
| PR Description | Pull request governance | `.forgejo/PULL_REQUEST_TEMPLATE.md` |
| CAB Change Request | Change advisory board | `docs/procedures/PROC-CHG-001-Change-Request.md` |

## Usage Notes

1. All contract templates require legal review before execution
2. Templates are version-controlled; check for latest version before use
3. Completed forms stored in `data/governance/` (excluded from git — sensitive)
4. Questions: raise via The Town Hall governance board

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial template index |

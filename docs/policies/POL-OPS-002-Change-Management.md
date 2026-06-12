# POL-OPS-002 — Change Management Policy
**Version:** 1.0.0 | **Owner:** Trancendos Platform Engineering | **Classification:** UNCLASSIFIED  
**Effective:** 2026-06-12 | **Review Cycle:** Annual | **Approver:** Platform Owner

## 1. Purpose
Govern all changes to the Trancendos production platform, ensuring changes are assessed, authorised, tested, and documented. This policy implements Magna Carta MC-RULE-007 (Town Hall Governance Gate).

## 2. Change Classification
| Type | Definition | CAB Required | Lead Time |
|---|---|---|---|
| **Standard** | Pre-approved, low-risk, documented procedure | No | 0 days |
| **Normal** | Assessed and approved by CAB | Yes | 5 business days |
| **Emergency** | Urgent fix for production incident | Post-hoc CAB review | Immediate |

## 3. Change Advisory Board (CAB)
The CAB is The Town Hall governance gate (CranBania, port 8071). All Normal changes must:
1. Be registered as a change request with `change_type`, `description`, `risk`, and `requestor`
2. Receive at least 1 CAB approval (Platform Owner or Security Lead)
3. Pass the automated compliance gate (`src/compliance/cab_gate.py`) before deployment

## 4. Mandatory CAB Review Categories
- Infrastructure changes (Terraform, Docker Compose)
- Security configuration changes (JWT, TLS, access control)
- Production deployments
- Database schema migrations
- Dependency upgrades
- Access control changes

## 5. Auto-Approved (Standard Changes)
- Documentation updates
- Test additions
- Minor bug fixes (no security impact, <50 LOC)
- README changes

## 6. Emergency Changes
Emergency changes bypass CAB approval but must be:
- Approved by Platform Owner (emergency bypass role)
- Post-hoc reviewed within 24 hours
- Retrospective change record created in The Town Hall

## 7. CAB Gate Integration
The `CABMiddleware` (`src/compliance/cab_gate.py`) enforces this policy at the API level:
- Mutating requests (`POST/PUT/DELETE/PATCH`) to `/admin/`, `/config/`, `/deploy/`, `/workers/` require `X-Change-ID` header
- The CAB gate validates the change ID is approved before the request proceeds
- All gate decisions are logged to The Observatory

## 8. Failed Changes
Failed changes are rolled back per the Disaster Recovery plan. Rollback procedures are documented in `scripts/dr_restore.py`.

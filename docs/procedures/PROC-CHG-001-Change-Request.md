# PROC-CHG-001 — Change Request Procedure
**Version:** 1.0.0 | **Owner:** Trancendos Platform Engineering | **Parent Policy:** POL-OPS-002

## 1. Purpose
Define how to raise, approve, implement, and close a change request through the CAB governance gate.

## 2. Raising a Change Request
```python
from src.compliance.cab_gate import cab_gate

change_id = cab_gate.register_change(
    change_type="production_deployment",
    description="Deploy rate-limit-service v1.0 to port 8026",
    requestor="platform-engineer",
    risk="low"
)
```
Or via The Town Hall UI: `http://trancendos.com/townhall/changes/new`

## 3. CAB Review
- Change request appears in The Town Hall CAB queue
- Approver reviews risk, description, and rollback plan
- Approval via: `cab_gate.approve_change(change_id, approver="platform-owner")`
- Status transitions: `PENDING → APPROVED` or `PENDING → REJECTED`

## 4. Implementing the Change
Include the change ID in mutating API calls:
```bash
curl -X POST https://api.trancendos.com/admin/deploy \
  -H "Authorization: Bearer $JWT" \
  -H "X-Change-ID: CHG-2026-0001" \
  -d '{"service": "rate-limit-service", "version": "1.0"}'
```

## 5. Post-Implementation
- Verify deployment health via The Observatory
- Close the change request: mark as `COMPLETED` or `FAILED`
- Failed changes: trigger rollback and create incident record

## 6. Emergency Change Procedure
1. Notify Platform Owner immediately
2. Implement fix with `X-Emergency-Change: true` header
3. Create retrospective change record within 24 hours
4. Post-hoc CAB review at next available slot

# PROC-DSR-001 — Data Subject Request Handling Procedure
**Version:** 1.0.0 | **Owner:** Trancendos Platform Engineering | **Parent Policy:** POL-PRI-001  
**Effective:** 2026-06-12 | **SLA:** 30 calendar days from receipt

## 1. Purpose
Define the end-to-end process for handling Data Subject Requests (DSRs) submitted under UK/EU GDPR Articles 15–22.

## 2. Request Receipt
DSRs may be submitted via:
- **Platform portal:** `/account/privacy` — authenticated self-service
- **Email:** privacy@trancendos.com
- **Post:** Trancendos Data Protection Officer

All requests are logged to The Observatory audit trail with a unique DSR-YYYY-NNNN reference.

## 3. Identity Verification
Before acting on a DSR, identity must be verified:
- **Authenticated portal requests:** JWT + MFA verification is sufficient.
- **Email/post requests:** Government-issued ID + proof of platform registration required.
- Verification completed within 5 business days.

## 4. Request Types and SLAs
| Request Type | GDPR Article | SLA | Automated? |
|---|---|---|---|
| Subject Access Request | Art 15 | 30 days | Partial — data export auto-generated |
| Rectification | Art 16 | 30 days | No — manual review required |
| Erasure | Art 17 | 30 days | Yes — deletion pipeline via The Void |
| Restriction | Art 18 | 30 days | No — flag set in user record |
| Data Portability | Art 20 | 30 days | Yes — JSON export via `/account/export` |
| Objection | Art 21 | 30 days | Partial — opt-out flags automated |

## 5. Access Request Process
1. Authenticate requester
2. Trigger automated data export: all data held across all Tranc3 workers
3. Generate PDF/JSON report
4. Encrypt and send via secure email within 30 days
5. Log response to Observatory

## 6. Erasure Process
1. Authenticate requester
2. Validate no legal hold applies (payments records, fraud investigation)
3. Trigger deletion pipeline:
   - User record → logical delete + cryptographic key erasure
   - JWT sessions → immediate revocation
   - Vector store entries → purge by user_id
   - AI conversation history → purge
   - Audit logs → anonymise (retain log structure, remove PII)
4. Confirm deletion within 30 days
5. Log to Observatory with audit hash

## 7. Escalation
Requests that cannot be completed within SLA, involve legal holds, or require management review are escalated to the Platform Owner.

## 8. Record Keeping
All DSR records are retained for 6 years from the date of response.

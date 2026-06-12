# POL-PRI-001 — Data Protection & Privacy Policy
**Version:** 1.0.0 | **Owner:** Trancendos Platform Engineering | **Classification:** UNCLASSIFIED — PUBLIC  
**Effective:** 2026-06-12 | **Review Cycle:** Annual | **Approver:** Platform Owner

## 1. Purpose
This policy establishes the principles governing how Trancendos collects, processes, stores, and deletes personal data in compliance with the UK GDPR, EU GDPR, and the Magna Carta Framework Rule MC-RULE-002.

## 2. Scope
All Trancendos platform services, workers, and personnel who process personal data belonging to platform users, staff, or third parties.

## 3. Data Protection Principles (UK/EU GDPR Article 5)
1. **Lawfulness, fairness, transparency** — All processing has a lawful basis; users are informed via the platform privacy notice.
2. **Purpose limitation** — Data collected for a specified purpose is not reused for incompatible purposes.
3. **Data minimisation** — Only data necessary for the stated purpose is collected.
4. **Accuracy** — Data is kept accurate and up to date; correction mechanisms are available.
5. **Storage limitation** — Personal data is deleted after the retention period defined in the Data Retention Schedule.
6. **Integrity and confidentiality** — Data is protected by AES-GCM encryption (The Void vault), TLS in transit, and RBAC access controls.
7. **Accountability** — Trancendos maintains a Record of Processing Activities (RoPA) and demonstrates compliance.

## 4. Lawful Bases
| Processing Activity | Lawful Basis |
|---|---|
| User authentication | Contract (Art 6(1)(b)) |
| Platform analytics | Legitimate interests (Art 6(1)(f)) |
| Payment processing | Contract (Art 6(1)(b)) |
| Marketing communications | Consent (Art 6(1)(a)) |
| Security monitoring | Legitimate interests (Art 6(1)(f)) |

## 5. Data Subject Rights
Users may exercise the following rights via the platform privacy portal or by contacting privacy@trancendos.com:
- **Access (Art 15)** — Subject Access Request (SAR) handled within 30 days per PROC-DSR-001.
- **Rectification (Art 16)** — Correction of inaccurate data within 30 days.
- **Erasure (Art 17)** — Right to be forgotten; automated deletion pipeline via The Void.
- **Restriction (Art 18)** — Processing restriction on request.
- **Portability (Art 20)** — Data export in JSON format on request.
- **Objection (Art 21)** — Opt-out of processing based on legitimate interests.

## 6. PII Detection and Response
The Magna Carta middleware (MC-RULE-002) scans all API responses for PII leakage patterns (SSN, card numbers, NHS numbers, passwords). Violations are:
- **Advisory mode:** Logged to The Observatory audit trail with severity HIGH.
- **Enforcement mode:** Response blocked with HTTP 403 and incident raised.

## 7. Data Retention
| Data Category | Retention Period | Deletion Method |
|---|---|---|
| User account data | Duration of relationship + 6 years | Cryptographic erasure (AES key deletion) |
| Audit logs | 7 years (The Observatory) | Secure deletion from SQLite |
| Session tokens | 60 minutes (JWT expiry) | Automatic expiry |
| AI conversation history | 90 days (configurable) | Automated purge |
| Payment records | 7 years (legal obligation) | Archived to The Basement |

## 8. Data Breaches
Breaches are handled under the Incident Response Plan. Reportable breaches (likely to result in risk to individuals' rights) are notified to the ICO within 72 hours per Art 33.

## 9. Third-Party Processors
All data processors are bound by Data Processing Agreements (DPAs). The supplier DPA register is maintained at `compliance/supplier_dpa_register.yaml`.

## 10. Policy Review
This policy is reviewed annually or following significant changes to processing activities, legislation, or platform architecture.

---
*Magna Carta Rule Reference: MC-RULE-002 (PII Protection), MC-RULE-009 (GDPR Transparency)*  
*DEFSTAN Reference: REQ-PRI-001, REQ-PRI-002*

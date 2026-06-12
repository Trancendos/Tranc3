# PROC-TRN-001 — Security Awareness and Policy Attestation

**Version:** 1.0.0 | **Date:** 2026-06-12
**Owner:** Trancendos Platform Engineering
**Framework:** ISO 27001 A.6.3 · GDPR Art. 29 · Magna Carta MC-010

## 1. Purpose

This procedure governs the annual security awareness programme and policy attestation process for all personnel with access to the Tranc3 platform.

## 2. Scope

Applies to:
- All platform administrators
- All technical staff (Platform Engineering, AI team, Security team)
- All third-party contractors with privileged system access

## 3. Annual Training Cycle

### Schedule

| Activity | Timeline | Owner |
|---|---|---|
| Training materials updated | 1 September | Compliance |
| Training distributed | 15 September | HR/Compliance |
| Completion deadline | 30 September | All staff |
| Non-completion escalation | 7 October | HR/Line managers |
| Register closed | 15 October | Compliance |

### Training Topics

1. **Information Security Fundamentals**
   - Social engineering awareness
   - Password security and MFA
   - Secure coding practices

2. **Data Protection (GDPR)**
   - Personal data definitions
   - Lawful basis for processing
   - Data subject rights and how to handle DSRs
   - Breach recognition and reporting

3. **AI Ethics and Governance**
   - EU AI Act obligations
   - Prohibited AI uses
   - AI transparency requirements
   - Human oversight obligations

4. **Change Management**
   - When CAB approval is required
   - How to submit a change request
   - Consequences of unauthorised changes

5. **Incident Reporting**
   - What constitutes a security incident
   - How to report (The Observatory / direct to Security lead)
   - GDPR breach notification obligations (72-hour rule)

## 4. Attestation Process

### Step 1: Distribution
Compliance owner distributes attestation form with links to:
- Policy library: `docs/policies/`
- This procedure: `docs/procedures/PROC-TRN-001-*.md`

### Step 2: Training Completion
Staff complete training materials (estimated 90 minutes).

### Step 3: Attestation Signature
Staff complete attestation form confirming:

> *"I confirm that I have read, understood, and will comply with the Trancendos security policies and procedures as listed. I understand my obligations under GDPR, the AI Ethics policy, and the Change Management policy. I commit to reporting any security incidents or suspected policy breaches without delay."*

### Step 4: Record Keeping
Compliance owner records completion in `docs/evidence/POLICY-ATTESTATION-REGISTER.md`.

### Step 5: Non-Completion
- Day 7: Reminder email
- Day 14: Line manager notification
- Day 21: Access review — consider temporary access restriction until completed
- Day 30: Escalate to management review

## 5. New Staff Onboarding

New staff must complete security awareness training within 5 business days of system access being granted. Access to sensitive systems is restricted until attestation is completed.

## 6. Privileged Access Additional Requirements

Administrators and privileged users must complete:
- CAB process walkthrough (30 minutes)
- Vault access training (20 minutes)
- Observatory/audit log review training (20 minutes)

## 7. Training Records

| Record | Retention | Location |
|---|---|---|
| Signed attestations | 3 years | `docs/evidence/POLICY-ATTESTATION-REGISTER.md` |
| Training completion records | 3 years | HR system / Compliance folder |
| Breach of policy records | 7 years | HR system (disciplinary records) |

## 8. Metrics

| Metric | Target |
|---|---|
| Annual completion rate | 100% |
| Completion within deadline | 95% |
| Incident reports per quarter | <3 missed reports |

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial procedure created |

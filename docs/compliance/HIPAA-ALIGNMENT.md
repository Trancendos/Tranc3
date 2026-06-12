# HIPAA Alignment Programme

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Owner:** Trancendos Platform Engineering
**Standard:** HIPAA §164.308 (Administrative) · §164.312 (Technical) · §164.314 (Organisational)
**Magna Carta Rule:** MC-RULE-009 (health_data checks)

## 1. Scope

This document applies when `HIPAA_PROFILE=enabled` in `config/magna_carta_config.json` and when the platform integrates health-related data (e.g., Sync-Bot wellbeing tier, Tranquility service, tAImra health tracking).

**Current status:** `HIPAA_PROFILE: false` (disabled by default). This programme governs future enablement.

## 2. PHI Boundary Definition

Protected Health Information (PHI) in Tranc3 context:

| Data Type | System | PHI Classification | Handling |
|---|---|---|---|
| Wellbeing scores | Tranquility (:tbd) | PHI if linked to named individual | Encrypted at rest |
| Health integration tokens | Sync-Bot (NID-TMR-01) | PHI-adjacent | Vault-stored only |
| Mental health indicators | I-Mind (:tbd) | PHI | Consent-gated |
| Biometric data | VRAR3D (:tbd) | PHI if health-linked | Prohibited without BAA |

## 3. Technical Safeguards (§164.312)

### Access Control
- Unique user identification: Infinity-One SSO, JWT per session
- Emergency access procedure: Break-glass process via infinity-admin-service
- Automatic logoff: Session expiry enforced in infinity-auth (configurable, default 1h)
- Encryption: AES-GCM (The Void) for PHI at rest; TLS 1.3 in transit

### Audit Controls
- All PHI access logged to The Observatory (workers/monitoring)
- Append-only audit trail, tamper-evident (HMAC signed per entry)
- Retention: 6 years minimum (HIPAA requirement)

### Integrity Controls
- PHI data integrity verified via checksums on write/read
- Vault service provides HMAC-verified secret retrieval

### Transmission Security
- All external interfaces: TLS 1.3 minimum (Traefik enforced)
- No PHI transmitted to unapproved third parties

## 4. Administrative Safeguards (§164.308)

### Security Management
- Risk analysis: `ARCHITECTURE_THREAT_MODEL.md` (STRIDE)
- Risk management: `docs/compliance/RISK-REGISTER.md`
- Sanctions policy: `docs/policies/POL-HR-001` (to be created)
- Information system activity review: Monthly via The Observatory dashboards

### Access Management
- Authorisation/supervision: Role-based (Admin/User/DevOps) via Infinity Gate
- Termination procedures: Infinity-One account deprovisioning
- Access establishment: CAB-gated for admin role assignment

## 5. Organisational Safeguards (§164.314)

### Business Associate Agreements (BAA)

When HIPAA_PROFILE is enabled, BAAs are required with:

| Provider | Service | BAA Required | Status |
|---|---|---|---|
| Fly.io | Backend hosting (if used) | Yes | Pending activation |
| Stripe | Payment processing | No (not PHI) | N/A |
| Ollama/local | AI inference | No (local) | N/A |

### Marketing Claims Tiers (per `src/entities/platform.py`)

| Tier | Description | HIPAA Language Permitted |
|---|---|---|
| Tier A | General wellness, no health claims | No HIPAA references |
| Tier B | Wellbeing tracking, no medical claims | "Wellness support" only |
| Tier C | Health integration, BAA in place | Full HIPAA compliance statements |

## 6. HIPAA Enablement Checklist

Before enabling HIPAA_PROFILE:
- [ ] Legal review of PHI data flows
- [ ] BAA executed with all relevant providers
- [ ] PHI-specific access controls tested
- [ ] Staff trained on HIPAA obligations
- [ ] Breach notification procedure documented (72-hour notice requirement)
- [ ] Annual HIPAA risk assessment scheduled
- [ ] Incident response plan updated for PHI breach scenarios

## 7. Breach Notification Procedure

1. Detect: The Observatory anomaly detection or manual report
2. Assess within 24 hours: Is PHI compromised?
3. Notify HHS within 60 days of discovery
4. Notify affected individuals without unreasonable delay
5. Notify media (if >500 individuals in a state)
6. Document: `docs/evidence/BREACH-LOG.md`

## 8. Compliance Mapping

| HIPAA Section | Requirement | Implementation | Status |
|---|---|---|---|
| §164.308(a)(1) | Risk analysis | ARCHITECTURE_THREAT_MODEL.md | COMPLIANT |
| §164.308(a)(3) | Workforce security | Infinity Gate RBAC | COMPLIANT |
| §164.312(a)(1) | Access control | ZeroTrust IAM | COMPLIANT |
| §164.312(a)(2)(i) | Unique user ID | Infinity-One SSO | COMPLIANT |
| §164.312(b) | Audit controls | The Observatory | COMPLIANT |
| §164.312(c)(1) | Integrity | HMAC verification | COMPLIANT |
| §164.312(e)(1) | Transmission security | TLS 1.3 (Traefik) | COMPLIANT |
| §164.314(a) | BAA with associates | BAA programme | PLANNED (on activation) |

## 9. Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial HIPAA alignment programme |

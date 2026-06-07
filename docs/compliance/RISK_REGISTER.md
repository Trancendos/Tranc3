# ISO 27001:2022 — Information Security Risk Register
**Organisation:** Trancendos Ltd  
**Scope:** Tranc3 Platform  
**Version:** 1.0 | **Date:** 2026-06-07 | **Owner:** ISMS Lead  
**Review cycle:** Quarterly

---

## Risk Rating Matrix

| Likelihood → | Rare (1) | Unlikely (2) | Possible (3) | Likely (4) | Almost Certain (5) |
|---|---|---|---|---|---|
| **Critical (5)** | Medium | High | High | Critical | Critical |
| **Major (4)** | Low | Medium | High | High | Critical |
| **Moderate (3)** | Low | Medium | Medium | High | High |
| **Minor (2)** | Low | Low | Medium | Medium | High |
| **Negligible (1)** | Low | Low | Low | Low | Medium |

**Rating:** Critical ≥ 15 | High 8–14 | Medium 4–7 | Low 1–3

---

## Risk Register

### R-001 — Credential / Secret Exposure

| Field | Value |
|-------|-------|
| **Category** | Confidentiality |
| **Asset** | SECRET_KEY, JWT_SECRET, API tokens |
| **Threat** | Developer accidentally commits secret to git |
| **Vulnerability** | Human error in git operations |
| **Likelihood** | 3 (Possible) |
| **Impact** | 5 (Critical) — full platform compromise |
| **Inherent Risk** | **Critical (15)** |
| **Controls** | gitleaks + detect-secrets pre-commit hooks; `.env` in `.gitignore`; Vault (Shamir unseal); startup validator hard-fails if SECRET_KEY < 32 chars |
| **Residual Likelihood** | 1 (Rare) |
| **Residual Impact** | 5 (Critical) |
| **Residual Risk** | **Medium (5)** |
| **Owner** | Engineering Lead |
| **Treatment** | Reduce — automated scanning + secret rotation policy |
| **Review Date** | 2026-09-07 |

---

### R-002 — Unauthorised Access via JWT Compromise

| Field | Value |
|-------|-------|
| **Category** | Confidentiality / Integrity |
| **Asset** | User sessions, admin access |
| **Threat** | JWT token stolen via XSS or network interception |
| **Vulnerability** | Token-based auth susceptible to theft if not properly protected |
| **Likelihood** | 3 (Possible) |
| **Impact** | 4 (Major) |
| **Inherent Risk** | **High (12)** |
| **Controls** | JWT revocation store (SQLite); short expiry (15 min access / 7 day refresh); httpOnly cookies; TLS-only; MFA enforced for admin |
| **Residual Likelihood** | 2 (Unlikely) |
| **Residual Impact** | 3 (Moderate) |
| **Residual Risk** | **Medium (6)** |
| **Owner** | Security Lead |
| **Treatment** | Reduce |
| **Review Date** | 2026-09-07 |

---

### R-003 — SQL Injection / Injection Attacks

| Field | Value |
|-------|-------|
| **Category** | Integrity / Availability |
| **Asset** | All SQLite databases across 38+ workers |
| **Threat** | Attacker injects malicious SQL via API inputs |
| **Vulnerability** | Dynamic query construction |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 5 (Critical) |
| **Inherent Risk** | **High (10)** |
| **Controls** | Parameterised queries throughout; Pydantic input validation; `test_penetration.py` OWASP suite; bandit SAST |
| **Residual Likelihood** | 1 (Rare) |
| **Residual Impact** | 4 (Major) |
| **Residual Risk** | **Medium (4)** |
| **Owner** | Engineering Lead |
| **Treatment** | Reduce |
| **Review Date** | 2026-12-07 |

---

### R-004 — GDPR Compliance Failure (Data Breach Notification)

| Field | Value |
|-------|-------|
| **Category** | Compliance / Legal |
| **Asset** | Personal data (users table, audit logs) |
| **Threat** | Data breach requiring ICO notification within 72 hours |
| **Vulnerability** | Incomplete breach detection and notification process |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 5 (Critical) — regulatory fines up to 4% global turnover |
| **Inherent Risk** | **High (10)** |
| **Controls** | Observatory audit log; GDPR SAR/erasure endpoints; consent management; 90-day retention policy; ICO registration pending |
| **Residual Likelihood** | 2 (Unlikely) |
| **Residual Impact** | 4 (Major) |
| **Residual Risk** | **High (8)** |
| **Owner** | ISMS Lead |
| **Treatment** | Reduce — complete ICO registration; document breach response procedure |
| **Review Date** | 2026-09-07 |

---

### R-005 — Denial of Service Attack

| Field | Value |
|-------|-------|
| **Category** | Availability |
| **Asset** | All self-hosted workers (ports 8004–8070) |
| **Threat** | DDoS or volumetric attack against public endpoints |
| **Vulnerability** | Self-hosted infrastructure without upstream DDoS scrubbing |
| **Likelihood** | 3 (Possible) |
| **Impact** | 4 (Major) |
| **Inherent Risk** | **High (12)** |
| **Controls** | Rate limiting per worker (token-bucket); Traefik rate limiting; Cryptex (Wazuh) planned; CF WAF for public endpoints |
| **Residual Likelihood** | 2 (Unlikely) |
| **Residual Impact** | 3 (Moderate) |
| **Residual Risk** | **Medium (6)** |
| **Owner** | Infrastructure Lead |
| **Treatment** | Reduce |
| **Review Date** | 2026-09-07 |

---

### R-006 — Supply Chain Compromise (Dependency)

| Field | Value |
|-------|-------|
| **Category** | Integrity |
| **Asset** | Python packages, Node packages |
| **Threat** | Malicious package published to PyPI/npm (typosquatting, takeover) |
| **Vulnerability** | Dependency on third-party packages |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 5 (Critical) |
| **Inherent Risk** | **High (10)** |
| **Controls** | Exact-pinned requirements (no `>=`); weekly pip-audit + safety scan; hash verification planned; Forgejo dependency audit workflow |
| **Residual Likelihood** | 1 (Rare) |
| **Residual Impact** | 4 (Major) |
| **Residual Risk** | **Medium (4)** |
| **Owner** | Engineering Lead |
| **Treatment** | Reduce |
| **Review Date** | 2026-12-07 |

---

### R-007 — Insider Threat / Privilege Abuse

| Field | Value |
|-------|-------|
| **Category** | Confidentiality / Integrity |
| **Asset** | Admin interfaces, user data |
| **Threat** | Malicious or negligent insider misuses elevated privileges |
| **Vulnerability** | Admin roles with broad access |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 4 (Major) |
| **Inherent Risk** | **High (8)** |
| **Controls** | Observatory audit trail for all admin actions; RBAC separation; MFA for admin; Forgejo branch protection prevents unreviewed changes |
| **Residual Likelihood** | 1 (Rare) |
| **Residual Impact** | 4 (Major) |
| **Residual Risk** | **Medium (4)** |
| **Owner** | ISMS Lead |
| **Treatment** | Reduce |
| **Review Date** | 2026-12-07 |

---

### R-008 — AI Model Output Bias / Harmful Content

| Field | Value |
|-------|-------|
| **Category** | Compliance / Reputational |
| **Asset** | Luminous AI inference engine; user-facing AI outputs |
| **Threat** | AI generates discriminatory, harmful, or legally non-compliant content |
| **Vulnerability** | LLM outputs are probabilistic and difficult to fully constrain |
| **Likelihood** | 3 (Possible) |
| **Impact** | 4 (Major) |
| **Inherent Risk** | **High (12)** |
| **Controls** | AI Act compliance baseline; bias evaluation framework; human review for high-risk decisions; output logging to Observatory |
| **Residual Likelihood** | 2 (Unlikely) |
| **Residual Impact** | 3 (Moderate) |
| **Residual Risk** | **Medium (6)** |
| **Owner** | AI Governance Lead |
| **Treatment** | Reduce — implement AI Act conformity assessment |
| **Review Date** | 2026-09-07 |

---

### R-009 — Data Loss (Storage Failure)

| Field | Value |
|-------|-------|
| **Category** | Availability / Integrity |
| **Asset** | SQLite databases across all workers |
| **Threat** | Disk failure or container crash causes data loss |
| **Vulnerability** | SQLite files on single Docker volumes without off-site replication |
| **Likelihood** | 2 (Unlikely) |
| **Impact** | 4 (Major) |
| **Inherent Risk** | **High (8)** |
| **Controls** | WAL mode on all SQLite DBs; Docker volume mounts; Fly.io encrypted volumes; IPFS for content; backup schedule pending |
| **Residual Likelihood** | 2 (Unlikely) |
| **Residual Impact** | 3 (Moderate) |
| **Residual Risk** | **Medium (6)** |
| **Owner** | Infrastructure Lead |
| **Treatment** | Reduce — implement automated off-site backup |
| **Review Date** | 2026-09-07 |

---

### R-010 — Misconfiguration of Infrastructure

| Field | Value |
|-------|-------|
| **Category** | Confidentiality / Availability |
| **Asset** | Traefik, Docker Compose, Vault |
| **Threat** | Misconfiguration exposes internal services or credentials |
| **Vulnerability** | Complex multi-service infrastructure with many configuration files |
| **Likelihood** | 3 (Possible) |
| **Impact** | 4 (Major) |
| **Inherent Risk** | **High (12)** |
| **Controls** | `citadel_preflight.py` config validator; IaC version-controlled; pre-deploy quality gate; `ARCHITECTURE_THREAT_MODEL.md` STRIDE analysis |
| **Residual Likelihood** | 2 (Unlikely) |
| **Residual Impact** | 3 (Moderate) |
| **Residual Risk** | **Medium (6)** |
| **Owner** | Infrastructure Lead |
| **Treatment** | Reduce |
| **Review Date** | 2026-09-07 |

---

## Risk Summary

| Risk ID | Title | Inherent | Residual |
|---------|-------|----------|----------|
| R-001 | Credential / Secret Exposure | Critical | Medium |
| R-002 | JWT Compromise | High | Medium |
| R-003 | SQL Injection | High | Medium |
| R-004 | GDPR Compliance Failure | High | High |
| R-005 | Denial of Service | High | Medium |
| R-006 | Supply Chain Compromise | High | Medium |
| R-007 | Insider Threat | High | Medium |
| R-008 | AI Bias / Harmful Output | High | Medium |
| R-009 | Data Loss | High | Medium |
| R-010 | Infrastructure Misconfiguration | High | Medium |

---

## Treatment Plan — Open Items

| Risk | Action | Owner | Due |
|------|--------|-------|-----|
| R-004 | Complete ICO registration | ISMS Lead | Q3 2026 |
| R-004 | Document 72h breach response procedure | ISMS Lead | Q3 2026 |
| R-005 | Deploy Cryptex (Wazuh) | Security Lead | Q4 2026 |
| R-008 | Complete AI Act conformity assessment | AI Governance Lead | Q4 2026 |
| R-009 | Implement automated off-site SQLite backup | Infrastructure Lead | Q3 2026 |
| All | Annual penetration test by accredited tester | ISMS Lead | Q4 2026 |

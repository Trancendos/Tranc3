# ISO 27001:2022 — Statement of Applicability (SOA)
**Organisation:** Trancendos Ltd  
**Scope:** Tranc3 Platform — all self-hosted workers, infrastructure, data stores, CI/CD  
**Version:** 1.0 | **Date:** 2026-06-07 | **Owner:** ISMS Lead  
**Status:** Draft — targeting ISO 27001:2022 certification Q2 2027

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Applicable and Implemented |
| ⚠️ | Applicable — Partial / In Progress |
| ❌ | Not Applicable (justified below) |

---

## Clause 5 — Organisational Controls

| Ref | Control | App | Status | Evidence |
|-----|---------|-----|--------|----------|
| 5.1 | Policies for information security | ✅ | Implemented | `CLAUDE.md`, `ARCHITECTURE_THREAT_MODEL.md` |
| 5.2 | Information security roles and responsibilities | ⚠️ | Partial | ISMS Lead assigned; full RACI pending |
| 5.3 | Segregation of duties | ⚠️ | Partial | Dev/admin roles separated; formal SoD matrix planned |
| 5.4 | Management responsibilities | ✅ | Implemented | Owner sign-off required for production deploys |
| 5.5 | Contact with authorities | ⚠️ | Planned | ICO registration pending |
| 5.6 | Contact with special interest groups | ⚠️ | Planned | CVE mailing-list subscriptions in place |
| 5.7 | Threat intelligence | ⚠️ | Partial | Cryptex (Wazuh+MISP) planned; pip-audit active |
| 5.8 | Information security in project management | ✅ | Implemented | Security gate in pre-deploy pipeline |
| 5.9 | Inventory of information and other assets | ⚠️ | Partial | `PLATFORM_ENTITIES.md` covers services; data asset register pending |
| 5.10 | Acceptable use of information and assets | ⚠️ | Planned | AUP doc planned |
| 5.11 | Return of assets | ❌ | N/A | Cloud-hosted — no physical hardware issued |
| 5.12 | Classification of information | ⚠️ | Partial | `EventSeverity` enum covers audit; formal taxonomy pending |
| 5.13 | Labelling of information | ⚠️ | Planned | Metadata tagging in Observatory planned |
| 5.14 | Information transfer | ✅ | Implemented | TLS enforced at Traefik; no cleartext inter-service |
| 5.15 | Access control | ✅ | Implemented | Zero Trust IAM (`src/auth/zero_trust.py`), JWT, MFA |
| 5.16 | Identity management | ✅ | Implemented | Infinity-One single identity layer (port 8043) |
| 5.17 | Authentication information | ✅ | Implemented | bcrypt password hashing, TOTP MFA, JWT revocation |
| 5.18 | Access rights | ✅ | Implemented | RBAC (user/admin/moderator) in users-service |
| 5.19 | Information security in supplier relationships | ⚠️ | Partial | Zero-cost architecture minimises suppliers; Fly.io/CF assessed |
| 5.20 | Addressing information security within supplier agreements | ⚠️ | Planned | DPA with Fly.io pending |
| 5.21 | Managing information security in the ICT supply chain | ⚠️ | Partial | `dependency_audit.py` + pip-audit weekly scan |
| 5.22 | Monitoring, review, and change management of supplier services | ⚠️ | Planned | Changelog monitoring via RSS |
| 5.23 | Information security for use of cloud services | ✅ | Implemented | Self-hosted first; CF Workers being decommissioned |
| 5.24 | Information security incident management planning | ⚠️ | Partial | Observatory audit log; incident runbook planned |
| 5.25 | Assessment and decision on information security events | ⚠️ | Partial | Severity tiers in `EventSeverity`; triage process pending |
| 5.26 | Response to information security incidents | ⚠️ | Planned | The Ice Box (Cuckoo) for isolation — planned |
| 5.27 | Learning from information security incidents | ⚠️ | Planned | Post-incident review process to be documented |
| 5.28 | Collection of evidence | ✅ | Implemented | Observatory SQLite audit log (90-day retention) |
| 5.29 | Information security during disruption | ⚠️ | Partial | Docker volume backups; RPO/RTO targets pending |
| 5.30 | ICT readiness for business continuity | ⚠️ | Planned | BCP document planned |
| 5.31 | Legal, statutory, regulatory, and contractual requirements | ⚠️ | Partial | GDPR consent management implemented; full legal register pending |
| 5.32 | Intellectual property rights | ✅ | Implemented | All code proprietary; open-source licences audited |
| 5.33 | Protection of records | ✅ | Implemented | Append-only audit log; WAL+FULL sync SQLite |
| 5.34 | Privacy and protection of PII | ✅ | Implemented | GDPR SAR/erasure endpoints; consent management; data minimisation |
| 5.35 | Independent review of information security | ⚠️ | Planned | Annual external audit planned for Q4 2026 |
| 5.36 | Compliance with policies, rules, and standards | ⚠️ | Partial | Automated compliance gate (DEFSTAN ≥70%); full audit pending |
| 5.37 | Documented operating procedures | ⚠️ | Partial | `CLAUDE.md` covers development; ops runbooks planned |

---

## Clause 6 — People Controls

| Ref | Control | App | Status | Evidence |
|-----|---------|-----|--------|----------|
| 6.1 | Screening | ⚠️ | Planned | Background check process for contributors planned |
| 6.2 | Terms and conditions of employment | ⚠️ | Partial | Contractor agreements reference data handling |
| 6.3 | Information security awareness, education, and training | ⚠️ | Planned | The Academy (LMS) planned |
| 6.4 | Disciplinary process | ⚠️ | Planned | HR process to be documented |
| 6.5 | Responsibilities after termination | ⚠️ | Planned | Offboarding checklist — access revocation via Infinity Admin |
| 6.6 | Confidentiality or non-disclosure agreements | ⚠️ | Partial | NDAs in contractor agreements |
| 6.7 | Remote working | ✅ | Implemented | Zero Trust IAM enforces device posture for remote access |
| 6.8 | Information security event reporting | ✅ | Implemented | Observatory event bus; SECURITY severity events trigger Cryptex |

---

## Clause 7 — Physical Controls

> **Justification for N/A:** Trancendos operates an entirely cloud-hosted and remote infrastructure.
> No physical premises, server rooms, or hardware assets are in scope.

| Ref | Control | App | Status | Evidence |
|-----|---------|-----|--------|----------|
| 7.1 | Physical security perimeters | ❌ | N/A | Cloud-hosted; no physical premises |
| 7.2 | Physical entry | ❌ | N/A | Cloud-hosted |
| 7.3 | Securing offices, rooms, and facilities | ❌ | N/A | Cloud-hosted |
| 7.4 | Physical security monitoring | ❌ | N/A | Cloud-hosted |
| 7.5 | Protecting against physical and environmental threats | ❌ | N/A | Delegated to cloud providers |
| 7.6 | Working in secure areas | ❌ | N/A | Cloud-hosted |
| 7.7 | Clear desk and clear screen | ❌ | N/A | Remote-only workforce |
| 7.8 | Equipment siting and protection | ❌ | N/A | Cloud-hosted |
| 7.9 | Security of assets off-premises | ❌ | N/A | Cloud-hosted |
| 7.10 | Storage media | ❌ | N/A | Cloud volumes; no physical media |
| 7.11 | Supporting utilities | ❌ | N/A | Delegated to cloud providers |
| 7.12 | Cabling security | ❌ | N/A | Cloud-hosted |
| 7.13 | Equipment maintenance | ❌ | N/A | Cloud-hosted |
| 7.14 | Secure disposal or re-use of equipment | ❌ | N/A | Cloud volumes destroyed by provider |

---

## Clause 8 — Technological Controls

| Ref | Control | App | Status | Evidence |
|-----|---------|-----|--------|----------|
| 8.1 | User endpoint devices | ⚠️ | Partial | Device posture in Zero Trust IAM; MDM planned |
| 8.2 | Privileged access rights | ✅ | Implemented | Admin role restricted; sudo auditing via Observatory |
| 8.3 | Information access restriction | ✅ | Implemented | RBAC + JWT scope enforcement across all workers |
| 8.4 | Access to source code | ✅ | Implemented | Forgejo (The Workshop) with branch protection |
| 8.5 | Secure authentication | ✅ | Implemented | MFA (TOTP), bcrypt, JWT, PKCE OAuth2 |
| 8.6 | Capacity management | ⚠️ | Partial | Prometheus metrics; auto-scaling planned |
| 8.7 | Protection against malware | ⚠️ | Partial | pip-audit, bandit, gitleaks in CI; Wazuh planned |
| 8.8 | Management of technical vulnerabilities | ✅ | Implemented | Weekly `dependency_audit.py`; Forgejo security scan |
| 8.9 | Configuration management | ✅ | Implemented | Docker Compose + Traefik; IaC version-controlled |
| 8.10 | Information deletion | ✅ | Implemented | GDPR erasure endpoint; 90-day audit log retention |
| 8.11 | Data masking | ⚠️ | Partial | `sanitize_for_log()` in Observatory; PII masking in exports pending |
| 8.12 | Data leakage prevention | ⚠️ | Partial | gitleaks + detect-secrets in pre-commit; DLP policy planned |
| 8.13 | Information backup | ⚠️ | Partial | Docker volume mounts; off-site backup schedule pending |
| 8.14 | Redundancy of information processing facilities | ⚠️ | Planned | Multi-region Fly.io; HA for self-hosted workers planned |
| 8.15 | Logging | ✅ | Implemented | Observatory ring buffer + SQLite + Loki (30-day) |
| 8.16 | Monitoring activities | ✅ | Implemented | Prometheus + Grafana dashboards; health aggregator (port 8029) |
| 8.17 | Clock synchronisation | ✅ | Implemented | NTP via host OS; ISO 8601 UTC timestamps throughout |
| 8.18 | Use of privileged utility programs | ⚠️ | Partial | Admin endpoints require `X-Internal-Secret`; full PAM pending |
| 8.19 | Installation of software on operational systems | ✅ | Implemented | Immutable Docker images; no runtime installs |
| 8.20 | Networks security | ✅ | Implemented | Traefik TLS termination; internal Docker network isolation |
| 8.21 | Security of network services | ✅ | Implemented | CORS policies; rate limiting per worker |
| 8.22 | Segregation of networks | ✅ | Implemented | Docker networks per service tier |
| 8.23 | Web filtering | ⚠️ | Planned | Outbound proxy filtering planned |
| 8.24 | Use of cryptography | ✅ | Implemented | AES-GCM (The Void); TLS 1.3; bcrypt; PBKDF2 |
| 8.25 | Secure development lifecycle | ✅ | Implemented | Pre-commit hooks (bandit, semgrep, gitleaks); Forgejo CI |
| 8.26 | Application security requirements | ✅ | Implemented | OWASP checks in `test_penetration.py`; DEFSTAN gate ≥70% |
| 8.27 | Secure system architecture and engineering principles | ✅ | Implemented | Zero Trust, defence-in-depth, least privilege throughout |
| 8.28 | Secure coding | ✅ | Implemented | ruff, bandit, mypy; SAST via semgrep |
| 8.29 | Security testing in development and acceptance | ✅ | Implemented | `test_chaos.py`, `test_penetration.py`, `test_compliance.py` |
| 8.30 | Outsourced development | ❌ | N/A | All development in-house |
| 8.31 | Separation of development, test, and production environments | ✅ | Implemented | Separate Fly.io apps; Docker Compose profiles |
| 8.32 | Change management | ✅ | Implemented | PR-based workflow; Forgejo branch protection |
| 8.33 | Test information | ✅ | Implemented | Synthetic test data only; no production PII in tests |
| 8.34 | Protection of information systems during audit testing | ✅ | Implemented | Read-only audit access; no production DB access during tests |

---

## Summary

| Category | Total | ✅ Implemented | ⚠️ Partial/Planned | ❌ N/A |
|----------|-------|---------------|-------------------|--------|
| Clause 5 (Organisational) | 37 | 13 | 22 | 2 |
| Clause 6 (People) | 8 | 2 | 6 | 0 |
| Clause 7 (Physical) | 14 | 0 | 0 | 14 |
| Clause 8 (Technological) | 34 | 24 | 9 | 1 |
| **Total** | **93** | **39** | **37** | **17** |

---

## Certification Roadmap

| Milestone | Target |
|-----------|--------|
| Risk Register complete | Q3 2026 |
| All P0/P1 controls fully implemented | Q4 2026 |
| Internal audit | Q1 2027 |
| Stage 1 (documentation review) | Q2 2027 |
| Stage 2 (certification audit) | Q2 2027 |

# SOC 2 Type II — Trust Services Criteria Mapping
**Organisation:** Trancendos Ltd  
**Scope:** Tranc3 Platform — all self-hosted workers, infrastructure, data stores, CI/CD  
**Version:** 1.0 | **Date:** 2026-06-07 | **Owner:** ISMS Lead  
**Evidence Period:** 2026-06-07 → 2026-12-07 (6 months)  
**Target Report Date:** Q1 2027

---

## Overview

SOC 2 Type II attests that the Trancendos platform's controls operate **effectively over the evidence period** (minimum 6 months). Controls map to AICPA Trust Services Criteria (TSC): Security (CC), Availability (A), Confidentiality (C), Processing Integrity (PI), and Privacy (P).

All five Trust Service Categories are in scope.

---

## Evidence Collection Schedule

| Frequency | Activity | Owner | Tool |
|-----------|----------|-------|------|
| Continuous | Observatory audit log flush to SQLite | Automated | `src/observability/observatory.py` |
| Continuous | Prometheus metrics / Grafana dashboards | Automated | `monitoring/prometheus.yml` |
| Continuous | Loki log aggregation (30-day rolling) | Automated | `monitoring/loki.yml` |
| Daily | Health aggregator status snapshot | Automated | `workers/health-aggregator/` |
| Weekly | Dependency vulnerability scan (pip-audit, bandit) | Automated | `.forgejo/workflows/dependency-audit.yml` |
| Monthly | Access review — admin role holders | ISMS Lead | `scripts/soc2_evidence_collector.py` |
| Monthly | JWT revocation log export | Security Lead | `workers/infinity-auth/` |
| Monthly | Key rotation status check | Security Lead | `src/security/key_rotation.py` |
| Quarterly | Penetration test results | Engineering Lead | `tests/test_penetration.py` |
| Quarterly | Chaos / resilience test results | Engineering Lead | `tests/test_chaos.py` |
| Quarterly | Compliance gate score (DEFSTAN ≥70%) | Automated | `tests/test_compliance.py` |
| Quarterly | Risk register review | ISMS Lead | `docs/compliance/RISK_REGISTER.md` |
| Per-incident | Incident response record | Security Lead | Observatory `EventSeverity.SECURITY` |

---

## CC — Common Criteria (Security)

### CC1 — Control Environment

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC1.1 | COSO — demonstrates commitment to integrity and ethical values | ✅ | `CLAUDE.md` security constraints; proprietary code policy |
| CC1.2 | Board oversight of internal control | ⚠️ | Owner sign-off required for production deploys (`5.4` SOA) |
| CC1.3 | Organisational structures, reporting lines, authority | ✅ | ISMS Lead, Engineering Lead, Security Lead, AI Governance Lead assigned |
| CC1.4 | Commitment to attract, develop, and retain competent individuals | ⚠️ | The Academy (LMS) planned; contractor NDAs in place |
| CC1.5 | Accountability for internal control responsibilities | ✅ | Observatory audit trail; RBAC enforcement |

### CC2 — Communication and Information

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC2.1 | Obtains and uses relevant quality information | ✅ | Prometheus + Grafana; Observatory feed |
| CC2.2 | Internal communication of control information | ✅ | `CLAUDE.md`; `PLATFORM_ENTITIES.md`; SOA and Risk Register |
| CC2.3 | External communication to relevant parties | ⚠️ | ICO registration pending; public security policy planned |

### CC3 — Risk Assessment

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC3.1 | Specifies objectives to identify and assess risks | ✅ | `docs/compliance/RISK_REGISTER.md` |
| CC3.2 | Identifies and analyses risks | ✅ | STRIDE analysis (`ARCHITECTURE_THREAT_MODEL.md`); 10-risk register |
| CC3.3 | Assesses fraud risk | ✅ | Insider threat R-007 in risk register; Observatory audit trail |
| CC3.4 | Identifies and assesses changes that could affect internal control | ✅ | PR-based workflow + Forgejo branch protection |

### CC4 — Monitoring Activities

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC4.1 | Selects, develops, and performs ongoing monitoring | ✅ | Prometheus + health aggregator; Observatory ring buffer |
| CC4.2 | Evaluates and communicates deficiencies | ⚠️ | Cryptex (Wazuh) planned; manual escalation process pending |

### CC5 — Control Activities

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC5.1 | Selects and develops control activities to mitigate risk | ✅ | RBAC, JWT, MFA, rate limiting, parameterised queries throughout |
| CC5.2 | Selects and develops technology general controls | ✅ | Bandit, semgrep, gitleaks pre-commit; Forgejo CI SAST |
| CC5.3 | Deploys through policies and procedures | ✅ | `CLAUDE.md` policies; Forgejo pipeline as policy-as-code |

### CC6 — Logical and Physical Access Controls

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC6.1 | Logical access security software, infrastructure, and architectures | ✅ | Zero Trust IAM (`src/auth/zero_trust.py`); JWT + MFA; bcrypt hashing |
| CC6.2 | Prior to issuing system credentials, registers and authorises | ✅ | User registration via Infinity Portal with email verification |
| CC6.3 | Removes access to protected information assets when no longer required | ✅ | JWT revocation store; account soft-delete + GDPR erasure endpoint |
| CC6.4 | Physical access restrictions | ❌ | N/A — cloud-hosted; no physical premises |
| CC6.5 | Logical access restrictions for protected information | ✅ | RBAC + scope enforcement; `X-Internal-Secret` on admin routes |
| CC6.6 | Logical access security measures against threats from outside | ✅ | Traefik TLS; CORS policies; rate limiting per worker; CF WAF |
| CC6.7 | Restricts transmission, movement, and removal of information | ✅ | TLS-only; no cleartext inter-service; httpOnly cookies |
| CC6.8 | Prevents or detects unauthorised or malicious software | ✅ | Immutable Docker images; pip-audit; bandit SAST |

### CC7 — System Operations

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC7.1 | Detects and monitors new vulnerabilities | ✅ | Weekly `dependency_audit.py`; CVE mailing list subscriptions |
| CC7.2 | Monitors system components for anomalous behaviour | ✅ | Prometheus alerts; Observatory SECURITY events |
| CC7.3 | Evaluates security events to determine if they are security incidents | ⚠️ | `EventSeverity.SECURITY` triage; incident runbook planned |
| CC7.4 | Responds to identified security incidents | ⚠️ | The Ice Box (Cuckoo) planned; manual procedure in place |
| CC7.5 | Identifies, develops, and implements changes to mitigate security incidents | ✅ | Post-incident PR workflow; Forgejo branch protection |

### CC8 — Change Management

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC8.1 | Authorises, designs, develops, configures, documents, tests, approves, and implements changes | ✅ | PR-based + review gate; `test_compliance.py` DEFSTAN ≥70% gate |

### CC9 — Risk Mitigation

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| CC9.1 | Identifies and addresses risks from use of vendors and business partners | ✅ | `dependency_audit.py` + pip-audit; exact-pinned requirements |
| CC9.2 | Assesses and manages risks associated with business disruption | ⚠️ | Docker volume backups; BCP planned |

---

## A — Availability

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| A1.1 | Capacity planning | ⚠️ | Prometheus metrics; auto-scaling planned |
| A1.2 | Environmental protections | ❌ | N/A — delegated to cloud providers (Fly.io) |
| A1.3 | Backup and recovery | ⚠️ | WAL-mode SQLite; Docker volumes; off-site backup pending |

---

## C — Confidentiality

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| C1.1 | Identifies confidential information | ✅ | `EventSeverity` taxonomy; Observatory `SECRETS` category |
| C1.2 | Disposes of confidential information | ✅ | GDPR erasure endpoint; 90-day audit log retention + purge |

---

## PI — Processing Integrity

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| PI1.1 | Obtains or generates complete, accurate, valid inputs | ✅ | Pydantic v2 validation throughout all workers |
| PI1.2 | Protects inputs, during processing, and in storage against corruption | ✅ | WAL+FULL sync SQLite; AES-GCM for secrets |
| PI1.3 | Produces complete, accurate, and valid outputs | ✅ | Parameterised queries; Pydantic response models |
| PI1.4 | Addresses processing errors and exceptions | ✅ | Observatory error events; circuit breaker in Service Mesh |
| PI1.5 | Stores inputs and outputs completely and accurately | ✅ | Append-only audit log; INSERT OR IGNORE deduplication |

---

## P — Privacy

| Ref | Criterion | Status | Evidence |
|-----|-----------|--------|----------|
| P1.1 | Provides notice to data subjects | ⚠️ | GDPR consent flags implemented; full privacy notice planned |
| P2.1 | Communicates choices for collection, use, retention | ✅ | Consent management (`/users/{id}/consent`); 5 granular flags |
| P3.1 | Collects personal information consistent with objectives | ✅ | Data minimisation; only required fields collected |
| P3.2 | Collects personal information using appropriate methods | ✅ | TLS-only; MFA; httpOnly cookies |
| P4.1 | Limits use of personal information | ✅ | RBAC; `X-Internal-Secret` admin gate |
| P4.2 | Retains personal information for appropriate timeframe | ✅ | 90-day audit log retention; GDPR erasure; `deleted_at` soft-delete |
| P4.3 | Disposes of personal information | ✅ | `DELETE /users/{id}/data` hard-erasure with unique placeholder |
| P5.1 | Grants data subjects access to their information | ✅ | `GET /users/{id}/data-export` (JSON + CSV) |
| P5.2 | Corrects inaccurate personal information | ✅ | `PUT /users/{id}` update endpoint |
| P6.1 | Discloses personal information to third parties with subject consent | ✅ | `data_sharing` consent flag gating external transfers |
| P6.2 | Discloses personal information only to properly authorised third parties | ✅ | No third-party sharing in current scope; consent flag enforced |
| P6.3 | Protects personal information of third parties | ✅ | Zero-cost architecture minimises third-party exposure |
| P6.4 | Notifies third parties of obligations for personal information | ⚠️ | DPA with Fly.io pending |
| P6.5 | Provides notification of breaches and incidents | ⚠️ | 72h breach procedure planned (R-004 treatment) |
| P6.6 | Documents personal information disclosures | ✅ | Observatory `DATA` category events |
| P6.7 | Provides de-identified information | ✅ | `sanitize_for_log()` in Observatory |
| P7.1 | Collects and maintains accurate personal information | ✅ | Pydantic validation; update endpoints |
| P8.1 | Provides process to submit and address privacy complaints | ⚠️ | SAR endpoint live; complaint routing process planned |

---

## Open Evidence Gaps

| Item | Gap | Owner | Due |
|------|-----|-------|-----|
| CC2.3 | Publish external-facing security policy / responsible disclosure | ISMS Lead | Q3 2026 |
| CC4.2 | Deploy Cryptex (Wazuh) for automated deficiency alerts | Security Lead | Q4 2026 |
| CC7.3 | Document formal incident triage procedure | Security Lead | Q3 2026 |
| CC9.2 | Document and test BCP / DRP | Infrastructure Lead | Q3 2026 |
| A1.3 | Implement automated off-site SQLite backup | Infrastructure Lead | Q3 2026 |
| P1.1 | Publish full privacy notice linked from UI | ISMS Lead | Q3 2026 |
| P6.4 | Execute DPA with Fly.io | ISMS Lead | Q3 2026 |
| P6.5 | Document and test 72h breach notification procedure | ISMS Lead | Q3 2026 |

---

## Evidence Artefacts Index

Automated artefacts collected by `scripts/soc2_evidence_collector.py`:

| Artefact | Source | Retention |
|----------|--------|-----------|
| `audit_snapshot_YYYYMM.json` | Observatory SQLite audit DB | Evidence period + 1 year |
| `access_review_YYYYMM.json` | Users-service admin role query | Evidence period + 1 year |
| `jwt_revocations_YYYYMM.json` | Infinity-auth revocation store | Evidence period + 1 year |
| `dependency_scan_YYYYMMDD.json` | pip-audit + bandit output | Evidence period + 1 year |
| `health_snapshot_YYYYMMDD.json` | Health aggregator `/health/all` | 90 days rolling |
| `key_rotation_log_YYYYMM.json` | Key rotation service | Evidence period + 1 year |
| `compliance_gate_YYYYMMDD.json` | `test_compliance.py` results | Evidence period + 1 year |
| `data_residency_YYYYMM.json` | Data residency enforcement log | Evidence period + 1 year |

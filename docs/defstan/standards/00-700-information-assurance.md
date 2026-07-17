# DEF STAN 00-700 — Information Assurance

**Standard:** DEF STAN 00-700 (adapted for civilian public platform)  
**Area Code:** IA  
**Status Summary:** 9 COMPLIANT, 1 PARTIAL  
**Score:** ~85%

## Purpose

Establishes information assurance requirements across the Tranc3 / Trancendos platform. Covers authentication, secrets management, transport security, input validation, rate limiting, audit logging, session management, CORS policy, dependency vulnerability management, and data encryption at rest.

## Applicability to Tranc3

All public-facing services, internal APIs, and infrastructure components. The platform processes user credentials, financial data (Royal Bank of Arcadia), AI model outputs, and operational telemetry.

## Requirements

### REQ-IA-001 — Authentication and Access Control

**Description:** All platform endpoints must enforce authentication. Unauthenticated requests must be rejected with a defined error response. RBAC must be enforced at the service boundary.

**Implementation Evidence:**
- `src/auth/zero_trust.py` — Zero Trust IAM with device posture, MFA, geographic policies, risk scoring
- `src/auth/dependencies.py` — FastAPI auth dependency on all protected routes
- `tests/test_zero_trust.py` — Zero trust boundary tests
- `tests/test_penetration.py` — Auth boundary penetration tests

**Compliance Status:** COMPLIANT  
**Verification:** Code review + test

---

### REQ-IA-002 — Secrets and Credential Management

**Description:** Secrets must be stored in a dedicated vault using AES-GCM encryption. Never in source code, logs, or committed configs.

**Implementation Evidence:**
- `cloudflare/infinity-void/` — The Void: AES-GCM vault, PBKDF2 key derivation (100k iterations)
- `workers/vault-service/` — Self-hosted vault (port 8038), migration from CF Worker

**Compliance Status:** COMPLIANT  
**Verification:** Code review

---

### REQ-IA-003 — Transport Layer Security

**Description:** All external-facing endpoints must use TLS 1.2+. Unencrypted HTTP rejected/redirected.

**Implementation Evidence:**
- `docker-compose.production.yml` — Traefik TLS termination
- `cloudflare/trancendos-api-gateway/` — Cloudflare edge TLS enforcement

**Compliance Status:** COMPLIANT  
**Verification:** Inspection

---

### REQ-IA-004 — Input Validation and Injection Prevention

**Description:** All user-supplied input validated against defined schema. SQL/command injection and XSS blocked.

**Implementation Evidence:**
- `src/validation/loop_validator.py` — Loop and cascade failure validation
- `Dimensional/sanitize.py` — Input sanitisation across all modules
- `tests/test_penetration.py` — OWASP A03 injection tests
- `tests/test_validation.py` — Schema enforcement tests

**Compliance Status:** COMPLIANT  
**Verification:** Test

---

### REQ-IA-005 — Rate Limiting and DoS Protection

**Description:** Rate limits per tenant and per IP. Violations logged and returned as defined error codes.

**Implementation Evidence:**
- `src/monetisation/billing.py` — Tiered rate limits: free 100/hr, pro 1k/hr, business 10k/hr
- `workers/rate-limit-service/` — Token-bucket rate limiter (port 8026)

**Compliance Status:** COMPLIANT  
**Verification:** Test

---

### REQ-IA-006 — Audit Logging

**Description:** All security-relevant events logged with timestamp, user identity, source IP, action. Tamper-evident.

**Implementation Evidence:**
- `src/observability/` — The Observatory: structured audit logging, W3C TraceContext
- `workers/audit-service/` — Audit service (port 8025)

**Compliance Status:** COMPLIANT  
**Verification:** Code review

---

### REQ-IA-007 — Session Management

**Description:** Sessions have bounded lifetimes, invalidated on logout, resistant to fixation/hijacking. Tokens cryptographically random.

**Implementation Evidence:**
- `src/auth/zero_trust.py` — Session management with MFA and device posture
- `workers/infinity-auth/` — OAuth2/SSO/MFA engine (port 8005)

**Compliance Status:** COMPLIANT  
**Verification:** Test

---

### REQ-IA-008 — CORS Policy Enforcement

**Description:** Explicit CORS configuration. No wildcard origins on authenticated endpoints.

**Implementation Evidence:**
- `api.py` — FastAPI CORSMiddleware with ALLOWED_ORIGINS
- `tests/test_penetration.py` — CORS boundary tests (OWASP A01)

**Compliance Status:** COMPLIANT  
**Verification:** Code review

---

### REQ-IA-009 — Dependency Vulnerability Management

**Description:** Third-party dependencies scanned for CVEs on every merge. High/critical resolved within SLA.

**Implementation Evidence:**
- `.forgejo/workflows/dependency-audit.yml` — pip-audit, Safety, npm audit (weekly + on PR)
- `.forgejo/workflows/security-scan.yml` — bandit, safety, ruff

**Compliance Status:** COMPLIANT  
**Verification:** Audit

---

### REQ-IA-010 — Data at Rest Encryption

**Description:** Sensitive data encrypted at rest (AES-256 or equivalent). Keys managed separately.

**Implementation Evidence:**
- `cloudflare/infinity-void/` — AES-GCM encrypted vault
- `fly.toml` — 1GB encrypted volume at /app/models

**Compliance Status:** PARTIAL  
**Gap:** SQLite workers (38 services) lack at-rest encryption. See Waiver WAV-003.  
**Verification:** Inspection

---

### REQ-IA-011 — Email/Domain Authentication (Anti-Spoofing)

**Description:** DNS-based sender authentication (SPF, DKIM, DMARC) in place for any domain able to send mail on the platform's behalf, so receivers can distinguish legitimate mail from spoofed/phishing mail impersonating the domain.

**Implementation Evidence:**
- `deploy/terraform/oci-citadel-dns.tf` — `cloudflare_record.spf`, `cloudflare_record.dmarc`
- `docs/architecture/ea-workbook/12b_dns_records.csv` — DNSR-005 (SPF), DNSR-006 (DMARC)
- `workers/email-service/worker.py` — the only component capable of sending mail from `trancendos.com`; `SMTP_HOST` is an unconfigured, bring-your-own relay (empty by default → log-only mode)

**Compliance Status:** PARTIAL  
**Gap:** SPF is `v=spf1 -all` (authorizes no sender — correct given no relay is configured, but means legitimate mail can't be sent yet either) and DMARC is `p=none` (monitor-only). No DKIM record exists, since DKIM requires a selector/key pair from an actual sending service. All three need updating together once `SMTP_HOST` is pointed at a real relay: add that relay's SPF `include:`/`ip4:`, publish its DKIM selector, then tighten DMARC to `p=quarantine` then `p=reject` once aggregate reports (routed to `dmarc-reports@trancendos.com`) confirm alignment. The `dmarc-reports@` mailbox itself does not exist yet either — create it (or repoint `rua`/`ruf`) before relying on reports.  
**Verification:** Inspection (DNS query for `trancendos.com` TXT and `_dmarc.trancendos.com` TXT)

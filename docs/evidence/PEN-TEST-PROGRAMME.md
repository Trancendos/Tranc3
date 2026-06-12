# Penetration Test Programme

**Version:** 1.0.0 | **Date:** 2026-06-12
**Framework:** ISO 27001 A.8.8 · SOC 2 CC7.1 · Magna Carta MC-010

## 1. Programme Overview

Annual penetration testing programme for the Tranc3 platform covering all internet-exposed attack surfaces. Internal red team exercises conducted quarterly.

## 2. Scope

### External (Annual — Professional Pen Tester)
- Traefik reverse proxy (443/80 ingress)
- All P0/P1 worker APIs exposed via Traefik
- Authentication flows (infinity-portal, infinity-auth)
- OAuth2/JWT implementation

### Internal (Quarterly — Internal Red Team)
- Container escape vectors
- Service-to-service trust boundaries
- SQLite file access controls
- Secret exposure via logs/environment

### Out of Scope
- Third-party services (Stripe, Cloudflare) — tested by vendor
- Physical infrastructure — N/A (cloud/VPS hosted)

## 3. Schedule

| Test ID | Type | Scope | Planned Date | Status | Provider |
|---|---|---|---|---|---|
| PT-2026-001 | Internal red team | Auth flows + API surface | 2026-09-30 | Planned | Internal |
| PT-2026-002 | External professional | Full external surface | 2026-12-15 | Planned | TBD |
| PT-2027-001 | Internal red team | Container/infra | 2027-03-31 | Planned | Internal |
| PT-2027-002 | External professional | Full external surface | 2027-12-15 | Planned | TBD |

## 4. Internal Test Methodology

### Reconnaissance
- Service enumeration via Docker Compose service map
- Port scanning (localhost only — no external scanning)
- API surface mapping from worker OpenAPI specs

### Authentication Testing
- JWT algorithm confusion attacks
- Token replay/expiry bypass
- OAuth2 PKCE implementation review
- CAB gate bypass attempts

### Injection Testing
- SQL injection against SQLite-backed endpoints
- Command injection in file processing (ffmpeg-worker)
- SSRF in AI gateway URL handling
- Path traversal in files-service

### Access Control Testing
- Horizontal privilege escalation between users
- Vertical privilege escalation to admin
- IDOR in resource identifiers
- CAB gate bypass via header manipulation

## 5. Findings Management

| Severity | CVSS Range | Response Time | Escalation |
|---|---|---|---|
| Critical | 9.0–10.0 | Immediate (24h) | Platform Eng + Management |
| High | 7.0–8.9 | 7 days | Platform Eng |
| Medium | 4.0–6.9 | 30 days | Sprint backlog |
| Low | 0.1–3.9 | 90 days | Backlog |
| Informational | 0.0 | Next review | Reference only |

## 6. Test Results Archive

| Test ID | Date | Findings (C/H/M/L) | Remediated | Report |
|---|---|---|---|---|
| PT-2026-001 | TBD | TBD | TBD | TBD |

## 7. Remediation Tracking

All pen test findings are logged in `docs/compliance/COMPLIANCE-ACTION-TRACKER.md` with:
- Finding reference number
- Severity
- Affected component
- Remediation owner
- Target remediation date
- Verification date

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial pen test programme |

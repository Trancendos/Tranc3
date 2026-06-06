# Privacy Impact Assessment (PIA)

> **Document ID:** PIA-001  
> **Classification:** UNCLASSIFIED — PUBLIC  
> **DEF STAN ref:** REQ-TD-006 (DEF STAN 05-057)  
> **GDPR Articles:** Art. 13, 14, 25, 30, 35  
> **Version:** 1.0  
> **Date:** 2026-06-06  
> **Owner:** Trancendos  
> **Review cycle:** Annual or on material change  

---

## 1. Purpose and Scope

This Privacy Impact Assessment (PIA) evaluates the privacy risks of the
Tranc3 / Trancendos platform and documents the controls in place to protect
personal data in accordance with UK GDPR and the Data Protection Act 2018.

**In scope:** All data processing activities of the Trancendos platform
including user authentication, AI inference, chat history, settings storage,
and observability/audit logging.

**Out of scope:** Third-party services where Trancendos acts as data
processor (Fly.io hosting, Cloudflare CDN) — these are covered by their
respective PIAs and DPAs.

---

## 2. Data Controller Details

| Field | Value |
|---|---|
| **Controller** | Trancendos |
| **Contact** | victicnor@gmail.com |
| **DPO** | Not required (below threshold) |

---

## 3. Personal Data Inventory

| Category | Data Elements | Legal Basis | Retention |
|---|---|---|---|
| Account data | username, hashed password | Contractual necessity (Art. 6(1)(b)) | Duration of account + 30 days |
| Session data | JWT tokens, session timestamps | Legitimate interest (Art. 6(1)(f)) | 24 hours (tokens), 90 days (logs) |
| AI interaction | Prompt text, generated responses | Contractual necessity | 90 days, user-deletable |
| Settings | Encrypted user preferences | Contractual necessity | Duration of account |
| Observability | Request IDs, anonymised IP, response times | Legitimate interest | 30 days rolling |
| Audit log | User ID, action, timestamp | Legal obligation (Art. 6(1)(c)) | 7 years |

### Special Category Data
No special category data (Art. 9) is knowingly processed. Users are
prohibited by Terms of Service from submitting health, biometric, or
other special category data as prompts.

---

## 4. Data Flow Diagram

```
User (Browser)
    │ HTTPS / TLS 1.3
    ▼
Traefik (reverse proxy) ─── rate limiting, TLS termination
    │
    ▼
tranc3-backend (FastAPI :8000)
    ├── Auth: hashed passwords → PostgreSQL
    ├── Session: JWT (signed, not encrypted) → stateless
    ├── AI prompts → AI Gateway (:8009)
    │       ├── Tier 1: Ollama (local, no data leaves server)
    │       ├── Tier 2: HuggingFace (data transferred to HF servers)
    │       ├── Tier 3: OpenRouter (data transferred to OpenRouter)
    │       └── Tier 5: Offline stub (no external transfer)
    ├── Settings → PostgreSQL (AES-GCM encrypted at application layer)
    └── Audit log → The Observatory (SQLite, local)
```

**Cross-border transfers:** When AI Gateway falls back to HuggingFace
(Tier 2) or OpenRouter (Tier 3), prompt text is transferred to servers
potentially outside the UK/EEA. Standard Contractual Clauses apply where
applicable. Users are informed of this in the Privacy Notice.

---

## 5. Privacy Risks and Controls

| Risk ID | Risk | Likelihood | Impact | Control | Residual |
|---|---|---|---|---|---|
| R-001 | Password exposure | Low | High | bcrypt hashing (cost 12) | Low |
| R-002 | JWT token theft | Medium | High | Short TTL (24h), HTTPS only | Low |
| R-003 | Prompt data at AI provider | Medium | Medium | User consent, SCCs, Tier 1 preferred | Low |
| R-004 | Settings data exposure | Low | High | AES-GCM encryption at rest | Very Low |
| R-005 | Audit log PII | Low | Low | User IDs only (no names in logs) | Very Low |
| R-006 | AI output contains PII | Medium | Medium | OutputSafetyFilter (src/core/output_safety.py) | Low |
| R-007 | Unauthorised data access | Low | High | Zero Trust IAM, device posture checks | Low |

---

## 6. Data Subject Rights

| Right | Implementation |
|---|---|
| Access (Art. 15) | `GET /user/settings` returns all user data |
| Rectification (Art. 16) | `PUT /user/settings` |
| Erasure (Art. 17) | `DELETE /gdpr/erase/{user_id}` — full account + log pseudonymisation |
| Portability (Art. 20) | `GET /user/export` — JSON export |
| Object (Art. 21) | Opt-out of analytics via settings |

GDPR erasure endpoint: `api.py` line ~1628 (`/gdpr/erase/{user_id}`).

---

## 7. Privacy by Design Measures

- **Data minimisation** — only username + hashed password stored at registration; no email required
- **Encryption at rest** — settings encrypted with AES-GCM before database storage (The Void / `src/auth/`)
- **Encryption in transit** — TLS 1.3 enforced at Traefik; HSTS headers set
- **Anonymisation** — observability logs use request IDs, not usernames
- **Access control** — Zero Trust IAM with device posture, MFA support
- **Output filtering** — `OutputSafetyFilter` blocks PII patterns in AI responses

---

## 8. PIA Conclusion

Processing is **proportionate** and **necessary** for the stated purposes.
Identified risks have been mitigated to acceptable levels through the
controls listed above.

**Next review date:** 2027-06-06 or on material change to data flows.

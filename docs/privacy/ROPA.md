# Record of Processing Activities (ROPA)

> **Document ID:** ROPA-001  
> **Classification:** UNCLASSIFIED — PUBLIC  
> **GDPR Article:** Art. 30  
> **Version:** 1.0  
> **Date:** 2026-06-06  
> **Controller:** Trancendos  

---

## Processing Activity 1: User Account Management

| Field | Detail |
|---|---|
| **Activity** | User registration, authentication, account management |
| **Purpose** | Enable users to access the Tranc3 platform |
| **Legal basis** | Art. 6(1)(b) — contractual necessity |
| **Data categories** | Username, bcrypt-hashed password, account creation timestamp |
| **Data subjects** | Platform users |
| **Recipients** | None (no third-party sharing) |
| **Retention** | Account lifetime + 30 days post-deletion |
| **Transfers** | None |
| **Security** | bcrypt (cost 12), Zero Trust IAM, TLS 1.3 |
| **Source** | `src/auth/`, `workers/users-service/` |

---

## Processing Activity 2: AI Inference / Chat

| Field | Detail |
|---|---|
| **Activity** | Processing user prompts through AI inference pipeline |
| **Purpose** | Provide AI-generated responses to users |
| **Legal basis** | Art. 6(1)(b) — contractual necessity |
| **Data categories** | Prompt text, generated response, model used, latency |
| **Data subjects** | Platform users |
| **Recipients** | HuggingFace (Tier 2 fallback), OpenRouter (Tier 3 fallback) — under SCCs |
| **Retention** | 90 days, user-deletable via GDPR erasure endpoint |
| **Transfers** | Conditional: Tier 2/3 fallback only; Tier 1 (Ollama) is local |
| **Security** | OutputSafetyFilter, TLS 1.3, token budgets |
| **Source** | `src/ai_gateway/`, `src/core/tranc3_inference.py` |

---

## Processing Activity 3: Session Management

| Field | Detail |
|---|---|
| **Activity** | Issuing and validating JWT session tokens |
| **Purpose** | Maintain authenticated sessions |
| **Legal basis** | Art. 6(1)(f) — legitimate interest (platform security) |
| **Data categories** | User ID, session timestamp, token expiry |
| **Data subjects** | Authenticated users |
| **Recipients** | None |
| **Retention** | Token TTL: 24 hours; session logs: 90 days |
| **Transfers** | None |
| **Security** | HS256 JWT, short TTL, HTTPS only |
| **Source** | `src/auth/`, `workers/infinity-auth/` |

---

## Processing Activity 4: Audit Logging (The Observatory)

| Field | Detail |
|---|---|
| **Activity** | Recording all significant platform actions |
| **Purpose** | Security audit trail, compliance, incident investigation |
| **Legal basis** | Art. 6(1)(c) — legal obligation; Art. 6(1)(f) — legitimate interest |
| **Data categories** | User ID (pseudonymous), action type, timestamp, request ID |
| **Data subjects** | Platform users and administrators |
| **Recipients** | None |
| **Retention** | 7 years (legal obligation) |
| **Transfers** | None |
| **Security** | SQLite on encrypted volume, access restricted to admin role |
| **Source** | `src/observability/`, `workers/audit-service/` |

---

## Processing Activity 5: Encrypted Settings Storage

| Field | Detail |
|---|---|
| **Activity** | Storing per-user encrypted preferences and secrets |
| **Purpose** | Persist user configuration securely |
| **Legal basis** | Art. 6(1)(b) — contractual necessity |
| **Data categories** | Encrypted preference key-value pairs |
| **Data subjects** | Platform users |
| **Recipients** | None |
| **Retention** | Account lifetime |
| **Transfers** | None |
| **Security** | AES-GCM encryption at application layer, key from SETTINGS_DB_URL env |
| **Source** | `workers/users-service/`, `src/auth/` |

---

## Data Subject Rights Register

| Request type | Handled by | SLA |
|---|---|---|
| Access request | `GET /user/settings` + manual review | 30 days |
| Erasure request | `DELETE /gdpr/erase/{user_id}` | 72 hours |
| Portability | `GET /user/export` | 30 days |
| Rectification | `PUT /user/settings` | Self-service |

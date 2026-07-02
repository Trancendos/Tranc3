# Service Doc-Pack — Infinity (OAuth2/OIDC + SSO + MFA Auth)

> Code-grounded Doc Pack per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.
> Claims cite `workers/infinity-auth/`.

**Service:** Infinity · **Slug:** `infinity` · **Lead AI:** The Guardian (Anchor: Orb of Orisis) (AID-INF-01, Tier 3) · **Prime:** Cornelius MacIntyre (Tier 2)
**Canonical status:** ✅ Self-hosted → **Live** tier (status per `CLAUDE.md`; identity/PID-INF per `PLATFORM_ENTITIES.md`)
**Code root:** `workers/infinity-auth/` · **Worker:** `infinity-auth` (port 8005) · **Owner:** Platform Engineering
**Version:** 1.0.0 · **Last verified against `main`:** 2026-07-02 @ `70fec6b`

---

## 1. Service Governance Charter (GOV)

- **Mission:** One account, all services — central identity for the platform: user
  registration/login, JWT issuance, OAuth2/OIDC authorization, SSO, and MFA (TOTP).
- **In scope:** account lifecycle (register/login/logout), access + refresh token issuance
  and verification, OAuth2 authorization-code + token endpoints, OIDC discovery + JWKS,
  TOTP MFA (setup/enable/disable + backup codes), role/tier management, per-caller rate limiting.
- **Out of scope:** secrets/vault storage (The Void), tool registry (The Spark), workflow
  execution (The Digital Grid), payment identity (Royal Bank of Arcadia).
- **Lead AI (Tier 3):** The Guardian (Anchor: Orb of Orisis); **Prime (Tier 2):** Cornelius MacIntyre.
- **SLOs (target):** availability 99.9% (auth is on the critical path), p99 token verify
  < 50 ms, error budget 0.1%/30d.
- **Review cadence:** Quarterly, or on any change to the token/OIDC surface or crypto.
- **Hard dependencies:** its own SQLite auth DB; no external paid IdP (zero-cost).

## 2. Detailed Design Document (DDD)

- **Component breakdown:**

  | Module | Responsibility |
  |--------|----------------|
  | `workers/infinity-auth/router.py` | FastAPI routes (auth, MFA, OAuth2/OIDC) |
  | `workers/infinity-auth/service.py` | Token mint/verify (`create_access_token`, `create_refresh_token`, `decode_access_token`), TOTP (`generate_totp_secret`, `generate_totp_provisioning_uri`), backup codes, role/tier mapping |
  | `workers/infinity-auth/database.py` | `AuthDatabase` — user + token persistence (SQLite) |
  | `workers/infinity-auth/models.py` | Pydantic models: `UserRegister`, `UserLogin`, `TokenResponse`, `RefreshRequest`, `TOTPSetupResponse`, `UserProfile`, … |
  | `workers/infinity-auth/main.py` / `worker.py` | App wiring, lifespan, `RateLimiter`, CORS |
  | `workers/infinity-auth/config.py` | Config (keys, origins) |

- **Public interface (routes, `router.py`):**

  | Method | Route | Purpose |
  |--------|-------|---------|
  | GET | `/health` | Liveness/readiness |
  | POST | `/auth/register` | Create account (Argon2 password hash) |
  | POST | `/auth/login` | Authenticate → access + refresh tokens |
  | POST | `/auth/refresh` | Rotate refresh → new access token |
  | POST | `/auth/logout` | Revoke session |
  | GET | `/auth/me` | Current user profile |
  | POST | `/auth/mfa/setup` \| `/enable` \| `/disable` | TOTP MFA lifecycle |
  | GET | `/auth/verify` | Token verification (for other services) |
  | PUT | `/auth/users/{user_id}/role` | Role management |
  | GET | `/.well-known/openid-configuration` | OIDC discovery |
  | GET | `/.well-known/jwks.json` | JWKS (public keys) |
  | GET | `/auth/authorize` | OAuth2 authorization-code endpoint |
  | POST | `/auth/token` | OAuth2 token endpoint |

- **Data model:** users (id, email, Argon2 hash, role/tier, MFA secret/enabled, backup
  codes hashed); refresh tokens; via `AuthDatabase` on SQLite.
- **Key sequence flows:**
  ```text
  Login:  POST /auth/login → verify Argon2 hash → (if MFA) require TOTP
        → create_access_token + create_refresh_token → TokenResponse
  Verify: other service → GET /auth/verify (Bearer) → decode_access_token → claims
  OIDC:   client → GET /auth/authorize → code → POST /auth/token → tokens;
          public keys via /.well-known/jwks.json
  ```
- **Error handling:** auth failures return standard 401/403; platform canonical codes via
  `src/errors/error_catalog.py`; rate-limit rejections via `RateLimiter`.
- **Concurrency / state:** async FastAPI; token signing keys from config; rate-limit state
  in-memory (token-bucket per caller).

## 3. Technical Architecture Solutions Design (TASD)

- **Context:** the platform's single sign-on / identity authority; replaces the CF
  `infinity-auth-api` worker with a self-hosted FastAPI service (per `CLAUDE.md`).
- **Architecture decisions:**

  | ID | Decision | Options | Why | Consequence |
  |----|----------|---------|-----|-------------|
  | AD-1 | Argon2 password hashing | bcrypt, PBKDF2, Argon2 | modern memory-hard KDF; OWASP-preferred | argon2 dependency (bcrypt retained as fallback) |
  | AD-2 | Self-issued OAuth2/OIDC (authorize + token + JWKS) | external IdP (Auth0/Okta) | zero-cost, full control, no vendor lock-in | must maintain OIDC surface + key rotation |
  | AD-3 | TOTP MFA + hashed backup codes | SMS OTP, WebAuthn | zero-cost, offline, no SMS gateway | TOTP-only (WebAuthn future) |
  | AD-4 | SQLite per-worker + in-memory rate limit | shared DB, Redis KV | zero-cost, no shared state (per platform principle) | single-writer DB; scale via read paths |

- **Non-functional drivers:** security (critical path), zero-cost, availability, OIDC interop.
- **Rejected alternatives:** external IdP (cost/lock-in), SMS MFA (gateway cost), shared
  session store (violates per-worker SQLite principle).

## 4. RACI Matrix

| Activity | Platform Owner | The Guardian (Lead AI) | Platform Eng | The Town Hall | SRE/On-call |
|----------|:--:|:--:|:--:|:--:|:--:|
| Token/OIDC surface change | **A** | C | R | C | I |
| Crypto/key rotation | **A** | C | R | C | C |
| Deploy | A | I | R | I | C |
| Incident (auth outage) | I | I | C | I | **R/A** |
| Access-policy change | **A** | C | R | C | I |
| Doc verification | I | I | R | **A** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream (callers):** every platform service that authenticates a user or verifies a
  token (`GET /auth/verify`); OAuth2/OIDC clients via `/auth/authorize` + `/auth/token`.
- **Downstream:** its own SQLite auth DB. No outbound calls to paid IdPs.
- **Tokens issued:** signed JWT access tokens (verifiable via `/.well-known/jwks.json`) +
  rotating refresh tokens.
- **Auth boundary:** Infinity *is* the auth boundary for the platform; it mints and verifies
  the tokens other services (e.g. The Spark, The Digital Grid) depend on.
- **Data classification:** stores PII (email) + credential material (Argon2 hashes, MFA
  secrets, hashed backup codes) — highest-sensitivity; never logged.

## 6. Architecture Scalability Document (ASD)

- **Load model:** token *verification* dominates (every authenticated request platform-wide);
  login/registration are lower-rate.
- **Scaling levers:** stateless token verification scales horizontally; cache JWKS at callers;
  keep the SQLite writer single and scale verification replicas.
- **Bottlenecks:** SQLite write contention on registration/refresh; Argon2 CPU cost (intentional).
- **Zero-cost limits & hard stops:** no paid IdP dependency. Rate limiting via in-memory
  token-bucket (`RateLimiter`) enforces per-caller ceilings and fails closed on abuse.
- **Degradation:** if the DB is read-only/unavailable, already-issued tokens still verify
  (stateless JWT); new logins/refresh degrade until the DB recovers.

## 7. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | Python | 3.11+ | PSF | ✅ | see `docs/SECURITY-ASSESSMENT.md` |
| Framework | FastAPI + Starlette | pinned | MIT/BSD | ✅ | clean |
| Password KDF | argon2-cffi (bcrypt fallback) | pinned | MIT/Apache | ✅ | clean |
| Tokens | JWT (JOSE) | pinned | MIT | ✅ | clean |
| MFA | TOTP (pyotp-style) | pinned | MIT | ✅ | clean |
| Storage | SQLite | stdlib | Public domain | ✅ | — |

## 8. Policy (POL)

- **Applicable platform policies:** `POL-PRI-001` (privacy), `POL-OPS-002`,
  Zero Trust IAM (`src/auth/zero_trust.py`) — see `docs/policies/`.
- **Service-specific rules:** passwords hashed with Argon2 (never stored/logged in plain);
  MFA secrets and backup codes stored hashed; refresh tokens rotate on use.
- **Data handling:** GDPR — email is PII; account deletion + DSR per `PROC-DSR-001`.
- **Access:** role/tier managed via `PUT /auth/users/{user_id}/role`; tier→limits per `src/monetisation/`.

## 9. Procedure (PROC)

- **Deploy:** `infinity-auth` worker (port 8005), Dockerfile in `workers/infinity-auth/`; CI via `.forgejo/workflows/`.
- **Key rotation:** rotate signing keys in config; publish new key in JWKS before retiring old (overlap window).
- **Enable MFA (user):** `POST /auth/mfa/setup` → scan provisioning URI → `POST /auth/mfa/enable`.
- **Role change:** `PUT /auth/users/{user_id}/role` (admin/authorized only); audited to The Observatory.
- **Config/secret change:** via change gate (`docs/procedures/PROC-CHG-001-Change-Request.md`); secrets from The Void.

## 10. Runbook (RUN)

- **Health check:** `GET /health` → 200.
- **Key alerts → action:**

  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | Auth 5xx spike | DB unavailable / key misconfig | check DB + signing key; confirm JWKS serves | **SRE → Platform Eng (P1)** |
  | Login failures surge | credential stuffing / brute force | confirm `RateLimiter` engaging; block offending callers | SRE → Security |
  | Token verify failures platform-wide | key rotation gap | ensure old key still in JWKS; roll back rotation | Platform Eng |
  | MFA lockouts | clock skew / lost device | backup-code path; admin reset | Support → Platform Eng |

- **Diagnostics:** structured JSON logs (no secrets/tokens), `trace_id`; metrics `/metrics`; audit to The Observatory.
- **Rollback:** redeploy previous image; keep JWKS backward-compatible so issued tokens stay valid.
- **Recovery:** restore SQLite from backup; already-issued JWTs remain verifiable (stateless).

## 11. Standards (STD)

- **API standard:** OAuth2 (RFC 6749) authorization-code + token; OIDC discovery + JWKS.
- **Crypto standard:** Argon2 password hashing; signed JWT; TOTP (RFC 6238) MFA.
- **Error standard:** canonical `ErrorCode` enum — `src/errors/error_catalog.py`; standard 401/403.
- **Logging standard:** structured JSON, `trace_id`, **never** log secrets/tokens/hashes.
- **Test standard:** `workers/infinity-auth/tests/` (`test_router.py`, `test_service.py`).
- **Naming standard:** "The Guardian (Anchor: Orb of Orisis)" full title in entity contexts (per `CLAUDE.md`).

---

## Verification Log

| Date | Verifier | Commit | Result |
|------|----------|--------|--------|
| 2026-07-02 | Platform Engineering | `70fec6b` | Routes (auth/MFA/OAuth2/OIDC/JWKS), Argon2 hashing, TOTP MFA, RateLimiter, and AuthDatabase verified against `workers/infinity-auth/`. Lead AI/Prime per PLATFORM_ENTITIES.md PID-INF. |

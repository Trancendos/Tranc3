# Service Doc-Pack Template — `<Service Name>`

> **How to use.** Copy this file into `docs/services/<service-slug>/README.md` (or split
> each `##` section into its own file). Replace every `<…>` placeholder. Delete guidance
> blockquotes. **Every factual claim must cite a real file/route/config** — if you cannot
> cite it, mark it `PLANNED`, do not assert it. Governed by
> `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.

**Service:** `<Service Name>` · **Slug:** `<service-slug>` · **Lead AI:** `<Tier-3 name>`
**Canonical status:** `<✅ In repo | 🔧 Partial | 🔧 Planned>` (must match the `CLAUDE.md` service table)
**Code root:** `<path>` · **Port:** `<port>` · **Owner:** Platform Engineering
**Version:** 0.1.0 · **Last verified against `main`:** `<YYYY-MM-DD @ commit>`

---

## 1. Service Governance Charter (GOV)

- **Mission:** `<one sentence — what this service is for>`
- **In scope:** `<bullets>`
- **Out of scope:** `<bullets — prevents scope creep>`
- **Lead AI (Tier 3):** `<name>` — role per `PLATFORM_ENTITIES.md`
- **SLOs:** availability `<%>`, p99 latency `<ms>`, error budget `<%>`
- **Review cadence:** `<Quarterly / on-change>`
- **Dependencies (hard):** `<services this cannot run without>`

## 2. Detailed Design Document (DDD)

> Only for ✅ / 🔧-Partial. Cite code.

- **Component breakdown:** `<module → responsibility, with file paths>`
- **Public interface:** `<routes / RPC methods / events, each with a code cite>`
- **Data model:** `<tables / schemas / in-memory structures>`
- **Key sequence flows:** `<request → … → response, e.g. mermaid>`
- **Error handling:** `<error types, canonical codes, failure modes>`
- **Concurrency / state:** `<async model, shared state, locks, queues>`

## 3. Technical Architecture Solutions Design (TASD)

- **Context:** `<where this sits in the platform>`
- **Architecture decisions (ADRs):**

  | ID | Decision | Options considered | Why | Consequence |
  |----|----------|--------------------|-----|-------------|
  | AD-1 | `<decision>` | `<A / B / C>` | `<rationale>` | `<trade-off accepted>` |

- **Non-functional drivers:** `<security, cost, latency, portability>`
- **Rejected alternatives:** `<what we did NOT do and why>`

## 4. RACI Matrix

| Activity | Platform Owner | Lead AI | Platform Eng | Town Hall | SRE / On-call |
|----------|:--:|:--:|:--:|:--:|:--:|
| Design change | A | C | R | C | I |
| Deploy | A | I | R | I | C |
| Incident response | I | I | C | I | **R/A** |
| Access grant | **A** | I | R | C | I |
| Doc verification | I | I | R | **A** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream (calls in):** `<callers, auth method, contract>`
- **Downstream (calls out):** `<targets, auth, failure handling, circuit breaker>`
- **Events published / consumed:** `<topic → schema>`
- **Auth boundary:** `<JWT / API key / mTLS — cite middleware>`
- **Data classification crossing the boundary:** `<PII? secrets? — controls>`

## 6. Architecture Scalability Document (ASD)

- **Load model:** `<expected RPS, concurrency, data volume>`
- **Scaling levers:** `<horizontal workers / cache / queue depth>`
- **Bottlenecks:** `<known limits>`
- **Zero-cost limits & hard stops:** `<free-tier ceilings, quota monitor, rotation to
  x6–x8 alternates, threshold at which the service sheds load / fails safe>`
- **Degradation strategy:** `<what still works when a dependency is down>`

## 7. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | `<Python 3.11 / Rust / Node>` | `<ver>` | `<lic>` | ✅ | `<clean / see SECURITY-ASSESSMENT>` |
| Framework | `<FastAPI / …>` | | | | |
| Storage | `<SQLite / IPFS / …>` | | | | |
| Transport | `<HTTP+SSE / WS / JSON-RPC>` | | | | |

## 8. Policy (POL)

> Reference platform policies; record only service-specific deltas.

- **Applicable platform policies:** `<POL-AI-001, POL-OPS-002, … with links>`
- **Service-specific rules:** `<deltas>`
- **Data handling:** `<retention, PII, GDPR basis>`
- **Access policy:** `<who, tiers, MFA requirement>`

## 9. Procedure (PROC)

- **Deploy:** `<steps / command / CI workflow>`
- **Configuration change:** `<steps + approval gate>`
- **Secret rotation:** `<steps — cite The Void / Vault>`
- **Onboarding a consumer:** `<steps>`

## 10. Runbook (RUN)

> Only for ✅ live services.

- **Health check:** `<endpoint + expected response>`
- **Key alerts → action:**

  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | `<alert>` | `<cause>` | `<action>` | `<who>` |

- **Diagnostics:** `<logs, metrics, traces — where>`
- **Rollback:** `<how to revert safely>`
- **Recovery from data loss:** `<backup restore steps>`

## 11. Standards (STD)

- **Applicable platform standards:** `<docs/defstan/… links>`
- **API standard:** `<JSON-RPC 2.0 / REST conventions>`
- **Logging standard:** `<structured JSON, trace_id, no secrets>`
- **Error standard:** `<canonical ErrorCode enum — src/errors/error_catalog.py>`
- **Test standard:** `<coverage target, required suites>`

---

## Verification Log

| Date | Verifier | Commit | Result |
|------|----------|--------|--------|
| `<date>` | `<name>` | `<sha>` | `<all claims code-backed / gaps: …>` |

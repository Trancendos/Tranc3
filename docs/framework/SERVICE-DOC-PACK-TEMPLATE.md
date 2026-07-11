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

## 7. Deployment Scope Matrix (DSM)

> The platform recognizes exactly three deployment scopes, defined in code by
> `src/platform/infrastructure_mode.py` (`PlatformInfraMode.CLOUD_ONLY` / `.HYBRID` /
> `.LOCAL_ONLY`, selected via `PLATFORM_INFRA_MODE`, legacy alias `SYSTEM_MODE`) and
> illustrated platform-wide in `docs/architecture/infrastructure-modes.md`. State facts, not
> aspiration — if the service doesn't branch on the mode itself, say so plainly rather than
> implying it does.

- **Mode awareness:** `<does this service's own code call PlatformInfraMode / branch on the
  mode directly? YES/NO — cite the grep/import. Most entities are NO: the mode is an
  externally-applied deployment-topology choice (which compose block runs, and where), not
  in-process branching.>`
- **Code root → runtime placement:** `<src/<x>/ mounted in api.py → runs wherever the
  tranc3-backend monolith runs; OR workers/<x>/ → standalone docker-compose service block with
  its own port>`
- **Persistence:** `<SQLite file / named volume / in-memory-only — cite the compose volume
  entry if one exists, or state plainly that none is configured>`

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | `<same docker-compose.production.yml block, deployed to a cloud host (e.g. Fly.io / Oracle Free Tier); Traefik/edge in front>` | `<ephemeral unless a named volume is attached>` | `<e.g. no persistent volume ⇒ state lost on redeploy; any hardware-only dependency (GPU/Ollama/local device) has no cloud equivalent>` |
| **Hybrid** | `<same block, split per docs/architecture/infrastructure-modes.md's Hybrid diagram — persistent data local (TrueNAS/Syncthing), compute/edge in cloud>` | `<local for data, cloud for edge/compute>` | `<requires CITADEL_LOCAL_STACK=true / local Docker reachable from the cloud edge, per should_run_citadel_docker() in infrastructure_mode.py>` |
| **Local-Only** | `<same block, run entirely on local/Citadel hardware behind local Traefik>` | `<fully local, volume-backed>` | `<none beyond standard local-hardware ops, unless noted above>` |

- **Zero-cost posture per mode:** `<cite this pack's own ASD zero-cost limits; note whether
  Cloud-Only relies on the platform's free-tier AI rotation chain (`zero_cost_cloud`) versus
  Hybrid/Local-Only (`zero_cost_full`) per `config/platform/infrastructure_mode.yaml`>`
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`);
  `<state whether this service needs anything beyond a redeploy-target change>`

## 8. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | `<Python 3.11 / Rust / Node>` | `<ver>` | `<lic>` | ✅ | `<clean / see SECURITY-ASSESSMENT>` |
| Framework | `<FastAPI / …>` | | | | |
| Storage | `<SQLite / IPFS / …>` | | | | |
| Transport | `<HTTP+SSE / WS / JSON-RPC>` | | | | |

## 9. Policy (POL)

> Reference platform policies; record only service-specific deltas.

- **Applicable platform policies:** `<POL-AI-001, POL-OPS-002, … with links>`
- **Service-specific rules:** `<deltas>`
- **Data handling:** `<retention, PII, GDPR basis>`
- **Access policy:** `<who, tiers, MFA requirement>`

## 10. Procedure (PROC)

- **Deploy:** `<steps / command / CI workflow>`
- **Configuration change:** `<steps + approval gate>`
- **Secret rotation:** `<steps — cite The Void / Vault>`
- **Onboarding a consumer:** `<steps>`

## 11. Runbook (RUN)

> Only for ✅ live services.

- **Health check:** `<endpoint + expected response>`
- **Key alerts → action:**

  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | `<alert>` | `<cause>` | `<action>` | `<who>` |

- **Diagnostics:** `<logs, metrics, traces — where>`
- **Rollback:** `<how to revert safely>`
- **Recovery from data loss:** `<backup restore steps>`

## 12. Standards (STD)

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

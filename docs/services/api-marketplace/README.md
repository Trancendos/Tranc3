# Service Doc-Pack — API Marketplace

| Field | Value |
|---|---|
| **Entity** | API Marketplace |
| **Lead AI** | Solarscene |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/apimarket/marketplace.py`, `src/apimarket/routes.py`; router registered in `api.py` (`app.include_router(_apimarket_router)`, line 878) |

> **Truthfulness:** claims cite `src/apimarket/marketplace.py` and `src/apimarket/routes.py`
> directly. Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> This pack **supersedes** the prior Planned-tier placeholder, which asserted "no `api_marketplace`
> implementation exists" — that was wrong; a Gemini Code Assist review on PR #201 caught that
> `_apimarket_router` is mounted live in `api.py`, and `CLAUDE.md`'s status was corrected to
> `✅ In repo` at that time. This is the first full code-grounded rewrite of this pack.
> **The module's own mission statement overclaims what's implemented.** The header lists five
> capabilities: "register, discover, **call** external APIs"; OAuth 2.0 **credential management**;
> **webhook subscription management**; **rate limiting** and usage tracking; and MCP-tool
> auto-generation integration with The Spark. Of these, only **register** and **discover** are
> real. There is **no method anywhere in `marketplace.py` that actually calls a registered
> connector's `base_url`** — this is a connector *metadata registry* only, not an API gateway or
> proxy, despite "call external APIs" being in its own mission bullet. No OAuth credential storage
> exists (`AuthType` is recorded as metadata only — no token/secret field, no OAuth flow code).
> No webhook subscription model exists at all (confusingly, "webhook subscription management" is
> claimed but this entity has no webhook-related dataclass or route — contrast with DevOcity,
> which does have a real `WebhookEndpoint`). No rate limiting is enforced — `rate_limit_per_min`
> is stored but never checked against `call_count`. `record_call()` (which would increment
> `call_count`/`error_count`) exists but is **never called from anywhere**, including its own
> `routes.py` — both counters are permanently zero. No MCP-tool auto-generation exists — no code
> in `src/mcp/` references this module.

## 1. Service Governance Charter (GOV)

- **Mission (as coded, not as claimed):** a connector metadata registry — name, base URL, claimed
  auth type, tags, and a manually-added endpoint list per connector. Genuinely useful as a
  discoverable catalogue; not an API gateway, proxy, credential vault, or rate limiter despite its
  own header describing all four.
- **Owner (RACI-A):** Platform Owner Trancendos.
- **Lead AI:** Solarscene.
- **Scope:** `src/apimarket/*` — registry CRUD only.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/apimarket/routes.py`, prefix `/apimarket`)

| Method | Route | Backing |
|---|---|---|
| GET | `/apimarket/status` | `APIMarketplace.stats()` — total/active connector counts, total (always-zero) call count |
| GET | `/apimarket/connectors` | `list_connectors()` — optional `tag`/`status` filters |
| GET | `/apimarket/connectors/{id}` | `get_connector()`, falling back to `find_by_slug()` if not a UUID hit — 404 if neither matches |
| POST | `/apimarket/connectors` | `register()` — body `{"name", "slug", "base_url", "auth_type", "description", "tags", "rate_limit_per_min"}`; 400 if required fields missing or `auth_type` invalid |
| POST | `/apimarket/connectors/{id}/endpoints` | `add_endpoint()` — records a method/path/description triple; 404 if connector missing |

### Data model (`marketplace.py`)
- `APIConnector`: `auth_type` (`AuthType` enum: none/api_key/bearer/oauth2/basic) is **metadata
  only** — no field stores an actual credential, token, or OAuth client config anywhere in this
  dataclass or module.
- `ConnectorEndpoint`: method/path/description — a static catalogue entry, not a callable route;
  nothing in this module builds an outbound HTTP request from it.
- Seeded on startup with 5 internal platform connectors (The Spark, The Digital Grid, The
  Observatory, The Void, Infinity Auth) — these are catalogue entries pointing at real platform
  URLs, but registering them here doesn't make them callable through this module either.

### What's genuinely missing vs. the module's own claims
See truthfulness header for the full list: no outbound call execution, no credential storage, no
webhook model, no rate-limit enforcement, no MCP-tool generation, and `record_call()` is dead
code with zero callers.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_marketplace()`); in-memory
  `_connectors` dict, no persistence, no external DB.
- **Decision: registry-first, gateway-deferred.** The module header itself says "Production
  delegates to Gravitee.io API Management for full lifecycle management, policies, analytics, and
  developer portal" — an honest acknowledgment that Gravitee (not this module) would be
  responsible for the call-execution/credential/rate-limit/analytics functionality. That framing
  is consistent with what's actually implemented; the inconsistency is only in the mission-bullet
  list at the very top of the file overselling what "this scaffold" itself does versus what
  Gravitee would add.
- **Not fixed:** none of the missing capabilities were implemented in this pass — each (outbound
  call proxy, OAuth credential vault, webhook delivery, rate limiting) is a substantial feature
  requiring real infrastructure (e.g. a secrets store for credentials — likely The Void), not a
  docs-pass-scale fix.

## 4. RACI Matrix

| Activity | Solarscene (Lead) | Platform Owner | The Void (future credentials) | Platform Engineering |
|---|---|---|---|---|
| Connector registry CRUD changes | **R** | A | I | C |
| Implementing real outbound call execution (future) | C | **A** | I | **R** |
| Implementing OAuth credential storage (future) | C | **A** | **R** | C |
| Gravitee.io integration (future, per module's own stated production plan) | C | **A** | I | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/apimarket/*` routes — no auth on any route, including registering
  arbitrary connectors pointed at arbitrary URLs (no SSRF-relevant risk today since nothing
  actually calls out to a registered `base_url`, but would become one if call-execution is added
  without an allowlist).
- **Downstream:** best-effort Observatory `observe()` on connector registration only.
- **Not integrated:** Gravitee.io (per the module's own stated production plan), The Spark
  (claimed MCP-tool auto-generation), any credential vault, any webhook delivery mechanism.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory dict, no cap defined — unbounded connector/endpoint growth.
- **Bottleneck:** single-process, no persistence; a restart loses all registered connectors
  except the 5 hard-coded seed entries.
- **Zero-cost limits:** no external dependency in `src/apimarket/*` today; Gravitee.io (when/if
  integrated) is self-hosted OSS per `CLAUDE.md`'s foundations table.
- **Degradation:** Observatory emission failure doesn't block registration.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** mounted in the `tranc3-backend` monolith (`api.py`); runs wherever that monolith's `docker-compose.production.yml` service block is deployed, on whatever port/host the monolith uses (compose service `tranc3-backend`)
- **Persistence:** None — this entity's own state is an in-memory `dict` (`_marketplace`'s connector/endpoint registry per this pack's own TFM/ASD), with no persistence of its own. While the `tranc3-backend` monolith has a named volume, that volume backs *other* entities' state, not this one; this service's own state (if any) is lost on restart/redeploy in every mode alike.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `tranc3-backend` compose block runs on a single cloud host (e.g. Fly.io / Oracle Free Tier); Traefik/edge in front | ephemeral — this service holds no state of its own; the monolith's volume does not apply to it | no entity-specific blocker beyond whatever applies to the monolith as a whole |
| **Hybrid** | same monolith block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, persistent data can sync to local TrueNAS while the monolith itself still runs wherever it's deployed | ephemeral, same as Cloud-Only — this service's own state does not benefit from the Hybrid data-locality split | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one, per `should_run_citadel_docker()` in `infrastructure_mode.py` |
| **Local-Only** | same monolith block, run entirely on local/Citadel hardware behind local Traefik | still ephemeral — local hardware does not change this service's own statelessness | none beyond standard local-hardware ops (backup, power, network) |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Call execution / credentials / webhooks / rate limiting | **not implemented** | N/A — deferred to a future Gravitee.io integration per the module's own stated plan |

## 9. Policy (POL)

- No route-level auth on any `/apimarket/*` route.
- Zero-cost mandate: no external dependency currently in this module to audit; any future
  Gravitee.io integration must pass `scripts/zero_cost_audit.py` per The Citadel's deploy gate.

## 10. Procedure (PROC)

- **Register a connector:** `POST /apimarket/connectors` with `{"name", "slug", "base_url"}` —
  creates a catalogue entry only; does not make the connector callable through this module.
- **List connectors:** `GET /apimarket/connectors?tag=mcp` (optional filters).
- **Attempt to call a registered API:** not supported by this module — the caller must construct
  and send the HTTP request themselves using the catalogue's `base_url`/endpoint metadata.

## 11. Runbook (RUN)

- **`call_count`/`error_count` are always zero:** expected — `record_call()` exists but has no
  caller anywhere in the codebase; this is not a bug to chase, it's dead code.
- **Registering a connector doesn't let me actually invoke its API through the platform:**
  expected — this module is a catalogue, not a gateway or proxy, despite what its own mission
  comment implies.
- **No OAuth token is stored for an `oauth2`-type connector:** expected — `AuthType` is metadata
  only; no credential storage exists in this module.

## 12. Standards (STD)

- Naming: canonical entity name "API Marketplace" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- A module's own header/docstring mission bullets MUST be kept in sync with what the code actually
  does — the gap between this module's claimed 5 capabilities and its 2 implemented ones is the
  reason for this standard, matching the same pattern already established for The Library
  (RAG/Outline claims), The Lab (AI-generation claims), Tranquility (Resonate/tAimra claims), and
  VRAR3D (Tranquility/Resonate claims) earlier in this doc-pack series.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/apimarket/marketplace.py` (265 lines), `src/apimarket/routes.py` (85 lines), `api.py` router registration (line 878) | Confirmed Live-tier, full pack authored — supersedes the prior stale Planned-tier "no code exists" placeholder (corrected to `✅ In repo` during PR #201's Gemini Code Assist review, but never given a full rewrite until now). Major finding: of the module's own 5 claimed capabilities (call external APIs, OAuth credential management, webhook subscriptions, rate limiting, MCP-tool auto-generation), only connector registration and discovery are actually implemented — the other 3, plus `record_call()`, are entirely absent or dead code. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | GOV §1 vs. RACI §4 | Fixed an internal contradiction: GOV prose named both Solarscene and Platform Owner Trancendos as "RACI-A" (ambiguous — RACI defines exactly one Accountable party), while the RACI table below correctly assigned "A" only to Platform Owner. Reworded GOV to separate "Owner (RACI-A): Platform Owner Trancendos" from "Lead AI: Solarscene", matching the table. |

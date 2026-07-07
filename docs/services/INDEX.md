# Service Doc-Pack Coverage Index

Tracks per-service design/architecture/governance documentation across all Trancendos
named entities. Governed by `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.
Artifact legend: **GOV** Charter · **DDD** · **TASD** · **RACI** · **SIM** · **ASD** ·
**TFM** · **POL** · **PROC** · **RUN** · **STD**.

**Required-by-status rule (honesty gate).** The `Status` column below shows the canonical
`CLAUDE.md`-service-table label verbatim; the framework normalizes each to a **gate tier**
(see `DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1) that sets the required pack:
- **Live** (any `✅` label) → full 11-artifact pack, code-grounded.
- **Partial** (`🔧` labels except `🔧 Planned`) → GOV, RACI, TFM, POL, STD + DDD/TASD/SIM/ASD scoped to what exists.
- **Planned** (`🔧 Planned`) → GOV, RACI, TFM, POL, STD **only** (intent-level; no fabricated DDD/RUN).

Status column mirrors the `CLAUDE.md` service table (status source); Lead AI/identity
mirrors `PLATFORM_ENTITIES.md` — update together.

| Service | Status | Lead AI | Pack | Notes |
|---------|--------|---------|------|-------|
| **The Spark** | ✅ In repo | Imfy (Prime: Norman Hawkins) | ✅ **Complete** (reference) | `docs/services/the-spark/` |
| **The Digital Grid** | ✅ In repo | Tyler Towncroft (Prime: The Doctor) | ✅ **Complete** | `docs/services/the-digital-grid/` |
| **Infinity** | ✅ Self-hosted | The Guardian (Anchor: Orb of Orisis) (Prime: Cornelius MacIntyre) | ✅ **Complete** | `docs/services/infinity/` |
| **The Nexus** | 🔧 Self-hosted | Nexus-Prime (Prime: Cornelius MacIntyre) | ✅ **Complete** | `docs/services/the-nexus/` |
| **The Observatory** | ✅ Self-hosted | Norman Hawkins (Prime: Cornelius MacIntyre) | ✅ **Complete** | `docs/services/the-observatory/` |
| **The Workshop** | ✅ In repo | Larry Lowhammer (Prime: The Doctor) | ✅ **Complete** | `docs/services/the-workshop/` |
| **The Town Hall** | ✅ Integrated | Tristuran (Prime: Cornelius MacIntyre) | ✅ **Complete** | `docs/services/the-town-hall/` |
| **The Lighthouse** | ✅ Deployed | Rocking Ricki | ✅ **Complete** (charter-only) | `docs/services/the-lighthouse/` |
| **The HIVE** | ✅ Deployed | The Queen | ✅ **Complete** (charter-only) | `docs/services/the-hive/` |
| **Royal Bank of Arcadia** | ✅ Deployed | Dorris Fontaine | ✅ **Complete** (charter-only) | `docs/services/royal-bank-of-arcadia/` |
| **Arcadian Exchange** | ✅ Deployed | The Porter Family | ✅ **Complete** (charter-only) | `docs/services/arcadian-exchange/` |
| **The Citadel** | ✅ Self-hosted | Trancendos | ✅ **Complete** | `docs/services/the-citadel/` |
| **The Void** | 🔧 Migrating | Prometheus (Prime: The Guardian) | ✅ **Complete** | `docs/services/the-void/` [^void-port] |
| **Luminous** | 🔧 Partial | Cornelius MacIntyre | ✅ **Complete** | `docs/services/luminous/` |
| **Turing's Hub** | 🔧 Partial | Samantha Turing | ✅ **Complete** | `docs/services/turings-hub/` |
| **Arcadia** | 🔧 Partial | Lilli SC (Prime: Dorris Fontaine) | ✅ **Complete** | `docs/services/arcadia/` |
| **The Chaos Party** | 🔧 Partial | The Mad Hatter (Prime: The Doctor) | ✅ **Complete** | `docs/services/the-chaos-party/` |
| **The Library** | ✅ In repo | Zimik | ✅ **Complete** | `docs/services/the-library/` |
| **The Academy** | ✅ In repo | Shimshi | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-academy/` |
| **DocUtari** | ✅ In repo | To be Defined | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/docutari/` |
| **The Basement** | ✅ In repo | Gary Glowman (Glow-Worm) | ✅ **Complete** | `docs/services/the-basement/` |
| **The Studio** | ✅ In repo | Voxx | ✅ **Complete** | `docs/services/the-studio/` |
| **Sashas Photo Studio** | ✅ In repo | Madam Krystal | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/sashas-photo-studio/` |
| **TranceFlow** | ✅ In repo | Junior Cesar | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/tranceflow/` |
| **TateKing** | ✅ In repo | Benji Tate & Sam King | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/tateking/` |
| **Fabulousa** | ✅ In repo | Baron Von Hilton | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/fabulousa/` |
| **Imaginarium** | ✅ In repo | Voxx | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/imaginarium/` |
| **The Lab** | ✅ In repo | The Dr. & Slime | ✅ **Complete** | `docs/services/the-lab/` |
| **The Artifactory** | ✅ In repo | Lunascene | ✅ **Complete** | `docs/services/the-artifactory/` |
| **API Marketplace** | ✅ In repo | Solarscene | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/api-marketplace/` |
| **Cryptex** | ✅ In repo | Renik | ✅ **Complete** | `docs/services/cryptex/` |
| **The Ice Box** | ✅ In repo | Neonach | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-ice-box/` |
| **The Warp Tunnel** | ✅ In repo | Rocking Ricki | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-warp-tunnel/` |
| **Warp Radio** | ✅ In repo | Rocking Ricki | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/warp-radio/` |
| **The Dutchy** | ✅ In repo | Predictive lore | ✅ **Complete** | `docs/services/the-dutchy/` |
| **Think Tank** | ✅ In repo | Trancendos | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/think-tank/` |
| **ChronosSphere / ArcStream** | ✅ In repo | Chronos | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/chronosphere-arcstream/` |
| **DevOcity** | ✅ In repo | Kitty | ✅ **Complete** | `docs/services/devocity/` |
| **Tranquility** | ✅ In repo | Savania | ✅ **Complete** | `docs/services/tranquility/` |
| **I-Mind** | ✅ In repo | Elouise | ✅ **Complete** | `docs/services/i-mind/` |
| **tAimra** | ✅ In repo | tAImra | ✅ **Complete** | `docs/services/taimra/` |
| **VRAR3D** | ✅ In repo | Entari | ✅ **Complete** | `docs/services/vrar3d/` |
| **Resonate** | ✅ In repo | Magdalena | ✅ **Complete** | `docs/services/resonate/` |

**Coverage:** **20 / 37 required full Live-tier packs** complete (full 11-artifact, code-grounded:
The Spark, The Digital Grid, Infinity, The Observatory, The Workshop, The Town Hall, The Citadel,
**The Basement, The Studio, I-Mind, The Library, The Lab, The Artifactory, Cryptex, The Dutchy,
DevOcity, Tranquility, tAimra, VRAR3D, Resonate**). The other **17 Live-tier (`✅`) entities are
charter-only, not full-pack-complete** — 4 as a documented §2.1 exception (deployed CF Workers
with no source in this repo) and **13 as an outstanding gap**: Think Tank, API Marketplace
(router-mounted in `api.py`), plus The Academy, Sashas Photo Studio, TranceFlow, TateKing,
Imaginarium, The Warp Tunnel, Warp Radio, DocUtari, Fabulousa, The Ice Box,
ChronosSphere/ArcStream (standalone `workers/*/worker.py` deployed via
`docker-compose.production.yml`, not mounted in `api.py`) — status corrected to `✅ In repo` but
their doc-pack has not yet been upgraded to match. **6 Partial-tier packs** (The Nexus, Luminous,
Turing's Hub, The Void, Arcadia, The Chaos Party). **0 genuinely Planned-tier entities remain** —
all 26 originally-`🔧 Planned` entities have been confirmed to have real, deployable code (a
Gemini Code Assist review on this PR caught the last 5 via non-obvious worker naming: `apimarket`,
`files-service`/`storage-service`, `fabulousa-service`, `ice-box-service`, `cron-service`).
**43 / 43 entities have a doc-pack**, but 17 of those packs do not yet match the tier their status
requires · 13 of the 26 corrected entities (The Basement, The Studio, I-Mind, The Library, The
Lab, The Artifactory, Cryptex, The Dutchy, DevOcity, Tranquility, tAimra, VRAR3D, Resonate) have
now received a real Live-tier rewrite · rollout order per framework §6.

> **Known §2.1 gap (4 entities):** The Lighthouse, The HIVE, Royal Bank of Arcadia, and Arcadian
> Exchange are `✅ Deployed` — **Live tier**, which requires the full 11-artifact code-grounded
> pack per §2.1 — but have no source code in this repo for their Cloudflare Workers to ground
> DDD/TASD/SIM/ASD/PROC/RUN against. Their packs are charter-only (GOV+RACI+TFM+POL+STD) as an
> **explicit, documented exception**, not a valid Planned-tier application — see each pack's
> truthfulness header. This is a real compliance gap against §2.1, tracked here rather than
> hidden, until either their source lands in this repo or the framework defines a
> deployed-no-source tier explicitly.
>
> **Known gap — CLAUDE.md `🔧 Planned` status was stale for all 26 originally-Planned entities;
> all 26 now corrected.** A PR review (cubic) caught that 2 of the "no code exists" charter-only
> packs were factually wrong; a full audit (extended by a later Gemini Code Assist find covering
> the last 5) confirmed real code for all 26. Across all 26, **15 have a router confirmed registered
> live in
> `api.py`** — The Library, The Basement, The Studio, The Lab, The Artifactory, Cryptex, The
> Dutchy (as `section7`), DevOcity, Tranquility, I-Mind, tAimra, VRAR3D, Resonate, Think Tank (as
> `_thinktank_router`), and API Marketplace (as `_apimarket_router` from `src/apimarket/routes` —
> caught by a Gemini Code Assist review on this PR alongside the remaining 4). The other **11** —
> The Warp Tunnel, Warp Radio, The Academy, Sashas Photo Studio, TranceFlow, TateKing, Imaginarium,
> DocUtari (`workers/files-service/`, `workers/storage-service/`), Fabulousa
> (`workers/fabulousa-service/`), The Ice Box (`workers/ice-box-service/`), and
> ChronosSphere/ArcStream (`workers/cron-service/`) — are **not** mounted in `api.py`, but each has
> a real, standalone `workers/<name-or-mapped-service>/worker.py` with its own Dockerfile **and a
> live service block in `docker-compose.production.yml`** (confirmed by grep for each service key;
> the DocUtari/Fabulousa/Ice-Box/ChronosSphere mappings were missed on the first pass because the
> compose service names — `files-service`, `fabulousa-service`, `ice-box-service`, `cron-service` —
> don't match the entity names). `CLAUDE.md`'s status column has been **corrected to `✅ In repo`**
> for all 26. Their doc-packs below are marked **⚠️ Mis-tiered**: still charter-only
> (GOV+RACI+TFM+POL+STD) even though their corrected Live-tier status now requires the full
> 11-artifact pack — this is the honest **current** gap (a real Partial/Live-tier rewrite with
> code-grounded DDD/TASD is still owed for all 26), not a stale-status problem anymore. **Zero**
> of the originally-Planned entities remain genuinely code-free.
> **Follow-up required:** author real Partial/Live-tier packs (code-grounded DDD/TASD/SIM/ASD/
> PROC/RUN) for all 26 corrected entities — the charter-only packs are a stopgap, not the fix.

## Rollout log

| Date | Change |
|------|--------|
| 2026-07-02 | Framework + template + The Spark reference pack; index established (1/43). |
| 2026-07-02 | Added The Digital Grid pack, code-grounded against `src/workflow/` (2/43). |
| 2026-07-02 | Added Infinity + The Observatory packs, code-grounded against `workers/infinity-auth/` and `src/observability/` (4/11 required full packs). |
| 2026-07-02 | Added Luminous + Turing's Hub packs (Partial-tier), code-grounded against `src/bio_neural/` + `src/core/` and `src/personality/`; review surfaced and repaired real route bugs (phi tensor type, neuromorphic kwarg, `/status` probe, `_matrix` import) and flagged remaining PARTIAL wiring. |
| 2026-07-03 | Added The Nexus pack, code-grounded against `workers/infinity-ws/worker.py` (JWT WebSocket hub, `ConnectionManager`, internal-secret HTTP routes, port 8004). |
| 2026-07-03 | Batch: added The Void, The Town Hall, The Chaos Party, The Workshop, Arcadia packs — code/config-grounded against `workers/infinity-void/worker.py`, `src/townhall/`, `tests/test_chaos.py`, `deploy/forgejo/`, `web/`. CranBania submodule scoped out (not checked out). |
| 2026-07-03 | Follow-up: corrected The Void's port note — the earlier claim ("8082 is the app default and authoritative, `EXPOSE 8002` stale") was wrong. 8002 is the consistently-referenced, intended port (monitoring, `workers/README.md`, wiki, `docs/vault_security.md`); fixed by adding an explicit `PORT=8002` to compose rather than changing the port. See `docs/services/the-void/` verification log. |
| 2026-07-03 | Added The Citadel pack (7th Live-tier full pack), code-grounded against `docker-compose.production.yml` (Traefik/Vault/Prometheus/Grafana/OTel), `deploy/citadel/deploy-production.sh`, and `scripts/citadel_preflight.py`. |
| 2026-07-04 | Batch: added charter-only (GOV+RACI+TFM+POL+STD) packs for all 30 remaining entities with no in-repo code — 26 `🔧 Planned` entities plus 4 `✅ Deployed`-but-source-absent Cloudflare Workers (The Lighthouse, The HIVE, Royal Bank of Arcadia, Arcadian Exchange). No DDD/TASD/SIM/ASD/RUN fabricated for any of them, per framework §2.1. All 43/43 platform entities now carry a doc-pack matching their gate tier. |
| 2026-07-04 | Follow-up: corrected `CLAUDE.md`'s stale `🔧 Planned` status to `✅ In repo` for 13 entities confirmed to have a router registered live in `api.py` (The Library, The Basement, The Studio, The Lab, The Artifactory, Cryptex, The Dutchy, DevOcity, Tranquility, I-Mind, tAimra, VRAR3D, Resonate). Their doc-packs are now marked ⚠️ Mis-tiered pending a real Live-tier rewrite. |
| 2026-07-04 | cubic (PR #200 review) caught that Think Tank was missed — `app.include_router(_thinktank_router)` at `api.py:910` (`src/quantum/routes`) confirms it's also live-wired. Corrected `CLAUDE.md` and this index the same way (now **14** entities corrected, not 13). The remaining **7** "stale-Planned" entities (The Warp Tunnel, Warp Radio, The Academy, Sashas Photo Studio, TranceFlow, TateKing, Imaginarium) have real code but no confirmed `api.py` wiring — left as `🔧 Planned` pending further investigation. |
| 2026-07-04 | Follow-up: investigated the remaining 7 "stale-Planned, unresolved-wiring" entities directly against `docker-compose.production.yml` — confirmed each has its own service block (`tranceflow:`, `imaginarium:`, `tateking:`, `sashas-photo-studio:`, `the-academy:`, `warp-tunnel:`, `warp-radio:`), a real `Dockerfile`, and `workers/<name>/worker.py`, i.e. deployed as standalone services rather than mounted in `api.py`. Corrected `CLAUDE.md`'s status to `✅ In repo` for all 7. Recalculated coverage summary to 7/32 full Live-tier packs, 25 Live-tier charter-only (4 §2.1 exception + 21 outstanding gap), 6 Partial-tier, 5 (claimed, later found wrong — see next entry) genuinely Planned. |
| 2026-07-04 | Gemini Code Assist and cubic (independently, same PR #201 review) caught that the remaining "5 genuinely code-free" claim was wrong: API Marketplace has `_apimarket_router` mounted in `api.py` (`src/apimarket/routes`), and DocUtari, Fabulousa, The Ice Box, and ChronosSphere/ArcStream each have a real standalone worker under a compose service name that doesn't match the entity name (`files-service`+`storage-service`, `fabulousa-service`, `ice-box-service`, `cron-service` respectively — confirmed via `docker-compose.production.yml` and cross-checked against `CLAUDE.md`'s worker-map table). **All 26** originally-`🔧 Planned` entities are now confirmed to have real code and status-corrected to `✅ In repo` — zero genuinely-Planned entities remain among them. Recalculated: 7/37 full Live-tier packs, 30 Live-tier charter-only (4 §2.1 exception + 26 outstanding gap), 6 Partial-tier, 0 genuinely Planned. |
| 2026-07-05 | Started the real Live-tier rewrite for the 26 Mis-tiered entities. First batch: The Basement (`src/basement/archive.py` + `routes.py` — archive/search layer, FAISS-optional, no auth on routes) and The Studio (`src/studio/hub.py` + `routes.py` — job-tracking orchestration shell; code-grounded finding: every sub-service is self-labelled `"planned"`/`"scaffold"` in its own capability manifest and no job ever leaves `queued`, documented explicitly). Both promoted from Mis-tiered to Complete (9/37 full Live-tier packs). 24 entities remain in the outstanding gap. |
| 2026-07-05 | Added I-Mind pack, code-grounded against `src/imind/protocol.py` (169 lines) and `routes.py` (28 lines). While grounding the pack, found and fixed a genuine safety-relevant bug: the self-harm severity-escalation guard compared `SensitivityLevel` string enum values with `<` (`level.value < SensitivityLevel.HIGH.value`), which is lexical string comparison, not severity ordering — since `"none" > "high"` alphabetically, the guard was always false and self-harm detections never escalated past `NONE`. Fixed by removing the faulty guard (the branch only runs when level is still `NONE`). A follow-up Gemini Code Assist review (PR #203) caught a second, deeper defect: the crisis-detection loop scanned all of `_CRISIS_PATTERNS` (including the self-harm patterns), making the self-harm branch unreachable regardless of the first fix — fixed by scoping the crisis check to `_CRISIS_PATTERNS[0]` only, and added `tests/test_imind.py` (previously untested). Also flagged, unfixed: no confirmed caller of `IMind.assess()` from the inference pipeline was found — routable but integration into the real chat flow is unverified. Promoted from Mis-tiered to Complete (10/37 full Live-tier packs). 23 entities remain in the outstanding gap. |
| 2026-07-05 | Added The Library pack, code-grounded against `src/library/knowledge_base.py` (277 lines), `routes.py` (62 lines), `src/observability/library_pipeline.py`, and `workers/library-service/`. Found and fixed a genuine production defect: `workers/library-service/Dockerfile` hardcoded port 8053 (EXPOSE/HEALTHCHECK/CMD) while `docker-compose.production.yml` routed the service to 8067 — since the Dockerfile CMD's `--port` flag overrides the `LIBRARY_PORT` env var, the container was unreachable at its compose-routed port; fixed by aligning the Dockerfile and `config.py`'s default to 8067. Also documented (not fixed, architectural): the Observatory→Library pipeline is dead code (`ingest()` is never called, and its target `/kb/ingest` endpoint doesn't exist on either implementation); the RAG/FAISS and Outline-sync integrations claimed in source comments aren't implemented in `src/library/*`; `Library.update()` has no HTTP route. Promoted from Mis-tiered to Complete (11/37 full Live-tier packs). 22 entities remain in the outstanding gap. |
| 2026-07-05 | Added The Lab pack, code-grounded against `src/lab/code_lab.py` (203 lines), `routes.py` (111 lines), and its two separate standalone workers (`workers/the-lab/`, `workers/lab-service/`). Found and fixed the same class of production defect as The Library's: `workers/lab-service/Dockerfile` hardcoded port 8039 while compose routed to 8066 — fixed by aligning the Dockerfile and `config.py`'s default to 8066. Also documented a significant, code-grounded finding: `src/lab/*` has no AI-generation call anywhere despite its own docstring claiming delegation to Tranc3Engine/Ollama/OpenRouter/Spark MCP — it is a pure session/message/artifact CRUD layer; real code generation (`workers/lab-service/`) and sandboxed execution (`workers/the-lab/`) live in two entirely separate workers that never call into `src/lab/*`. Promoted from Mis-tiered to Complete (12/37 full Live-tier packs). 21 entities remain in the outstanding gap. |
| 2026-07-05 | Added The Artifactory pack, code-grounded against `src/artifactory/registry.py` (256 lines), `routes.py` (100 lines), and `workers/artifactory-service/worker.py`. Found and fixed a genuine build-breaking defect: `workers/artifactory-service/` had **no Dockerfile at all** despite compose referencing one — `docker compose build` would fail outright. Fixed by adding a Dockerfile matching the established single-file-worker convention. Discovered, and explicitly flagged rather than rushed-fixed, the same missing-Dockerfile defect in **8 other** worker directories (`backup-service`, `cranbania`, `fabulousa-service`, `ice-box-service`, `litellm-service`, `queue-service-go`, `rate-limit-service-go`, `the-void`) — a real, previously undocumented platform-wide gap, tracked for a dedicated follow-up pass rather than rushed here (2 are Go services, 1 is a submodule, 1 is CF-worker-ambiguous). Promoted from Mis-tiered to Complete (13/37 full Live-tier packs). 20 entities remain in the outstanding gap. |
| 2026-07-05 | Added Cryptex pack, code-grounded against `src/cryptex/threat_detector.py` (351 lines), `bounty_hunter.py` (413 lines), and `routes.py` (105 lines), plus grep-verified import analysis of the module's other 6 files. Major finding: **~69% of this module's code (6 of 9 files, ~1,940 of 2,806 lines — MISP/Wazuh connectors, CVE scanner, genetic rules, graph anomaly, ML detector) is never imported by any live code path** — real, substantial implementations that simply never run. Also flagged, not fixed: `Cryptex.is_blocked()` is never consulted by any request-handling middleware, so IP/actor "blocking" has zero real enforcement effect; and the unauthenticated `POST /cryptex/bounty/scan` endpoint accepts an arbitrary caller-supplied scan target with no allowlist. Promoted from Mis-tiered to Complete (14/37 full Live-tier packs). 19 entities remain in the outstanding gap. |
| 2026-07-05 | Added The Dutchy pack, code-grounded against `src/research/section7.py` (285 lines), `routes.py` (53 lines), and `bci_interface.py` (132 lines, self-declared unwired stub). Verified genuine cross-entity integration — `generate_platform_health_report()`/`generate_security_report()` make real calls into 5 other live entities (Observatory, Town Hall, Cryptex, Basement, Nexus), and `_store_and_publish()` genuinely writes to The Library (confirmed via `Library.create()` call) — one of the more substantively wired entities audited in this series, not a scaffold. Major finding: a completely separate, unrelated `src/section7/` package (6 files, live-wired CVE/OSV/CISA threat-intel polling loop, started from `api.py`'s startup) shares the "Section 7" name with this entity's actual code path (`src/research/section7.py`) — a genuine, previously undocumented naming collision, flagged for future disambiguation rather than conflated. Promoted from Mis-tiered to Complete (15/37 full Live-tier packs). 18 entities remain in the outstanding gap. |
| 2026-07-05 | Added DevOcity pack, code-grounded against `src/devocity/portal.py` (350 lines) and `routes.py` (103 lines). Verified real, well-practiced API key generation (SHA-256 hashed, one-time plaintext reveal) and genuine Redis persistence (rarer than most entities audited in this series, which are pure in-memory). Major finding: **no code anywhere in the repo validates a DevOcity-issued key against any protected route** — the `SPARK`/`GRID`/`ADMIN`/`FULL` scopes are purely descriptive with zero enforcement effect (confirmed via grep cross-check against `src/security/security_framework.py`'s unrelated key-validation mechanism). Also flagged: unauthenticated account creation with an unverified `user_id` (contradicts the module's own "wired to Infinity SSO" claim), unauthenticated key issuance for any known account ID, and four dead counters (`usage`, `request_count`, `delivery_count`, `failure_count`) declared but never incremented. None code-fixed — each requires an architectural auth decision out of scope for a docs pass. Promoted from Mis-tiered to Complete (16/37 full Live-tier packs). 17 entities remain in the outstanding gap. |
| 2026-07-05 | Added Tranquility pack, code-grounded against `src/tranquility/wellbeing.py` (179 lines) and `routes.py` (71 lines). Verified a genuine, working cross-entity integration: `log_mood()` really calls `IMind.assess()` on low/very-low mood entries. Major finding, documented not fixed: **no auth on any route, most consequentially `GET /tranquility/export/{user_id}` (full mood-history export) and `DELETE /tranquility/data/{user_id}`** — any caller who knows a `user_id` can read or delete another user's wellbeing data, a materially sensitive gap given the module's own "governed by Magna Carta + I-Mind protocols" claim. Also documented: two of the module's four stated capabilities (Resonate empathy routing, tAimra burnout signals) exist only as comments, never implemented. Promoted from Mis-tiered to Complete (17/37 full Live-tier packs). 16 entities remain in the outstanding gap. |
| 2026-07-05 | Added tAimra pack, code-grounded against `src/taimra/digital_twin.py` (165 lines) and `routes.py` (74 lines). Verified the twin lifecycle state machine (OFFLINE→LEARNING→ACTIVE, offline-by-default no-op behavior) is real and correctly implemented. Major finding, documented not fixed: **no auth on any route — including export and delete of another user's digital twin** — and the module's own stated privacy guarantee ("the twin never infers or stores sensitive I-Mind flagged content") has zero enforcement in code, since no I-Mind import or call exists anywhere in this module (unlike Tranquility's genuine I-Mind integration, found in the prior entry in this same batch). Also noted a dead `TwinStatus.PAUSED` enum member never assigned anywhere. Promoted from Mis-tiered to Complete (18/37 full Live-tier packs). 15 entities remain in the outstanding gap. |
| 2026-07-05 | Added VRAR3D pack, code-grounded against `src/vrar3d/wellbeing_centre.py` (237 lines) and `routes.py` (76 lines). Major finding: `CLAUDE.md`'s "standalone 3D/VR immersion" entity description is broader than the actual code, which implements a wellbeing-scene library specifically (meditation/breathing/nature/focus/sleep/crisis-calm) per the module's own filename and header — flagged as a scope mismatch, not silently reconciled. Confirmed the module's claimed Tranquility/Resonate/I-Mind integrations are unimplemented: `recommend_scene()` takes a caller-supplied `sensitivity_level` string rather than calling I-Mind itself, and no code path in the repo currently supplies a real "critical" value. Also found all 6 seed scenes have an unset `aframe_url` — the catalogue currently has no renderable WebXR content wired up. Promoted from Mis-tiered to Complete (19/37 full Live-tier packs). 14 entities remain in the outstanding gap. |
| 2026-07-05 | Added Resonate pack, code-grounded against `src/resonate/empathy.py` (119 lines) and `routes.py` (41 lines). Verified `wrap_response()` is real, correct, deterministic empathy-framing logic. **Most safety-relevant finding across this doc-pack batch:** `escalate_to_human()` returns a user-facing message claiming "A support team member has been notified" when **no notification transport exists anywhere in this repo** — only a best-effort Observatory event and a log line occur. Flagged for prioritized correction rather than merely documented as a routine gap, since a false "you've been helped" claim in a crisis-support context is more serious than the platform's other unenforced-flag findings (The Studio, I-Mind). Also confirmed, matching I-Mind's own pattern: no caller of this module was found in the real inference pipeline. Promoted from Mis-tiered to Complete (20/37 full Live-tier packs). 13 entities remain in the outstanding gap. |

[^void-port]: `PLATFORM_ENTITIES.md` lists The Void's *primary worker* as `config-service` (8024) —
    that is a **different** worker owned by the same entity (`PID-VOI`), not the vault
    (`infinity-void`, port 8002), so it is not an error. See `docs/services/the-void/` for the
    full pack.

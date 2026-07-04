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
| **The Library** | ✅ In repo | Zimik | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-library/` |
| **The Academy** | ✅ In repo | Shimshi | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-academy/` |
| **DocUtari** | 🔧 Planned | To be Defined | ✅ **Complete** (charter-only) | `docs/services/docutari/` |
| **The Basement** | ✅ In repo | Gary Glowman (Glow-Worm) | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-basement/` |
| **The Studio** | ✅ In repo | Voxx | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-studio/` |
| **Sashas Photo Studio** | ✅ In repo | Madam Krystal | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/sashas-photo-studio/` |
| **TranceFlow** | ✅ In repo | Junior Cesar | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/tranceflow/` |
| **TateKing** | ✅ In repo | Benji Tate & Sam King | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/tateking/` |
| **Fabulousa** | 🔧 Planned | Baron Von Hilton | ✅ **Complete** (charter-only) | `docs/services/fabulousa/` |
| **Imaginarium** | ✅ In repo | Voxx | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/imaginarium/` |
| **The Lab** | ✅ In repo | The Dr. & Slime | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-lab/` |
| **The Artifactory** | ✅ In repo | Lunascene | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-artifactory/` |
| **API Marketplace** | 🔧 Planned | Solarscene | ✅ **Complete** (charter-only) | `docs/services/api-marketplace/` |
| **Cryptex** | ✅ In repo | Renik | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/cryptex/` |
| **The Ice Box** | 🔧 Planned | Neonach | ✅ **Complete** (charter-only) | `docs/services/the-ice-box/` |
| **The Warp Tunnel** | ✅ In repo | Rocking Ricki | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-warp-tunnel/` |
| **Warp Radio** | ✅ In repo | Rocking Ricki | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/warp-radio/` |
| **The Dutchy** | ✅ In repo | Predictive lore | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/the-dutchy/` |
| **Think Tank** | ✅ In repo | Trancendos | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/think-tank/` |
| **ChronosSphere / ArcStream** | 🔧 Planned | Chronos | ✅ **Complete** (charter-only) | `docs/services/chronosphere-arcstream/` |
| **DevOcity** | ✅ In repo | Kitty | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/devocity/` |
| **Tranquility** | ✅ In repo | Savania | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/tranquility/` |
| **I-Mind** | ✅ In repo | Elouise | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/i-mind/` |
| **tAimra** | ✅ In repo | tAImra | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/taimra/` |
| **VRAR3D** | ✅ In repo | Entari | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/vrar3d/` |
| **Resonate** | ✅ In repo | Magdalena | ⚠️ **Mis-tiered** (charter-only, needs Live-tier upgrade) | `docs/services/resonate/` |

**Coverage:** **7 / 32 required full Live-tier packs** complete (full 11-artifact, code-grounded:
The Spark, The Digital Grid, Infinity, The Observatory, The Workshop, The Town Hall, The Citadel).
The other **25 Live-tier (`✅`) entities are charter-only, not full-pack-complete** — 4 as a
documented §2.1 exception (deployed CF Workers with no source in this repo) and **21 as an
outstanding gap**: The Library, The Basement, The Studio, The Lab, The Artifactory, Cryptex, The
Dutchy, DevOcity, Tranquility, I-Mind, tAimra, VRAR3D, Resonate, Think Tank (router-mounted in
`api.py`), plus The Academy, Sashas Photo Studio, TranceFlow, TateKing, Imaginarium, The Warp
Tunnel, Warp Radio (standalone `workers/*/worker.py` deployed via `docker-compose.production.yml`,
not mounted in `api.py`) — status corrected to `✅ In repo` but their doc-pack has not yet been
upgraded to match. **6 Partial-tier packs** (The Nexus, Luminous, Turing's Hub, The Void, Arcadia,
The Chaos Party). **5 genuinely Planned-tier / charter-only packs** correctly at their required
tier (DocUtari, Fabulousa, API Marketplace, The Ice Box, ChronosSphere/ArcStream — GOV+RACI+TFM+
POL+STD, intent-level, no fabricated DDD/RUN). **43 / 43 entities have a doc-pack**, but 25 of
those packs do not yet match the tier their (in 21 cases, just-corrected) status requires ·
rollout order per framework §6.

> **Known §2.1 gap (4 entities):** The Lighthouse, The HIVE, Royal Bank of Arcadia, and Arcadian
> Exchange are `✅ Deployed` — **Live tier**, which requires the full 11-artifact code-grounded
> pack per §2.1 — but have no source code in this repo for their Cloudflare Workers to ground
> DDD/TASD/SIM/ASD/PROC/RUN against. Their packs are charter-only (GOV+RACI+TFM+POL+STD) as an
> **explicit, documented exception**, not a valid Planned-tier application — see each pack's
> truthfulness header. This is a real compliance gap against §2.1, tracked here rather than
> hidden, until either their source lands in this repo or the framework defines a
> deployed-no-source tier explicitly.
>
> **Known gap — CLAUDE.md `🔧 Planned` status was stale for 21 entities; all 21 now corrected.**
> A PR review (cubic) caught that 2 of the "no code exists" charter-only packs were factually
> wrong; a full audit found the real number was **21 of the 26** `🔧 Planned` entities already
> had real, substantial code in this repo. Of those 21, **14 have a router confirmed registered
> live in `api.py`** — The Library, The Basement, The Studio, The Lab, The Artifactory, Cryptex,
> The Dutchy (as `section7`), DevOcity, Tranquility, I-Mind, tAimra, VRAR3D, Resonate, and Think
> Tank (as `_thinktank_router` from `src/quantum/routes`). The remaining **7** — The Warp Tunnel,
> Warp Radio, The Academy, Sashas Photo Studio, TranceFlow, TateKing, Imaginarium — are **not**
> mounted in `api.py`, but each has a real, standalone `workers/<name>/worker.py` with its own
> Dockerfile **and a live service block in `docker-compose.production.yml`** (confirmed by grep for
> each service key), i.e. deployable independently of the monolith rather than absent. `CLAUDE.md`'s
> status column has been **corrected to `✅ In repo`** for all 21. Their doc-packs below are marked
> **⚠️ Mis-tiered**: still charter-only (GOV+RACI+TFM+POL+STD) even though their corrected
> Live-tier status now requires the full 11-artifact pack — this is the honest **current** gap (a
> real Partial/Live-tier rewrite with code-grounded DDD/TASD is still owed for all 21), not a
> stale-status problem anymore. Only 5 of the 26 originally-Planned entities are genuinely
> code-free: DocUtari, Fabulousa, API Marketplace, The Ice Box, ChronosSphere/ArcStream.
> **Follow-up required:** author real Partial/Live-tier packs (code-grounded DDD/TASD/SIM/ASD/
> PROC/RUN) for all 21 corrected entities — the charter-only packs are a stopgap, not the fix.

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
| 2026-07-04 | Follow-up: investigated the remaining 7 "stale-Planned, unresolved-wiring" entities directly against `docker-compose.production.yml` — confirmed each has its own service block (`tranceflow:`, `imaginarium:`, `tateking:`, `sashas-photo-studio:`, `the-academy:`, `warp-tunnel:`, `warp-radio:`), a real `Dockerfile`, and `workers/<name>/worker.py`, i.e. deployed as standalone services rather than mounted in `api.py`. Corrected `CLAUDE.md`'s status to `✅ In repo` for all 7 (Fabulousa excluded — confirmed genuinely code-free, no `workers/fabulousa/` directory exists). All 21 originally-stale-Planned entities are now status-corrected; recalculated coverage summary to 7/32 full Live-tier packs, 25 Live-tier charter-only (4 §2.1 exception + 21 outstanding gap), 6 Partial-tier, 5 genuinely Planned. |

[^void-port]: `PLATFORM_ENTITIES.md` lists The Void's *primary worker* as `config-service` (8024) —
    that is a **different** worker owned by the same entity (`PID-VOI`), not the vault
    (`infinity-void`, port 8002), so it is not an error. See `docs/services/the-void/` for the
    full pack.

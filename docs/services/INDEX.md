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
| **The Library** | 🔧 Planned | Zimik | ✅ **Complete** (charter-only) | `docs/services/the-library/` |
| **The Academy** | 🔧 Planned | Shimshi | ✅ **Complete** (charter-only) | `docs/services/the-academy/` |
| **DocUtari** | 🔧 Planned | TBD | ✅ **Complete** (charter-only) | `docs/services/docutari/` |
| **The Basement** | 🔧 Planned | Gary Glowman | ✅ **Complete** (charter-only) | `docs/services/the-basement/` |
| **The Studio** | 🔧 Planned | Voxx | ✅ **Complete** (charter-only) | `docs/services/the-studio/` |
| **Sashas Photo Studio** | 🔧 Planned | Madam Krystal | ✅ **Complete** (charter-only) | `docs/services/sashas-photo-studio/` |
| **TranceFlow** | 🔧 Planned | Junior Cesar | ✅ **Complete** (charter-only) | `docs/services/tranceflow/` |
| **TateKing** | 🔧 Planned | Benji Tate & Sam King | ✅ **Complete** (charter-only) | `docs/services/tateking/` |
| **Fabulousa** | 🔧 Planned | Baron Von Hilton | ✅ **Complete** (charter-only) | `docs/services/fabulousa/` |
| **Imaginarium** | 🔧 Planned | Voxx | ✅ **Complete** (charter-only) | `docs/services/imaginarium/` |
| **The Lab** | 🔧 Planned | The Dr. & Slime | ✅ **Complete** (charter-only) | `docs/services/the-lab/` |
| **The Artifactory** | 🔧 Planned | Lunascene | ✅ **Complete** (charter-only) | `docs/services/the-artifactory/` |
| **API Marketplace** | 🔧 Planned | Solarscene | ✅ **Complete** (charter-only) | `docs/services/api-marketplace/` |
| **Cryptex** | 🔧 Planned | Renik | ✅ **Complete** (charter-only) | `docs/services/cryptex/` |
| **The Ice Box** | 🔧 Planned | Neonach | ✅ **Complete** (charter-only) | `docs/services/the-ice-box/` |
| **The Warp Tunnel** | 🔧 Planned | Rocking Ricki | ✅ **Complete** (charter-only) | `docs/services/the-warp-tunnel/` |
| **Warp Radio** | 🔧 Planned | Rocking Ricki | ✅ **Complete** (charter-only) | `docs/services/warp-radio/` |
| **The Dutchy** | 🔧 Planned | Predictive lore | ✅ **Complete** (charter-only) | `docs/services/the-dutchy/` |
| **Think Tank** | 🔧 Planned | Trancendos | ✅ **Complete** (charter-only) | `docs/services/think-tank/` |
| **ChronosSphere / ArcStream** | 🔧 Planned | Chronos | ✅ **Complete** (charter-only) | `docs/services/chronosphere-arcstream/` |
| **DevOcity** | 🔧 Planned | Kitty | ✅ **Complete** (charter-only) | `docs/services/devocity/` |
| **Tranquility** | 🔧 Planned | Savania | ✅ **Complete** (charter-only) | `docs/services/tranquility/` |
| **I-Mind** | 🔧 Planned | Elouise | ✅ **Complete** (charter-only) | `docs/services/i-mind/` |
| **tAimra** | 🔧 Planned | tAImra | ✅ **Complete** (charter-only) | `docs/services/taimra/` |
| **VRAR3D** | 🔧 Planned | Entari | ✅ **Complete** (charter-only) | `docs/services/vrar3d/` |
| **Resonate** | 🔧 Planned | Magdalena | ✅ **Complete** (charter-only) | `docs/services/resonate/` |

**Coverage:** **7 / 11 required full packs** complete (Live-tier: The Spark, The Digital Grid,
Infinity, The Observatory, The Workshop, The Town Hall, The Citadel) · **6 Partial-tier packs**
(The Nexus, Luminous, Turing's Hub, The Void, Arcadia, The Chaos Party) · **30 Planned-tier /
charter-only packs** (GOV+RACI+TFM+POL+STD, intent-level, no fabricated DDD/RUN — 4 deployed-but-
no-repo-source CF Workers + 26 unbuilt Planned entities) · **43 / 43 entities now have a doc-pack**
of the tier their status requires · rollout order per framework §6.

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

[^void-port]: `PLATFORM_ENTITIES.md` lists The Void's *primary worker* as `config-service` (8024) —
    that is a **different** worker owned by the same entity (`PID-VOI`), not the vault
    (`infinity-void`, port 8002), so it is not an error. See `docs/services/the-void/` for the
    full pack.

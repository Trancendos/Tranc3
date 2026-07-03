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
| The Lighthouse | ✅ Deployed | Rocking Ricki | ⬜ Pending | CF `infinity-lighthouse` |
| The HIVE | ✅ Deployed | The Queen | ⬜ Pending | CF `infinity-hive` |
| Royal Bank of Arcadia | ✅ Deployed | Dorris Fontaine | ⬜ Pending | CF `arcadia-royal-bank` |
| Arcadian Exchange | ✅ Deployed | The Porter Family | ⬜ Pending | CF `arcadia-exchange` |
| The Citadel | ✅ Self-hosted | Trancendos | ⬜ Pending | Compose + Traefik |
| **The Void** | 🔧 Migrating | Prometheus (Prime: The Guardian) | ✅ **Complete** | `docs/services/the-void/` [^void-port] |
| **Luminous** | 🔧 Partial | Cornelius MacIntyre | ✅ **Complete** | `docs/services/luminous/` |
| **Turing's Hub** | 🔧 Partial | Samantha Turing | ✅ **Complete** | `docs/services/turings-hub/` |
| **Arcadia** | 🔧 Partial | Lilli SC (Prime: Dorris Fontaine) | ✅ **Complete** | `docs/services/arcadia/` |
| **The Chaos Party** | 🔧 Partial | The Mad Hatter (Prime: The Doctor) | ✅ **Complete** | `docs/services/the-chaos-party/` |
| The Library | 🔧 Planned | Zimik | ⬜ Charter-only | Outline |
| The Academy | 🔧 Planned | Shimshi | ⬜ Charter-only | Custom LMS |
| DocUtari | 🔧 Planned | TBD | ⬜ Charter-only | Paperless-ngx |
| The Basement | 🔧 Planned | Gary Glowman | ⬜ Charter-only | `src/basement/` (TBD) |
| The Studio | 🔧 Planned | Voxx | ⬜ Charter-only | `src/studio/` (TBD) |
| Sashas Photo Studio | 🔧 Planned | Madam Krystal | ⬜ Charter-only | SD + ComfyUI |
| TranceFlow | 🔧 Planned | Junior Cesar | ⬜ Charter-only | Godot |
| TateKing | 🔧 Planned | Benji Tate & Sam King | ⬜ Charter-only | FFmpeg |
| Fabulousa | 🔧 Planned | Baron Von Hilton | ⬜ Charter-only | Penpot |
| Imaginarium | 🔧 Planned | Voxx | ⬜ Charter-only | orchestrator |
| The Lab | 🔧 Planned | The Dr. & Slime | ⬜ Charter-only | `src/lab/` (TBD) |
| The Artifactory | 🔧 Planned | Lunascene | ⬜ Charter-only | Zot |
| API Marketplace | 🔧 Planned | Solarscene | ⬜ Charter-only | Gravitee |
| Cryptex | 🔧 Planned | Renik | ⬜ Charter-only | Wazuh + MISP |
| The Ice Box | 🔧 Planned | Neonach | ⬜ Charter-only | Cuckoo |
| The Warp Tunnel | 🔧 Planned | Rocking Ricki | ⬜ Charter-only | `src/security/warp_tunnel/` (TBD) |
| Warp Radio | 🔧 Planned | Rocking Ricki | ⬜ Charter-only | `src/warp_radio/` (TBD) |
| The Dutchy | 🔧 Planned | Predictive lore | ⬜ Charter-only | `src/research/` |
| Think Tank | 🔧 Planned | Trancendos | ⬜ Charter-only | `src/quantum/`, `src/deepmind/` |
| ChronosSphere / ArcStream | 🔧 Planned | Chronos | ⬜ Charter-only | Cal.com |
| DevOcity | 🔧 Planned | Kitty | ⬜ Charter-only | Custom portal |
| Tranquility | 🔧 Planned | Savania | ⬜ Charter-only | `src/tranquility/` (TBD) |
| I-Mind | 🔧 Planned | Elouise | ⬜ Charter-only | `src/imind/` (TBD) |
| tAimra | 🔧 Planned | tAImra | ⬜ Charter-only | `src/taimra/` (TBD) |
| VRAR3D | 🔧 Planned | Entari | ⬜ Charter-only | Three.js |
| Resonate | 🔧 Planned | Magdalena | ⬜ Charter-only | `src/resonate/` (TBD) |

**Coverage:** **6 / 11 required full packs** complete (Live-tier: The Spark, The Digital Grid,
Infinity, The Observatory, The Workshop, The Town Hall) · **6 Partial-tier packs**
(The Nexus, Luminous, Turing's Hub, The Void, Arcadia, The Chaos Party) · 43 / 43 entities
status-tracked · rollout order per framework §6.

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

[^void-port]: `PLATFORM_ENTITIES.md` lists The Void's *primary worker* as `config-service` (8024) —
    that is a **different** worker owned by the same entity (`PID-VOI`), not the vault
    (`infinity-void`, port 8002), so it is not an error. See `docs/services/the-void/` for the
    full pack.

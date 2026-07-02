# Service Doc-Pack Coverage Index

Tracks per-service design/architecture/governance documentation across all Trancendos
named entities. Governed by `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.
Artifact legend: **GOV** Charter · **DDD** · **TASD** · **RACI** · **SIM** · **ASD** ·
**TFM** · **POL** · **PROC** · **RUN** · **STD**.

**Required-by-status rule (honesty gate).** The `Status` column below shows the canonical
`PLATFORM_ENTITIES.md` label verbatim; the framework normalizes each to a **gate tier**
(see `DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1) that sets the required pack:
- **Live** (any `✅` label) → full 11-artifact pack, code-grounded.
- **Partial** (`🔧` labels except `🔧 Planned`) → GOV, RACI, TFM, POL, STD + DDD/TASD/SIM/ASD scoped to what exists.
- **Planned** (`🔧 Planned`) → GOV, RACI, TFM, POL, STD **only** (intent-level; no fabricated DDD/RUN).

Status column mirrors `PLATFORM_ENTITIES.md` — update both together.

| Service | Status | Lead AI | Pack | Notes |
|---------|--------|---------|------|-------|
| **The Spark** | ✅ In repo | Imfy (Prime: Norman Hawkins) | ✅ **Complete** (reference) | `docs/services/the-spark/` |
| The Digital Grid | ✅ In repo | Tyler Towncroft | ⬜ Pending | `src/workflow/` — next priority |
| Infinity | ✅ Self-hosted | The Guardian | ⬜ Pending | `workers/infinity-auth/` (8005) |
| The Nexus | 🔧 Self-hosted | Nexus-Prime | ⬜ Pending | `workers/infinity-ws/` (8004) |
| The Observatory | ✅ Self-hosted | Norman Hawkins | ⬜ Pending | `src/observability/` |
| The Workshop | ✅ In repo | Larry Lowhammer | ⬜ Pending | `deploy/forgejo/` |
| The Town Hall | ✅ Integrated | Tristuran | ⬜ Pending | `workers/cranbania/` (8071) |
| The Lighthouse | ✅ Deployed | Rocking Ricki | ⬜ Pending | CF `infinity-lighthouse` |
| The HIVE | ✅ Deployed | The Queen | ⬜ Pending | CF `infinity-hive` |
| Royal Bank of Arcadia | ✅ Deployed | Dorris Fontaine | ⬜ Pending | CF `arcadia-royal-bank` |
| Arcadian Exchange | ✅ Deployed | The Porter Family | ⬜ Pending | CF `arcadia-exchange` |
| The Citadel | ✅ Self-hosted | Trancendos | ⬜ Pending | Compose + Traefik |
| The Void | 🔧 Migrating | Prometheus | ⬜ Pending | `workers/infinity-void/` (8082) |
| Luminous | 🔧 Partial | Cornelius MacIntyre | ⬜ Pending | `src/bio_neural/`, `src/core/` |
| Turing's Hub | 🔧 Partial | Samantha Turing | ⬜ Pending | `src/personality/` |
| Arcadia | 🔧 Partial | Lilli SC | ⬜ Pending | `web/` |
| The Chaos Party | 🔧 Partial | The Mad Hatter | ⬜ Pending | `tests/test_chaos.py` |
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

**Coverage:** 1 / 43 complete · reference pack established · rollout order per framework §6.

## Rollout log

| Date | Change |
|------|--------|
| 2026-07-02 | Framework + template + The Spark reference pack; index established (1/43). |

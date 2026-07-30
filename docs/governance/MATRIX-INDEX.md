# Matrix Index

> **What this is.** A single master map answering one question for every "Matrix" or "Framework"
> requested across this platform's governance brainstorming: **does real code already back this,
> and if so, is it documented?** Most of the ~35 items requested turned out to already exist as
> real, running code — just scattered, unnamed, or documented under a different name — following
> the exact pattern already found for circuit breakers (4 implementations, one name), Location
> Traffic (real building blocks, no unified matrix), and the AI Relationship Matrix. This index is
> the map; the docs it links to (existing or newly written) are the territory.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. How to read this table

- **Exists + documented** — real code, already has a governance doc. Just listed here with a
  pointer.
- **Exists, newly documented** — real code was already running but had no consolidating doc until
  this pass. A new doc now exists (linked).
- **Exists, thin** — real code exists but is minimal/utility-level, not a governance system. Noted
  honestly rather than inflated into a "Matrix" it isn't.
- **Genuine gap** — no real code found. Not built. Recorded here so a future pass doesn't have to
  re-derive that finding from scratch.

## 2. The map

| Requested item | Status | Real code | Doc |
|---|---|---|---|
| Error Code Matrix / Registry | Exists + documented | `src/errors/error_catalog.py` (`ErrorCode` enum) | Referenced in `docs/governance/CODE-COMPLIANCE-MATRIX.md`; full doc — [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) |
| CVE Matrix | Exists, newly documented | `src/platform/intelligent_scanner.py`, `zero_cost_service_map.py`, `.forgejo/workflows/security-scan.yml`/`dependency-audit.yml` | [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §3 |
| Remediation Matrix | Exists, newly documented | `src/healing/nanocode_bots.py`, `src/audit/automated_auditor.py` | [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §4 |
| Self-Healing Matrix | Exists, newly documented | `src/observability/self_healer.py`, `src/adaptive/cell_automaton.py` | [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §5 |
| Diagnosis / Resolution Matrix | Exists, newly documented | `src/intelligence/causal_reasoner.py`, `src/workflow/builder.py` diagnosis nodes | [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §6 |
| Health Matrix | Exists + documented | `src/observability/health.py` (Health Aggregation, `CLAUDE.md` Observability Stack) | `CLAUDE.md` Observability Stack section |
| Circuit Breaker Matrix | Exists + documented | `src/resilience/circuit_core.py` + TASD-001 | `docs/architecture/decisions/TASD-001-circuit-breaker-consolidation.md`, `docs/governance/HARD-STOP-MATRIX.md` |
| Loop Framework | Exists + documented | `src/validation/loop_validator.py`'s `LoopValidator` — cascade-failure prevention, same TASD-001 consolidation | `TASD-001`, `HARD-STOP-MATRIX.md` |
| Permissions Matrix | Exists, newly documented | `src/roles/registry.py` (Job Description assignment) + `src/access/registry.py` (per-user Location subscription/consent) + Zero Trust IAM (`src/auth/zero_trust.py`) | [PERMISSIONS-ACCESS-MATRIX.md](PERMISSIONS-ACCESS-MATRIX.md) |
| Privacy Matrix | Exists, newly documented | `src/privacy/dsr_workflow.py` — real GDPR DSR automation (access/erasure/rectification/portability/restriction/objection, 30-day SLA tracking) | [PRIVACY-MATRIX.md](PRIVACY-MATRIX.md) |
| Data Registry | **Genuine gap** | No dataset/data-asset registry found. `src/access/registry.py` is a *user-consent* registry, not a data-asset one; `src/training/dataset.py`/`src/core/dataset.py` are ML data loaders, not a governance registry | Recorded here as a gap |
| Validation Matrix | Exists, thin | `src/validation/validators.py` — basic input validators (email, username, port, safe-string). Real, but utility-level, not a governance system | Noted here; not inflated into a doc |
| Routing Matrix | Exists, thin | `src/routers/`, `workers/model-router-service/`, per-tier `t2ance/router.py` / `trance_one/router.py` FastAPI routers. These are literal HTTP routers, not a routing-policy governance matrix | Noted here |
| Worker Matrix | Exists + documented | The Self-Hosted Worker Map is already the platform's Worker Matrix | `CLAUDE.md` Self-Hosted Worker Map table (90+ workers, ports, priorities) |
| API Matrix | Exists + documented | `src/apimarket/marketplace.py` (external), FastAPI routers (internal) | `CLAUDE.md` API Marketplace entity; internal APIs undocumented as a single surface (see gap note below) |
| Marketplace Matrix | Exists + documented | `src/apimarket/marketplace.py` — API Marketplace, already a named platform entity | `CLAUDE.md` entity table |
| Data Share Framework | **Genuine gap** | No cross-Location data-sharing framework found beyond ad hoc HTTP calls between workers | Recorded here as a gap |
| Federated Learning Framework / Matrix | Exists, thin | `src/nanoservices/fmd_distiller/` (federated model distillation) — real but narrow, one nanoservice, not a platform-wide framework | Noted here |
| Token Calculation Matrix | Exists + documented | Distinct from Token *Efficiency* Matrix (already built) — token counting/budgeting lives in `src/ai_gateway/` provider adapters | `docs/governance/TOKEN-EFFICIENCY-MATRIX.md` (closest existing doc; a pure calculation-mechanics doc doesn't exist separately and would duplicate it) |
| Activity Matrix | Exists + documented | `src/relations/registry.py`'s Activity Feed | `docs/governance/AI-RELATIONSHIP-MATRIX.md` §7 |
| Observation Matrix | Exists + documented | `src/relations/registry.py`'s `get_insights()` (busiest Location, negative-activity spikes, at-risk relationships) | `docs/governance/AI-RELATIONSHIP-MATRIX.md` §8 |
| Learning Matrix | Exists, thin | `workers/mlflow-service/` (experiment tracking), Turing's Hub (`src/personality/`) skill benchmarking. No single "how the platform learns" governance doc | Noted here; candidate for a future pass if MLflow usage grows |
| Development Matrix | Exists + documented | DevOcity (`src/devocity/`) is already the named platform entity for this | `CLAUDE.md` entity table |
| Defensive / Protective Matrix | Exists + documented | Cryptex (`src/cryptex/`), The Ice Box (`workers/ice-box-service/`), The Warp Tunnel (`src/security/warp_tunnel/`) are already named platform entities covering this | `CLAUDE.md` entity table; `docs/governance/ESTATE-PROTECTION-MATRICES.md` |
| Vulnerability Matrix | Exists, newly documented | Same as CVE Matrix above | [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §3 |
| Research Matrix | Exists + documented | The Dutchy (`src/research/`) is already the named entity for Intelligence & Market Analysis | `CLAUDE.md` entity table |
| Solutions Matrix | **Genuine gap** | No dedicated "solutions" tracking system found distinct from Remediation | Recorded here as a gap |
| Testing Matrix | Exists + documented | The Chaos Party (`tests/test_chaos.py`, `workers/chaos-party/`) + `src/nanoservices/chaos_engineering/` are already the named entity/system for this | `CLAUDE.md` entity table |
| AI to Agent Matrix | Exists, newly documented | `src/agents/orchestrator.py` — real SQLite-backed multi-agent task queue (`AgentConfig`, `AgentTask`, priority scheduling) | [AI-AGENT-BOT-TIER-MATRIX.md](AI-AGENT-BOT-TIER-MATRIX.md) §2 |
| AI to Bot Matrix | Exists + documented | `src/workers/bot_registry.py`'s `BotRegistry` — 12 bot types, already documented in `CLAUDE.md`'s BotRegistry section | [AI-AGENT-BOT-TIER-MATRIX.md](AI-AGENT-BOT-TIER-MATRIX.md) §3 |
| Orchestrator AI to Prime AI Matrix | Exists, newly documented | `trance_one/tier_bridge.py` (`TierCommand`/`TierCommandType`) — real Tier-1→Tier-2 command dispatch, live at `/sovereign/dispatch/{command_type}` | [AI-AGENT-BOT-TIER-MATRIX.md](AI-AGENT-BOT-TIER-MATRIX.md) §4 |
| Prime AI to AI Matrix | Exists, newly documented | `t2ance/prime_registry.py`/`domain_authority.py` — `prime_for_entity()` maps every Tier-3 entity to its governing Domain Prime | [AI-AGENT-BOT-TIER-MATRIX.md](AI-AGENT-BOT-TIER-MATRIX.md) §5 |
| Location (Application) Matrix | Exists + documented | `PLATFORM_ENTITIES` itself | `CLAUDE.md` entity table, `PLATFORM_ENTITIES.md` |
| Location to Location Traffic Matrix | Done this session | — | `docs/governance/LOCATION-TRAFFIC-MATRIX.md` |
| Relationship Matrix | Exists + documented | `src/relations/registry.py` | `docs/governance/AI-RELATIONSHIP-MATRIX.md` |
| Attribute Matrix | Exists + documented | `LocationEntity` dataclass fields themselves (`src/entities/platform.py`) | `PLATFORM_ENTITIES.md` |
| Entity Matrix | Exists + documented | `PLATFORM_ENTITIES` | `PLATFORM_ENTITIES.md` |
| Association Matrix | Exists, thin | `src/cmdb/models.py` — CMDB-style associations between platform components, but this is infrastructure CMDB, not entity-to-entity association in the `PLATFORM_ENTITIES` sense | Noted here |

## 3. What this pass produced

Four new docs, each grounded in real, already-running code found during this investigation:

1. **[ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md)** — Error Code Registry, CVE/Vulnerability tracking, Remediation, Self-Healing, and Diagnosis/Resolution, which all turned out to be genuinely interconnected (an error surfaces → gets classified against a CVE/pattern → triggers remediation → self-healing closes the loop) rather than five separate systems.
2. **[PERMISSIONS-ACCESS-MATRIX.md](PERMISSIONS-ACCESS-MATRIX.md)** — the Role Registry (who holds a Job Description), the Access Registry (who's consented into which Location), and Zero Trust IAM (device/MFA/geo risk scoring), consolidated.
3. **[PRIVACY-MATRIX.md](PRIVACY-MATRIX.md)** — the GDPR DSR workflow, which was fully built and REQ-PRI-001-tagged but had no governance doc pointing to it.
4. **[AI-AGENT-BOT-TIER-MATRIX.md](AI-AGENT-BOT-TIER-MATRIX.md)** — AI-to-Agent, AI-to-Bot, Orchestrator-to-Prime, and Prime-to-AI, since these four are really one hierarchy (Trance-One Sovereign → T2ance Primes → Tranc3 Lead AIs → Agents → Bots) split across `trance_one/`, `t2ance/`, `src/agents/`, and `src/workers/bot_registry.py`.

## 4. Genuine gaps recorded (not built)

Four items had no real code behind them anywhere in the repo:

- **Data Registry** — a dataset/data-asset governance registry (distinct from the Access Registry's user-consent tracking).
- **Data Share Framework** — a formal cross-Location data-sharing contract/audit layer.
- **Solutions Matrix** — a dedicated "proposed solutions" tracker distinct from Remediation.
- Two items exist only as **thin utility code**, not governance systems: **Validation Matrix**
  (`src/validation/validators.py` is a handful of input validators) and **Association Matrix**
  (`src/cmdb/models.py` is infrastructure CMDB, not entity association).

None of these are built as part of this pass — inventing a "Matrix" doc for code that doesn't exist
would misrepresent the platform's actual state, the same reasoning applied to
`LOCATION-TRAFFIC-MATRIX.md` earlier. If any of these four is wanted as real functionality later,
that's a build task, not a documentation one.

## 5. Cross-references

- `docs/governance/AI-RELATIONSHIP-MATRIX.md`, `LOCATION-TRAFFIC-MATRIX.md`, `HARD-STOP-MATRIX.md`,
  `THRESHOLD-MATRIX.md`, `GPU-MATRIX.md`, `TOKEN-EFFICIENCY-MATRIX.md`, `CODE-COMPLIANCE-MATRIX.md`
  — the matrices this index builds on rather than duplicates.
- `docs/governance/TRANCENDOS-MODELS-MATRIX.md` — the tier/governance system
  `AI-AGENT-BOT-TIER-MATRIX.md` cross-references rather than re-describes for the advancement-
  pipeline side of Trance-One/T2ance.

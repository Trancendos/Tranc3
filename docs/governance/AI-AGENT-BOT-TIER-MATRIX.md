# AI ↔ Agent ↔ Bot Tier Matrix

> **What this is.** Four brainstormed items — AI-to-Agent, AI-to-Bot, Orchestrator-AI-to-Prime-AI,
> and Prime-AI-to-AI — are really one 5-tier hierarchy split across four modules that don't
> currently cross-reference each other: `trance_one/` (Tier 1), `t2ance/` (Tier 2), the named
> Lead AIs (Tier 3, already covered by `PLATFORM_ENTITIES`), `src/agents/` (Tier 4), and
> `src/workers/bot_registry.py` (Tier 5). This doc is the connective map.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. The five tiers, restated for this matrix

| Tier | Name | Module | Real, live? |
|---|---|---|---|
| 1 | Sovereign / Orchestrator | `trance_one/` | Yes — `/sovereign` HTTP surface |
| 2 | Prime | `t2ance/` | Yes — `/primes` HTTP surface |
| 3 | Lead AI | `PLATFORM_ENTITIES` (`src/entities/platform.py`) | Yes — the 43-entity table itself |
| 4 | Agent | `src/agents/` | Yes — SQLite-backed, no HTTP surface yet (see §2) |
| 5 | Bot | `src/workers/bot_registry.py` | Yes — `BotRegistry`, already in `CLAUDE.md` |

This matches `CLAUDE.md`'s own Tier 1–5 vocabulary (Sovereign/Primes/Lead AI/Agents/Bots) — nothing
new is being introduced, just connected.

## 2. AI to Agent

`src/agents/orchestrator.py`'s `AgentOrchestrator` — a real, SQLite-persisted multi-agent task
queue, explicitly inspired by `@trancendos/agent-sdk`'s `agent-orchestrator.ts`
(infinity-adminOS), zero-cost (pure Python asyncio + sqlite3, no external dependencies).

- `AgentConfig` — static registration: `id`, `name`, `role`, `tools`, `max_concurrent_tasks`,
  `priority`.
- `AgentTask` — a unit of work: `agent_id`, `description`, `priority` (0–10), `status`
  (pending/running/completed/failed), timestamps, `result`.
- `AgentPerformance` — tracked per agent.

`src/agents/agent_types.py`'s `AgentType` enum and `AgentProfile` dataclass define the catalog of
agent kinds a Lead AI can dispatch work to, with `find_best_profile(required_tags)` doing
capability-based matching.

**Gap:** like the Privacy Matrix's DSR workflow, this orchestrator has no mounted HTTP router —
grepping for its usage shows the class is real and presumably invoked in-process, but there's no
`/agents` API surface documented anywhere. Worth flagging alongside `PRIVACY-MATRIX.md`'s identical
finding as a recurring pattern: several real subsystems in this codebase are built but not yet
exposed.

## 3. AI to Bot

`src/workers/bot_registry.py`'s `BotRegistry` — already documented in `CLAUDE.md`'s BotRegistry
section. 12 bot types split into **inference bots** (`InferenceBot`, `EmbeddingBot`, `EmotionBot`,
`TokenizeBot`, `ConsciousnessBot`, `PersonalityBot`, `PredictBot` — all proxy to Tranc3Engine) and
**utility bots** (`CODE`, `MEMORY`, `MONITOR`, `SEARCH`, `SUMMARISE` — standalone). This is the most
mature of the four relationships in this doc — already live in `tranc3-bots` (port 8080).

## 4. Orchestrator AI to Prime AI

`trance_one/tier_bridge.py`'s `TierCommand`/`TierCommandType` — a real command relay, live at
`/sovereign/dispatch/{command_type}` (`trance_one/router.py`). `TierCommandType` spans far more than
Tier 1↔2:

- **Lifecycle**: `ACTIVATE_ENTITY`, `DEACTIVATE_ENTITY`, `ROTATE_ENTITY`, `RESTART_ENTITY`.
- **Policy**: `ENFORCE_ZERO_COST`, `SUSPEND_PAID_CALLS`.
- **Intelligence** (crosses all the way to Tier 4/5): `PROMOTE_AGENT` (temporary Tier 4→3
  elevation), `RECALL_AGENT`, `SPAWN_WORKER` (Tier 5), `TERMINATE_WORKER`.
- **Platform**: `PLATFORM_HEALTH_CHECK`, `BROADCAST_STATUS`.

Every `TierCommand` and `TierEvent` is logged to The Observatory audit trail per the module's own
docstring. `TRANCENDOS-MODELS-MATRIX.md` already documents the *governance* side of Trance-One/
T2ance (the `board_and_human` advancement-approval pipeline); this tier bridge is the *operational
command* side — a different concern the Models Matrix doc doesn't cover, not a duplicate of it.

## 5. Prime AI to AI

`t2ance/domain_authority.py`'s `DomainPrime` — each of the 9 `PrimeDomain`s (ArchPrime, CommPrime,
CreatePrime, DevPrime, KnowPrime, SecPrime, WellPrime, GovPrime, OpsPrime) governs a real,
enumerated set of Tier-3 entity IDs via `DOMAIN_ENTITY_MAP` (e.g. ArchPrime governs `the-spark`,
`the-digital-grid`, `the-hive`, `the-nexus`, `infinity`, `luminous`). `t2ance/prime_registry.py`'s
`prime_for_entity()` resolves the reverse lookup — which Prime governs a given entity — live at
`/primes/entity/{entity_id}`. Rotation requests route through `get_relay().route_rotation_request()`
(`/primes/rotate/{entity_id}`), and a full adaptive-intelligence report across all 9 Domain Primes
is live at `/primes/intelligence`.

## 6. What this doc adds that didn't exist before

Nothing new was built. The value here is that `trance_one/`, `t2ance/`, `src/agents/`, and
`src/workers/bot_registry.py` had zero cross-references to each other before this pass — each is a
real, independently-documented-or-undocumented system, and this doc is the first place that states
plainly they form one 5-tier command/delegation hierarchy.

## 7. Cross-references

- `docs/governance/TRANCENDOS-MODELS-MATRIX.md` — the governance/advancement side of Tiers 1–3.
- `docs/governance/PRIVACY-MATRIX.md` — the sibling "real code, no HTTP surface" finding for the
  DSR workflow, same pattern as this doc's §2 finding for `AgentOrchestrator`.
- `CLAUDE.md` — BotRegistry (§3) and the Tier 1–5 vocabulary this doc is built on.

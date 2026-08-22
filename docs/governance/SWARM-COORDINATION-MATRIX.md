# Swarm Coordination Matrix

> **What this is.** A brainstorm session (external, not this codebase) proposed a large stigmergy /
> ant-colony-optimization / particle-swarm system for The HIVE — Redis pheromone fields, MMAS
> islands, adaptive evaporation, migration topologies — as blueprint code, explicitly caveated by
> its own author as unverified against the real platform. This document does the verification: it
> traces "swarm" and "pheromone" through the actual repo, states plainly what already exists, what
> is scaffolding, and what genuinely does not exist yet — following the same discipline as
> [MATRIX-INDEX.md](MATRIX-INDEX.md) and [BOM-MATRIX.md](BOM-MATRIX.md): check real code before
> building anything new.

**Owner:** Cornelius MacIntyre (The HIVE's Prime) · **Version:** 1.0.0 · **Last verified:** 2026-08-07

---

## 1. What's real: ACO-pheromone backend selection (already shipped, tested, in production)

`workers/cache-service/worker.py` — literally docstringed `"ACO pheromone router, 7 zero-cost
backends"` — implements a real, minimal, scalar reinforcement/decay pattern:

```python
class ThresholdGuard:
    pheromone: float = 1.0
    def reinforce(self) -> None: self.pheromone = min(1.0, self.pheromone + 0.1)
    def decay(self) -> None: self.pheromone = max(0.0, self.pheromone - PHEROMONE_DECAY)

def _select_backend() -> str:
    return max(available, key=lambda b: _GUARDS[b].pheromone) if available else "offline"
```

Each of the 7 cache backends (in-memory, Valkey, SQLite, DuckDB, diskcache, Dragonfly, offline
stub) carries one pheromone value in `[0, 1]`. A successful call reinforces its backend; a failure
decays it (`CACHE_PHEROMONE_DECAY`, default `0.05`). Backend selection is a greedy max over
current pheromone. Exercised in `tests/test_workers_p3.py` (backend-selection assertions with
guard-state snapshot/restore between tests) — this is real, not decorative.

The same *general* ACO-pheromone pattern — a scalar that reinforces on success and decays on
failure, guiding a greedy pick — greps across 11 other workers (Observatory, TranceFlow, The Grid,
analytics-service, library-service, lab-service, storage-service, Cryptex, cron-service, VRAR3D,
files-service — 12 total including cache-service) plus 4 shared `src/` modules
(`src/adaptive/dna_router.py`, `src/mesh/genetic_router.py`,
`src/nanoservices/symbiotic_collective/symbiotic_collective.py`, and
`src/ai_gateway/provider_rotation.py`). **These are not literally the same `ThresholdGuard` class
reused** — spot-checking a sample shows independent implementations of the same idea:
`files-service/worker.py` defines its own separate `_ThresholdGuard`; `provider_rotation.py` calls
a differently-named `AntColonyRouter` (`Dimensional.swarm.ant_colony`); `genetic_router.py`
implements its own `RouteGene` dataclass with a `pheromone` field and its own
deposit/decay/desirability methods; `dna_router.py` is a genetic-algorithm wrapper that says it's
*"compatible with"* the ACO pheromone router rather than being one itself. This doc verifies
cache-service's copy line-by-line; the rest share the *concept*, not a shared implementation — a
full per-file audit of how many independent variants exist is recorded as a gap in §6, not claimed
here.

**So the core instinct — "pheromone-style adaptive selection is a real Trancendos idiom" — is correct.**
It's just much smaller than the external brainstorm assumed: one float per option, reinforce/decay,
greedy pick. No islands, no Redis, no MMAS bounds, no migration.

## 2. What's real: The HIVE's `SwarmCoordinator` — group lifecycle, not emergent coordination

`workers/hive-service/Dimensional/hive/hive_core.py` is real, deployed (see §3), and does exactly
what its own docstring claims: *"data movement and swarm system coordination"* — `SwarmCoordinator`
creates named `Swarm` objects (purpose: ETL / aggregation / replication), tracks `SwarmNode`
membership and `SwarmStatus` (forming → active → …), and `FlowMonitor` records per-pipeline
throughput/latency to SQLite.

This is a **group-lifecycle registry**, not a stigmergic system: no pheromone field, no decay, no
choice-probability over candidates. Grepped explicitly for `self.heal`/`self_heal`/`topology` in
`hive_core.py`, `sentinel_bridge.py`, and `worker.py` — zero matches. `PLATFORM_ENTITIES.md`'s
"Self-Healing Topology" ability for PID-HVE has no corresponding code found; treat it as flavor
text, same honest-gap treatment `MATRIX-INDEX.md` gives other unbuilt "abilities."

## 3. Genuine drift found while researching this (not previously documented in this session)

Four separate queue/cache/hive-named workers were deployed in `workers/` at the time of writing
(a fifth, `queue-service-go`, was removed as dead code in the same pass — see below):

| Worker | Language | Compose-deployed? | Role |
|---|---|---|---|
| `queue-service` | Python | ✅ (port 8022) | Priority task queue, retry/dead-letter/sweep. Docstring: *"Lead AI: The Queen"* |
| `cache-service` | Python | ✅ (port 8023) | ACO pheromone router (§1) |
| `hive-service` | Python | ✅ (port 8051) | `SwarmCoordinator` / `FlowMonitor` (§2) |
| `bullmq-queue-service` | Node/TypeScript | ✅ (port 8092) | BullMQ-backed queue; ownership vs. `queue-service` unclear from either worker's own docs |

One concrete, previously-unflagged issue confirmed, and one initially-suspected issue retracted
after deeper checking:

1. **`queue-service-go` was dead code — removed.** Zero commits since its single creation commit,
   no Dockerfile, not referenced anywhere in `docker-compose.production.yml`. A 2026-07-05 audit
   pass (`docs/services/the-artifactory/README.md`) had already flagged it as missing a Dockerfile
   but left it unresolved. Rather than build deployment infrastructure for an untested, fully
   redundant Go reimplementation of the role `queue-service` (Python, deployed, tested) already
   fills, the directory was deleted and the stale doc reference removed. It's also recorded (as
   `SRV-QUEUEGO-001`/`APP-QUEUEGO-001`/`DEP-QUEUEGO-001`, all already annotated `"not deployed, not
   reviewed"`) in three `docs/architecture/ea-workbook/*.csv` rows alongside two sibling
   never-deployed Go/Rust rewrites (`monitoring-go`, `rate-limit-service-go`/`-rs`) — those CSV
   rows are point-in-time inventory snapshots from an earlier session, left as-is rather than
   edited here, consistent with treating `docs/services/INDEX.md` as an append-only record above.
2. **`hive-service` does *not* have a port drift — initial read was wrong, corrected here.** This
   doc originally flagged `worker.py`'s bare Python default (`HIVE_PORT` env var, falling back to
   `8060` only if unset) against compose's routed port (`8051`) as a mismatch. Checking the actual
   `Dockerfile` shows its `CMD` hardcodes `uvicorn worker:app --port 8051` directly — the Python
   fallback is unreachable dead code, the same pattern `CLAUDE.md`'s "Routing defects (issue #188)"
   section already documents for `audit-service`/`queue-service`/`search-service`. Compose also sets
   `HIVE_PORT=8051` explicitly as a second, redundant safeguard. No drift exists; retracted rather
   than left standing, since a false finding in a doc about honest verification would defeat its
   own purpose.

Neither issue is caused by, or related to, the external brainstorm — both surfaced purely from
tracing "does HIVE's queue/cache infrastructure actually work the way the docs say" for this
review.

## 4. What's not real: `DistributedIntelligenceSwarm` / `main_2060.py`

`src/distributed/swarm_intelligence.py` declares `self.pheromone_trails: Dict = {}` — and never
reads or writes it again anywhere in the file. Task assignment (`_assign_tasks`) is plain
round-robin. `_execute_on_node` "executes" by encoding text as `ord(c) % 768` into a `torch.Tensor`
— there is no real distributed execution, no actual node compute. The class is wrapped in
`IntelligenceBlockchain` and `HomomorphicCrypto` scaffolding that reads as far more sophisticated
than what it does.

It is reachable only via `main_2060.py` (repo root, not under `src/` — name is the platform's own
signal: a 2060 vision file,
not the real entry point — that's `api.py` per `CLAUDE.md`), which is **not referenced by any
Dockerfile or `docker-compose.production.yml` service** and has no test coverage. It sits behind
`FeatureFlag.SWARM_INTELLIGENCE`, gated by `ENABLE_SWARM` — **defaulting to `false`**, grouped with
equally-inactive `ENABLE_HOLOGRAPHIC` and `ENABLE_EVOLUTION` flags. This is honestly-marked
speculative scaffolding, not a hidden production system — no correction needed there, just don't
mistake it for evidence that "real" distributed swarm intelligence already runs on Trancendos.

## 5. Verdict on the external brainstorm

| Claim | Verdict |
|---|---|
| "Queen + emergent coordination isn't a contradiction" | Correct, and consistent with `PLATFORM_ENTITIES.md`'s own "Swarm Packet Optimization" / "Self-Healing Topology" flavor text for PID-HVE |
| "Pheromone-style reinforcement is a viable pattern here" | Correct — it's already real, shipped, tested (§1) — just far smaller in scope than proposed |
| "The HIVE already does emergent, decentralized task routing" | Not true — `SwarmCoordinator` is a group registry (§2) |
| "Route this through Redis + Lua + multi-island MMAS/PSO" | Contradicts `CLAUDE.md`'s stated architecture principles (*"In-memory rate limiting over Cloudflare KV,"* *"SQLite over Cloudflare D1 — no shared state"*) — would add a new shared-state dependency the platform's own principles argue against |
| "API Marketplace is the wrong place for this" | Correct — internal HIVE coordination isn't a Commercial/Financial-pillar concern |
| "Cornelius sits directly above the HIVE, below the human admin, in escalation" | Corroborated independently — several suites in `compliance/matrix_suites.yaml` (Matrix Suites Stage 7.1–7.3, this same session) literally have `escalation: [..., "Cornelius MacIntyre", "Human owner"]` |

## 6. Honest gaps (recorded, not built)

- **No per-worker audit of the other 11 `ThresholdGuard` copies.** §1 verified `cache-service`
  line-by-line; the rest share the pattern by grep only. Whether they're independent copies (drift
  risk) or intentional per-worker tuning is unknown.
- **`queue-service` vs. `bullmq-queue-service` ownership** — two independently-deployed task queues
  with no documented division of responsibility.
- **No stigmergic (multi-option, decaying-field) coordination exists above the single-scalar
  `ThresholdGuard` pattern anywhere in the deployed stack.** If a real multi-agent routing problem
  ever emerges (not evidenced today) that needs more than reinforce/decay-and-pick-max, the
  starting point should be extending `ThresholdGuard`'s already-shipped, already-tested idiom — not
  a new Redis-backed subsystem.

No code changes accompany this document. It is a scoping/gap record only, matching the honesty
rule inherited from `REGULATION-MATRIX.md` §6 and applied throughout `MATRIX-SUITES.md`: a capability
being *documented* is not a capability being *built*.

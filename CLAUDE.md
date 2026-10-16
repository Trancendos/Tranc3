# CLAUDE.md

> **NON-AUTHORITATIVE — READ THIS FIRST**
>
> This file is **temporary working guidance** for AI coding assistants (Claude Code and others) when operating inside this repository.  
> It is **not** the system of record.
>
> **Canonical sources of truth (in priority order):**
> 1. **Magna Carta** (`compliance/magna-carta/`) — constitutional rules and non-negotiable governance
> 2. **The Town Hall** (CranBania + `src/townhall/`) — decisions, work routing, Kanban / ITSM flow
> 3. **The Library** (`src/library/`) — durable knowledge, runbooks, architecture decisions
> 4. Platform Entities & Models Matrix
> 5. The Observatory / Basement (audit & archive)
>
> See `docs/governance/SOURCE-OF-TRUTH-AND-WORK-FLOW.md` for the full policy.
>
> Any durable fact discovered while using this file **must** be written into the appropriate canonical location above.  
> Do not treat this file as the backlog, the constitution, or the knowledge base.

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Testing
make test            # full pytest suite with coverage
make test-fast       # skip slow/integration tests
pytest tests/test_tranc3_ml.py -v  # single test file

# Targeted test suites (all produce logs/test_results.jsonl)
pytest tests/test_smoke.py -v           # fast sanity checks (<2s)
pytest tests/test_uat.py -v             # user acceptance / end-to-end journeys
pytest tests/test_chaos.py -v           # fault injection and resilience
pytest tests/test_penetration.py -v     # OWASP injection / security boundary
pytest tests/test_compliance.py -v      # error catalog, MCP protocol, GDPR
pytest tests/test_nanoservices.py -v    # nanoservice layer (port 8001)
pytest tests/test_compatibility.py -v  # JSON-RPC 2.0, Pydantic v2, serialization
pytest tests/test_validation.py -v     # input validation and schema enforcement
pytest tests/test_spark_grid_integration.py -v  # The Spark + The Digital Grid integration

# Linting
make lint            # ruff + mypy

# Dev servers
make dev-api         # FastAPI backend on :8000 (hot-reload)
make dev-web         # frontend dev server

# Database
make migrate         # apply pending Alembic migrations
make migrate-new msg="describe change"  # create a new migration

# Cleanup
make clean           # remove __pycache__, .pyc, build artefacts
```

The `tranc3-bots` sub-project has its own pyproject.toml with matching pytest config; run tests from `tranc3-bots/` with `pytest`.

## Trancendos Platform — Named Services

Every service, location, and subsystem has a canonical code name. Use ONLY these names in code, comments, routes, log messages, and documentation.

Canonical reference for all 43 platform entities: `PLATFORM_ENTITIES.md` and `src/entities/platform.py`.

**Location Functions & Job Descriptions.** Every Location has a functional Job Description title
(e.g. Royal Bank of Arcadia → Chief Financial Officer) distinct from its canonical `lead_ai` name
— see `docs/governance/LOCATION-FUNCTIONS.md`. Which AI currently holds that Job Description is
mutable at runtime via the Role Assignment Registry (`src/roles/registry.py`, SQLite-backed,
exposed at `/roles` — `src/roles/routes.py`, mounted in `api.py`), letting operators add, remove,
or reassign AIs to a role without a code change; every change is recorded in an audit history.

**Backlog Routing Register.** Which Location owns an outstanding item is a Town Hall
decision, not a lookup: `src/townhall/routing.py` (SQLite-backed, exposed at
`/townhall/routing` — `src/townhall/routing_routes.py`, mounted in `api.py`) records the
Location, the named authority, the written reason and the Location's solution pack, emits
`townhall.item.routed` to The Observatory, and never overwrites — a re-route supersedes and
both rows stay in `routing_history`. It refuses a Location that is not one of the 43, and one
with no solution pack, because routing work to a place with no architecture or acceptance
criteria is what "unrouted" already means. Decisions are exported to
`config/estate/backlog_routing.yaml`, which is what `scripts/build_action_backlog.py` reads in
CI — the export is also what makes a routing decision show up in a diff. Items with no
decision stay `_unrouted_` in the backlog, and that count is a queue the Town Hall owes an
answer to rather than a number assigned away by judgement.

**Trancendos Models Matrix.** Every named AI's base model is one of the platform's existing
orchestration tiers — **Trance-One** (Tier 1, Sovereign/Orchestrator, most capable), **T2ance**
(Tier 2, Primes), or **Tranc3** (Tier 3, Lead AI/AI Base, the default) — via
`get_orchestration_tier()` in `src/entities/platform.py`. An AI's base model can expand into a
named specialized variant when associated with a distinguishing skill matrix (e.g. The Dr. →
`T2ance-CODE`, George Porter → `Tranc3-Crypto`); see `docs/governance/TRANCENDOS-MODELS-MATRIX.md`
for the full base-tier/variant table, the regular benchmarking mechanism, and the governed
advancement pipeline (Prime → Cornelius → Human, each with its own % threshold) that gates a real
skill/feature improvement into a model rather than baking in routine updates unchecked. Code:
`src/models/` (`matrix.py`, `benchmark.py`, `governance.py`, `routes.py`, exposed at `/models`,
mounted in `api.py`).

*(The remainder of the original CLAUDE.md content follows unchanged. It remains useful session guidance but is no longer the authoritative source.)*

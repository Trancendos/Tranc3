# Production Readiness Roadmap

**Target:** Self-hosted, zero-cost Trancendos stack with editable governance names and merge-clean `main`.

## Phase 0 — Immediate (this week)

| # | Action | Owner | Done when |
|---|---|---|---|
| 0.1 | Merge `cursor/production-readiness-consolidation-6d5c` → `main` | Agent/CI | CI green on main |
| 0.2 | Close PRs #84–89 as superseded | Human | PRs closed with link to merge commit |
| 0.3 | Set prod secrets on Citadel | Ops | `api.py` starts, health 200 |
| 0.4 | Run UAT compose + seed | Ops | `scripts/seed_uat_data.py` exits 0 |
| 0.5 | Fix wrong names via Admin UI | You | Syntax-Sage shows as T4 Agent, etc. |

## Phase 1 — Governance & names (1–2 sprints)

| # | Action |
|---|---|
| 1.1 | Wire `effective.resolve_entity()` into worker `/health` and gateway |
| 1.2 | Pytest: entity rename, tier assign, reset overrides |
| 1.3 | Standardize MacIntyre + Guardian title in `platform.py` |
| 1.4 | Regenerate `src/config/id_registry.json` from platform.py |
| 1.5 | Deprecate `docs/architecture/master-schema.md` generic names |

## Phase 2 — Infinity routing (hub-and-spoke)

| # | Action |
|---|---|
| 2.1 | Enforce Portal → Gate → Infinity → Location in portal worker |
| 2.2 | Role routes: user→Arcadia, devops→Citadel, admin→Infinity-Admin |
| 2.3 | Document routing in `docs/INFINITY_ECOSYSTEM_MATRIX.md` (done) |
| 2.4 | E2E tests for three personas |

## Phase 3 — Proactive automation ($0)

| # | Action |
|---|---|
| 3.1 | Add `deploy/ansible/` playbooks (Ansible Core) |
| 3.2 | YAML swarm manifests → `cron-service` / queue-service |
| 3.3 | `make health` in CI post-deploy (script exists) |
| 3.4 | Renovate + dependency-scanner on main |

## Phase 4 — Decommission legacy

| # | Action |
|---|---|
| 4.1 | Route `api.trancendos.com` via Traefik only |
| 4.2 | Retire CF workers per `CF_WORKER_MIGRATION_ROADMAP.md` |
| 4.3 | Segment Tranc3 into location repos when templates stable |

## Phase 5 — Tranc3 completion & split

| # | Action |
|---|---|
| 5.1 | Tranc3 Tier-3 AI base complete (`tranc3_base.py`) |
| 5.2 | Freedom-of-movement routing for AIs (not hub-bound) |
| 5.3 | Hub power-ups when AI co-located with location |
| 5.4 | Extract locations to dedicated repos |

---

## Auto-merge policy

You approved: **merge when tests pass**. Recommended CI gate on consolidation PR:

```bash
pytest tests/test_smoke.py tests/test_knowledge_brain.py tests/test_canonical_routes.py \
  tests/test_gbrain_worker.py tests/test_compatibility.py -q
```

Full `make test` optional for nightly; fast gate for merge.

---

## Design system

See `docs/DESIGN_SYSTEM.md` + tier templates in `src/entities/templates/`.

| Template class | Tier | File |
|---|---|---|
| Trance-One | 1 Orchestrator | `trance_one_base.py` |
| T2ance | 2 Prime | `t2ance_base.py` |
| Tranc3 | 3 AI | `tranc3_base.py` |
| Infinity-Agent | 4 Agent | `infinity_agent_base.py` |
| Infinity-Bot | 5 Bot | `infinity_bot_base.py` |

Use these to spawn new entities without duplicating boilerplate.

# Integration scope plan: `cursor/production-integration-8d67`

**Regenerate:** `make integration-plan` → `logs/integration_scope_cursor_production-integration-8d67_latest.md`

## Verdict

Do **not** bulk-merge. This branch deletes 41 files under `shared_core/` and would regress encrypted SQLite auth, zero-cost env defaults, and proactive orchestration. Integrate only via scoped cherry-picks after review.

**Diff summary (vs `main`):** 117 files | +13 / ~63 / −41

## Recommended PR order (scoped)

| Priority | Scope | Action |
|----------|-------|--------|
| 1 | `workers/` (+10 Dockerfiles/requirements) | Cherry-pick per worker; verify healthchecks still use `curl` if Dockerfile removes it |
| 2 | `tests/` | Port only with matching worker/src changes |
| 3 | `Dimensional/` | Medium risk — run targeted tests (`test_sentinel_cluster`, raft, hive) |
| 4 | `src/` | Small mods — review entity templates and error catalog |
| 5 | `web/` | UX/a11y as separate Arcadia PR |
| 6 | `monitoring/`, `scripts/` | Safe if additive |
| ⛔ | `shared_core/` | **Block** — 41 deletions |
| ⛔ | `aeonmind/` | **Block** — polyglot surface; separate program |
| ⛔ | `.env.example` | **Block** — weakens SECRET_KEY / zero-cost guidance on branch tip |

## Automation

- Weekly Forgejo: `.forgejo/workflows/integration-scope-plan.yml`
- Manual: `python3 scripts/integration_scope_plan.py --branch <name>`

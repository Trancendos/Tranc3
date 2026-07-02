# Merge strategy (Tranc3 / Trancendos)

Phased plan for integrating deferred branches without regressing `main`. **Never bulk-merge branches with mass deletions.**

## Golden rules

1. **Additive cherry-picks only** — prefer scoped PRs over merging integration branches whole.
2. **Block `shared_core/` deletions** until `refactor/shared-core-to-dimensional` is ported incrementally.
3. **Reject dependency downgrades** — no `>=` loosening where `main` uses `==` pins; no removal of sqlalchemy, alembic, bcrypt, pyotp, psycopg2 without explicit review.
4. **Preserve observability** — do not replace `monitoring/prometheus.yml` wholesale; extend scrape jobs in place.
5. **Verify against `docker-compose.production.yml`** — service names and ports on `main` win over stale integration branches.

## Phase 0 — Complete (on `main`)

| Item | Status |
|------|--------|
| CWE-117 log injection (#116) | Merged |
| Torch import-time fixes (#118) | Merged |
| Notifications webhook SSRF (#119) | Merged |
| API startup readiness (`validate_startup`, `/ready` 503) | On `main` |
| P3 worker Dockerfiles (8030–8038) | On `main` |

## Phase 1 — Observability gaps (in progress)

| PR / branch | Scope | Notes |
|-------------|-------|-------|
| `cursor/integration-p3-prometheus-e51c` | P3 Prometheus scrape + blackbox health probes | `turings-hub-service:8035`, `mlflow-service:8039`, `sentinel-station-service:8041` |

**Do not cherry-pick** `4259fc7` from `cursor/production-integration-8d67` whole — it strips VictoriaMetrics, Tempo, SigNoz, KrakenD, Qdrant, and weakens `requirements.txt`.

## Phase 2 — Housekeeping

- Close superseded PR **#117** (`claude/loving-mendel-dPsZ7`) manually — landed via #118 + #119.
- Delete stale remotes with 1–5 unique commits (not eligible for `stale-branch-cleanup`):
  - `cursor/production-readiness-*` (all variants)
  - `cursor/production-ready-3c86`
  - `palette-add-empty-state-prompts-*` (if content on `main`)
  - `cursor/api-startup-readiness-c17e` (if 0-ahead after verify)
- Re-run CodeQL on `main`; dismiss per `docs/SECURITY_ALERT_DISMISSALS.md`.

## Phase 3 — Scoped integration (`production-integration-8d67`)

Use `make integration-plan` → `logs/integration_scope_cursor_production-integration-8d67_latest.md`.

| Bucket | Action |
|--------|--------|
| Observability / Prometheus | Phase 1 only (additive) |
| Worker requirements pins | Reject loosening |
| `shared_core/` removals | Block |
| New `Dimensional/` modules | Cherry-pick file-by-file from `refactor/shared-core-to-dimensional` |

## Phase 4 — Archive (no merge to `main`)

| Branch | Reason |
|--------|--------|
| `phase-24/aeonmind-polyglot-v0.9.0` | +56k lines; separate program |
| `infra/phase16-adaptive-storage` | ~157k deletions |
| `security/dependabot-remediation-critical` | Conflicts with `SECURITY.md` |
| `merge/aeonmind-into-main` | Experimental; mass deletion |

## Automation

```bash
make branch-audit              # ahead/merged report
make stale-branch-cleanup      # dry-run delete 0-ahead remotes
make integration-plan          # scoped breakdown for integration branch
python3 scripts/pr_hygiene.py  # superseded PR suggestions
```

## Operator checklist before any merge

1. `git log main..<branch> --oneline` — count unique commits.
2. `git diff main...<branch> --stat` — flag deletions > 500 lines or `shared_core/`.
3. Run targeted tests for touched paths (`pytest tests/test_workers_p3.py -v` for P3 workers).
4. Open **draft** PR with explicit “additive only” note in description.

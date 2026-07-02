# Branch integration report (Tranc3 / Trancendos)

**Policy:** Integrate only zero-cost, reviewable changes. Block mass-deletion branches.

## Integrated on `main` (this pass)

| Source branch | What landed |
|---------------|-------------|
| `cursor/api-startup-readiness-c17e` | `validate_startup()` in `api.py`, `_bootstrap_complete` + `/ready` 503 until boot |
| `cursor/production-readiness-stack-065b` | Vault file storage, `tranc3-backend` in compose, API gateway upstream wiring |
| `cursor/zero-cost-adaptive-admin-os-6d5c` | (prior) Adaptive rotator, Admin OS, proactive orchestrator |
| `cursor/production-entity-swarm-6d5c` | (prior) Entity overrides DB, swarm coordinator |
| `jules-*` | Cosine similarity optimizations (already present on main) |
| `palette-aria-*` | ChatView `aria-label` (already present on main) |
| `a7b72c2` (cherry-pick) | `conftest.py` worker SQLite paths, `pyotp` test dep, JWT error split in auth gateway |
| `4efcbf6` (security) | Full GitHub Security tab remediation on `main` |
| PR #116 | CWE-117 log injection (`sanitize_for_log` / `SafeLogger`) |
| PR #118 | Torch import-time crash fixes (supersedes #117 torch portions) |
| PR #119 | Notifications webhook SSRF hardening (`WEBHOOK_ALLOWED_DOMAINS`, `HTTPSConnection`) |

## In flight

| Branch | Scope |
|--------|-------|
| `cursor/integration-p3-prometheus-e51c` | Additive P3 Prometheus scrape jobs (8016–8039) + blackbox health probes; see `docs/MERGE_STRATEGY.md` |

## Superseded — close / delete manually

| Ref | Action |
|-----|--------|
| PR #117 (`claude/loving-mendel-dPsZ7`) | Close — superseded by #118 + #119 |
| `cursor/production-readiness-*` (8 branches) | Delete remote after review — all ~305 commits behind `main`, 1–5 unique commits each |
| `cursor/torch-import-fixes-e51c`, `cursor/security-alerts-*` | Already deleted (merged squash residue) |

## Merged remote refs (0 commits ahead — delete candidates)

Run `make stale-branch-cleanup` for the live list. Typical candidates (verify before `--apply`):

- `cursor/security-codeql-remediation-e51c`, `cursor/consolidate-open-prs-e51c`
- `feat/phase20-*`, `feat/phase22-*`, `feat/phase28-*`
- `claude/fix-*`, `cursor/windows-*`, `palette-spark-dashboard-a11y-*`

Protected from auto-delete: `cursor/production-integration-*`, `claude/loving-mendel-*`, `phase-24/*`.

## Blocked — do not blind merge

| Branch | Risk |
|--------|------|
| `merge/aeonmind-into-main` | ~23k deletions, experimental protocols |
| `phase-24/aeonmind-polyglot-v0.9.0` | +56k lines, polyglot stack |
| `refactor/shared-core-to-dimensional` | Massive dimensional refactor |
| `infra/phase16-adaptive-storage` | ~157k deletions |
| `palette-a11y-improvements-*` | ~21k deletions |
| `cursor/production-integration-8d67` | Mixed good fixes + mass `shared_core` removal; **Prometheus top commit regresses main** — cherry-pick observability additively only |

## Review queue (cherry-pick per file)

| Branch | Verdict | Notes |
|--------|---------|-------|
| `claude/loving-mendel-dPsZ7` | review | PR #84 — async KnowledgeBrain, RBAC pieces |
| `merge/phase16-into-main` | review | OpenBao client, optional Oracle paths |
| `cursor/production-readiness-ci-fixes-2277` | review | conftest / knowledge brain CI |
| `fix/go-grpc-security-81` | cherry-pick | Go proto + golangci if aeonmind used |

## Automation

- `make branch-audit` → `logs/branch_benefit_audit_latest.md` (ahead + merged sections)
- `make stale-branch-cleanup` / `make stale-branch-cleanup-apply` → delete 0-ahead remote refs
- `make integration-plan` → scoped PR plan for `cursor/production-integration-8d67`
- `make fork-audit` → `logs/fork_audit_latest.md` (requires `gh auth`)
- `make pr-audit` → open PR readiness (requires `gh auth`)
- `python3 scripts/citadel_preflight.py` — pre-deploy gate
- `python3 scripts/pr_hygiene.py [--apply]` — close superseded PRs #84–89
- `config/swarm/manifests/citadel-deploy.yaml` — swarm preflight bundle
- Forgejo weekly: `branch-integration-audit.yml`, `pr-readiness-audit.yml`, `stale-branch-cleanup.yml`, `fork-audit.yml`, `integration-scope-plan.yml`, `citadel-preflight.yml`

See `logs/integration_scope_cursor_production-integration-8d67_latest.md` for the scoped breakdown of the large integration branch.

## External repos / forks

This workspace is **Trancendos/Tranc3**. Related work may exist in:

- **infinity-adminOS** (TypeScript) — mapped in `CROSS_REPO_SYNERGY.md`; Python ports live under `src/mesh/`, `src/event_bus/`, `src/ai_gateway/`
- **Cloudflare Workers** (`cloudflare/*`) — migrating to `workers/*` per `CF_WORKER_MIGRATION_ROADMAP.md`

Fork state is **not** inferable from git alone. Run `make fork-audit` (or weekly Forgejo `fork-audit.yml`) and review `logs/fork_audit_latest.md`. Forks are never auto-merged into `main`.

## Citadel deploy (operator)

```bash
cp .env.production.example .env.production   # fill from Vault
python3 scripts/citadel_preflight.py
make deploy-citadel
```

Optional free-tier AI keys (off by default): `GROQ_API_KEY`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, `SAMBANOVA_API_KEY` in `config/zero_cost/providers.yaml`.

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

## Blocked — do not blind merge

| Branch | Risk |
|--------|------|
| `merge/aeonmind-into-main` | ~23k deletions, experimental protocols |
| `phase-24/aeonmind-polyglot-v0.9.0` | +56k lines, polyglot stack |
| `refactor/shared-core-to-dimensional` | Massive dimensional refactor |
| `infra/phase16-adaptive-storage` | ~157k deletions |
| `palette-a11y-improvements-*` | ~21k deletions |
| `cursor/production-integration-8d67` | Mixed good fixes + mass `shared_core` removal |

## Review queue (cherry-pick per file)

| Branch | Verdict | Notes |
|--------|---------|-------|
| `claude/loving-mendel-dPsZ7` | review | PR #84 — async KnowledgeBrain, RBAC pieces |
| `merge/phase16-into-main` | review | OpenBao client, optional Oracle paths |
| `cursor/production-readiness-ci-fixes-2277` | review | conftest / knowledge brain CI |
| `fix/go-grpc-security-81` | cherry-pick | Go proto + golangci if aeonmind used |

## Automation

- `python3 scripts/branch_benefit_audit.py` → `logs/branch_benefit_audit_latest.md`
- `python3 scripts/citadel_preflight.py` — pre-deploy gate
- `python3 scripts/pr_hygiene.py [--apply]` — close superseded PRs #84–89
- `config/swarm/manifests/citadel-deploy.yaml` — swarm preflight bundle
- Forgejo: `.forgejo/workflows/citadel-preflight.yml`, `branch-integration-audit.yml`

## External repos / forks

This workspace is **Trancendos/Tranc3**. Related work may exist in:

- **infinity-adminOS** (TypeScript) — mapped in `CROSS_REPO_SYNERGY.md`; Python ports live under `src/mesh/`, `src/event_bus/`, `src/ai_gateway/`
- **Cloudflare Workers** (`cloudflare/*`) — migrating to `workers/*` per `CF_WORKER_MIGRATION_ROADMAP.md`

No additional GitHub forks were cloned in-agent; run `branch_benefit_audit.py` after adding remotes.

## Citadel deploy (operator)

```bash
cp .env.production.example .env.production   # fill from Vault
python3 scripts/citadel_preflight.py
make deploy-citadel
```

Optional free-tier AI keys (off by default): `GROQ_API_KEY`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, `SAMBANOVA_API_KEY` in `config/zero_cost/providers.yaml`.

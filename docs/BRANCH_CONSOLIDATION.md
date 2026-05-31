# Branch consolidation (May 2026)

This document records what was merged into `main`, which open PRs were superseded, and how to clean up GitHub after consolidation.

**Canonical production branch:** `main` @ `d2bffcd` or later.

## What is on `main` now

| Area | Status |
|------|--------|
| **CLOUD_ONLY default** | `PLATFORM_INFRA_MODE=CLOUD_ONLY` in `config/platform/infrastructure_mode.yaml` |
| **Cloud auto-rotation** | `src/adaptive/cloud_rotation_loop.py` + rotator chain `zero_cost_cloud` |
| **Proactive orchestrator** | `src/adaptive/proactive_orchestrator.py` (API lifespan) |
| **Adaptive API** | `GET/POST /adaptive/mode`, `GET /adaptive/status` |
| **Citadel deploy** | `scripts/citadel_deploy_all.py` — skips Docker in CLOUD_ONLY unless `--local` |
| **P0 production stack** | Metrics, health blocks, `pre_deploy_quality_gate`, forensic docs |
| **MicroCeph shim** | `shared_core/architecture/microceph_provider.py` re-exports (cherry-picked) |
| **Ecosystem mode** | `api_ecosystem.py` / `src/routers/ecosystem.py` map `LOCAL_ONLY` → `TRUE_NAS` |

See also: [PLATFORM_INFRASTRUCTURE_MODE.md](./PLATFORM_INFRASTRUCTURE_MODE.md).

## Merged commits (consolidation wave)

```
db2ba96+ fix(lint): cherry-pick PR #84/#88 ruff + format (3f68e45, 4715c17) — CI clean
d2bffcd feat(platform): align ecosystem SYSTEM_MODE with PLATFORM_INFRA_MODE
b24456d fix(shared_core): re-export MicroCeph constants from shim
a8484cb fix(platform): restore CLOUD_ONLY default and cloud auto-rotation
42986ff feat(deploy): single citadel_deploy_all script for Windows/Linux
```

### PR tip commits applied to `main` (May 2026 follow-up)

| Source | Applied |
|--------|---------|
| #84 `3f68e45` | Worker unused imports, B027 hooks on entity templates |
| #84 `4f2b136` / `b24456d` | MicroCeph shim re-exports (already on main) |
| #88 `4715c17` | Ruff format on gateway/entities/protocols; health_check alignment; A2A `ABC` transport |
| #84 `821af4c` | Skipped (conflicted with `lead_tier` on `effective.py` — kept main behaviour) |
| #84 `707e99f` | Skipped (auto-generated `.security_learning/` scanner noise only) |
| #86 full merge | **Not applied** (would revert production stack; `aeonmind/` already on main) |
| #89 palette UX | Already on main (`d84c0a7`, `ChatView` empty prompts) |

Earlier `main` already included production readiness, adaptive rotation (70110bf), phase16 merge (9adf306), and related work — do not re-merge old PR branches on top of this.

## Open PRs — close without merging

These five PRs were **left open** because their branch tips predate current `main`. Merging them would **revert** Citadel deploy, adaptive systems, production gates, and worker Dockerfiles.

| PR | Branch | Action | Reason |
|----|--------|--------|--------|
| [#84](https://github.com/Trancendos/Tranc3/pull/84) | `claude/loving-mendel-dPsZ7` | **Close** | MicroCeph fix cherry-picked (`b24456d`); rest regresses `main` |
| [#86](https://github.com/Trancendos/Tranc3/pull/86) | `merge/aeonmind-into-main` | **Close** | ~6k+ line revert vs current production stack |
| [#87](https://github.com/Trancendos/Tranc3/pull/87) | `merge/phase16-into-main` | **Close** | Phase16 storage already on `main` (`9adf306`) |
| [#88](https://github.com/Trancendos/Tranc3/pull/88) | `merge/phase24-platform` | **Close** | Adaptive/production work superseded by `main` |
| [#89](https://github.com/Trancendos/Tranc3/pull/89) | `palette-add-empty-state-prompts-...` | **Close** | Empty-state commit already on `main` (`d84c0a7`) |

### Close PRs in GitHub UI

1. Open each PR → **Close pull request** (do not merge).
2. Optional comment: *Superseded by main @ d2bffcd — see docs/BRANCH_CONSOLIDATION.md.*

Or with CLI (requires `gh` auth with repo write):

```bash
gh pr close 84 86 87 88 89
```

## Remote branches deleted (consolidation agent)

Already removed from `origin`:

- `cursor/restore-cloud-only-adaptive-6d5c`
- `cursor/forensic-p0-review-6d5c`
- `cursor/proactive-automation-6d5c`
- `cursor/production-readiness-consolidation-6d5c`
- `cursor/production-entity-swarm-6d5c`

## Optional branch cleanup (after closing PRs)

Delete stale heads that are fully superseded (only if you no longer need the branch name):

```bash
git fetch origin --prune

git push origin --delete \
  claude/loving-mendel-dPsZ7 \
  merge/phase24-platform \
  merge/phase16-into-main \
  merge/aeonmind-into-main \
  palette-add-empty-state-prompts-4011591944121060762
```

**Do not delete** `main` or active feature branches you are still developing.

Many `cursor/production-readiness-*` branches may still exist on the remote; most have **no open PR**. Delete only after confirming `git branch -r --merged origin/main` contains them.

## Modes (reminder)

| Mode | When |
|------|------|
| `CLOUD_ONLY` | **Now** — CF/Fly/Supabase + cloud AI rotation |
| `HYBRID` | Migration; `CITADEL_LOCAL_STACK=true` for compose |
| `LOCAL_ONLY` | Citadel ready → `citadel_deploy_all.py --local` |

## Re-opening work safely

If you still need AeonMind, phase24 CVE work, or other large features from closed PRs:

1. `git checkout main && git pull`
2. Create a **new** branch from current `main`.
3. Cherry-pick **individual commits** (not whole stale branches).
4. Run `python scripts/pre_deploy_quality_gate.py` before opening a new PR.

## Verify after cleanup

```bash
git checkout main && git pull
python scripts/pre_deploy_quality_gate.py
pytest tests/test_infrastructure_mode.py tests/test_adaptive_rotator.py -q
curl -s http://localhost:8000/adaptive/mode   # when API is running
```

Expected `mode`: `CLOUD_ONLY`, `cloud_auto_rotate`: `true`.

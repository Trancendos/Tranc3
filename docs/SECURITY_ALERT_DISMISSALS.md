# Security Alert Dismissals (Tier 0)

Documented false positives and intentional suppressions on `main`. Rescan after merge
to bulk-close stale GitHub Security alerts.

## Trivy / Kubernetes (Flux)

| Alert | Check | Disposition | Mitigation |
|-------|-------|-------------|------------|
| #2450 | KSV118 Tiller deployed | False positive | `fmd-distiller` is not Helm Tiller; skip on pod template in `flux/base/deployments.yaml` |
| #2476–#2451 | KSV013 untrusted registry | Accepted risk | Self-hosted Forgejo (`forgejo.local`); skip on all nanoservice pod templates in both Flux trees |
| #1513–#1515 | KSV104 ConfigMap sensitive content | False positive | ConfigMaps hold non-secret env keys only (LOG_LEVEL, URLs); metadata skip on ConfigMaps |

## Dependencies

| Alert | CVE / package | Disposition | Mitigation |
|-------|---------------|-------------|------------|
| #1 (sentencepiece) | sentencepiece CVE-2026-1260 | Fixed | Pinned `sentencepiece==0.2.1`; listed in `.trivyignore` |
| #41, #42 | chromadb GHSA-f4j7-r4q5-qw2c / CVE-2026-45829 | Fixed | Removed from `requirements-ai.txt`; embedded client + in-memory fallback only |
| #45 | torch PYSEC-2025-194 (`torch.jit.script`) | Risk accepted | JIT never used; `torch==2.12.0` is latest PyPI |

## Secret scanning

| Alert | Location | Disposition | Mitigation |
|-------|----------|-------------|------------|
| #1 (Supabase) | `deploy/forgejo/set-org-secrets.sh` (historical) | Fixed | Commit `2375429` — env vars only; **rotate `SUPABASE_SERVICE_ROLE_KEY` in Supabase dashboard** (key was in git history and may have been exposed) |

## CodeQL Notes (deferred paths)

**Addressed (PR follow-up on `cursor/codeql-deferred-cleanup-e51c`):**

- Empty-except (`except: pass`) in `shared_core/`, `Dimensional/`, and `archive/` — replaced with
  `logger.debug("suppressed %s", _exc, exc_info=False)` via `scripts/fix_empty_except_pass.py`
  (~157 handlers across 56 files). Intentional null-stub `pass` in `_Null*` classes unchanged.
- Cyclic-import Notes in `shared_core/` and `Dimensional/` — barrel re-exports and lazy optional
  imports annotated with `# codeql[py/cyclic-import]` (same pattern as live `src/mcp/` and
  `src/workflow/`). Scope: package `__init__.py` barrels, infinity worker kit, proactive wiring,
  service bus, auth middleware, and sentinel vault checks.

**Still deferred (structural / low priority):**

- `archive/` — legacy, not deployed; empty-except fixed for consistency only

## Live-path fixes (this branch)

- P1 #1137: ZFS TOCTOU — atomic open+stat in `tranc3-ts/src/providers/ZFSProvider.ts`
- P1/P2B: Exception exposure — `safe_error_detail()` in live workers and `src/routers/*`
- P2A: Log injection — `sanitize_for_log()` in `src/core/config.py`, `src/mcp/server.py`
- P3: Pod `runAsUser`/`runAsGroup`/`fsGroup` 65534 in both Flux deployment trees
- CodeQL Notes: `NotImplementedError`, explicit returns, narrowed except in live `src/` paths

## Post-merge checklist (`main` @ `7826f48`, 2026-06-11)

Consolidated on `main` via PRs #108–#112 (live-path CodeQL, dependabot, torch optional imports,
deferred-tree empty-except + cyclic-import suppressions). CI on latest merges: Ruff, Pytest,
CodeQL, and Trivy workflow scans passed.

### 1. Rescan Security tab (manual — token lacks `security_events` / `actions` write)

Cloud agent cannot list or dismiss alerts (`403 Resource not accessible by integration`) or
dispatch workflow runs. In the GitHub UI:

1. Open **GitHub → Trancendos/Tranc3 → Security**
2. **Actions → CodeQL Advanced**, **Trivy Security Scan**, **Security Gate** → **Run workflow** on `main`
   (or push an empty commit to `main` to trigger push workflows)
3. Filter **Code scanning** → severity **Error** → confirm live worker/router paths no longer appear

### 2. Bulk-close stale Trivy K8s alerts

For each alert in the tables above, open the alert → **Close as** → choose:

| Alert ID(s) | Disposition | Close reason (paste into GitHub) |
|-------------|-------------|--------------------------------|
| #2450 | False positive | KSV118: `fmd-distiller` pod name contains substring "tiller"; not Helm Tiller. Skip in `flux/base/deployments.yaml` annotations. |
| #2476–#2451 | Risk accepted | KSV013: self-hosted Forgejo registry (`forgejo.local`); intentional for zero-cost stack. Skips on nanoservice pod templates in both Flux trees. |
| #1513–#1515 | False positive | KSV104: ConfigMaps hold non-secret env keys only (LOG_LEVEL, URLs); metadata skip on ConfigMaps. |
| #1 (sentencepiece) | Fixed | sentencepiece CVE-2026-1260: pinned `sentencepiece==0.2.1` in `requirements.txt` + `.trivyignore`. |
| #41, #42 | Fixed | chromadb GHSA-f4j7-r4q5-qw2c: removed from `requirements-ai.txt`; optional embedded client only; see `SECURITY.md`. |
| #45 | Risk accepted | torch PYSEC-2025-194: `torch.jit.script` never used; `torch==2.12.0` latest PyPI. |
| #1 (Supabase) | Revoked | After rotating `SUPABASE_SERVICE_ROLE_KEY` in Supabase; script fixed in `2375429`; see `docs/credential-rotation-advisory.md`. |

### 3. External check failures (no repo action)

- **CodeSlick Security** — monthly analysis quota exhausted; re-enable when quota resets
- **Standalone Trivy** status check — external app; Trivy **workflow** scans pass on `main`

### 4. Stale remote branch cleanup (2026-06-11)

**Deleted** (16 branches — all had merged PRs, no open PRs):

`claude/loving-mendel-dPsZ7`, `claude/security-fixes-post-102`, `claude/torch-optional-import`,
`claude/torch-optional-remaining`, `cursor/codeql-deferred-cleanup-e51c`,
`cursor/security-codeql-remediation-e51c`, `fix/go-grpc-security-81`,
`infra/phase16-adaptive-storage-v2`, `jules-3517920969573178146-463dd9dd`,
`jules-palette-a11y-dashboard-5068055496884495727`,
`palette-a11y-improvements-12605502358406383526`, `palette-aria-labels-2309680963122305268`,
`palette-ux-aria-labels-5045932787340505675`, `palette-ux-dashboard-a11y-1760855168706661139`,
`palette-ux-improvements-12278857656879242599`, `🎨-palette-ux-improvement-16883467493237960093`

**Retained** (17 branches — no merged PR or superseded work still unreviewed):

`cursor/production-integration-8d67` (33 commits ahead), `phase-24/aeonmind-polyglot-v0.9.0`,
`refactor/shared-core-to-dimensional`, `security/dependabot-remediation-critical` (content on
`main` via PR #105 from `cursor/security-dependabot-remediation-e51c`), palette/production-readiness
cursor branches, etc. Delete manually after confirming no unique commits are needed.

### 5. `claude/loving-mendel-dPsZ7` — cherry-pick not needed

PR #63 merged 2026-05-26; branch had 17 post-merge commits (CodeQL SQL allowlist, rate-limit dedup,
master-worker). **All targeted security fixes are already on `main`** via PRs #108–#111:

- `workers/identity-service/worker.py` — `_VALID_COLUMNS` allowlist
- `workers/rate-limit-service/worker.py` — single `_INTERNAL_SECRET` / `_router` definition
- `src/mcp/tools.py`, `src/workflow/nodes.py`, `workers/the-grid/worker.py` — `lgtm[py/unsafe-*]` suppressions

Merging the branch tip would **regress** live-path hardening (`sanitize_for_log`, path validation,
optional torch, encrypted SQLite). Branch deleted after verification; no dedicated cherry-pick PR.

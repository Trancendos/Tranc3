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
| #1 | sentencepiece CVE-2026-1260 | Fixed | Pinned `sentencepiece==0.2.1`; listed in `.trivyignore` |

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

## Post-merge checklist (`main` @ `2c007066`, 2026-06-11)

Merged via PR #108. CI on merge: Ruff, Pytest, CodeQL, and Trivy workflow scans passed.

### 1. Rescan Security tab

1. Open **GitHub → Trancendos/Tranc3 → Security**
2. Trigger or wait for CodeQL + Dependabot + Trivy rescans on `main`
3. Filter **Code scanning** → severity **Error** → confirm live worker/router paths no longer appear

### 2. Bulk-close stale Trivy K8s alerts

For each alert in the table above, open the alert → **Close as** → choose:

| Disposition | Close reason |
|-------------|--------------|
| False positive | KSV118 Tiller / KSV104 ConfigMap (mitigation in Flux annotations) |
| Risk accepted | KSV013 untrusted registry (self-hosted Forgejo) |
| Fixed | sentencepiece CVE (pinned in requirements) |

### 3. External check failures (no repo action)

- **CodeSlick Security** — monthly analysis quota exhausted; re-enable when quota resets
- **Standalone Trivy** status check — external app; Trivy **workflow** scans pass on `main`

### 4. Follow-up branch (optional)

- **Done:** bulk empty-except + cyclic-import suppressions in `shared_core/` and `Dimensional/`
  (PR `cursor/codeql-deferred-cleanup-e51c`)
- **After merge:** rescan Security tab; bulk-close stale alerts per checklist above

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

**Unused-import Notes (CodeQL `py/unused-import`, branch `cursor/codeql-unused-imports-e51c`):**

| Alert ID(s) | File | Fix |
|-------------|------|-----|
| #2562, #1827, #1828 | `shared_core/liquid/ltc_router.py` | Probe via `importlib.util.find_spec` instead of importing `torch`/`ncps` at module load |
| #2560, #2561 | `*/infinity/worker_integration.py` | `# codeql[py/unused-import]` on re-exported `InfinityHealthOrchestrator` |
| #2558–#2559 | `*/infinity/proactive_defense.py` | Removed unused `FirewallAction`, `ThreatLevel` optional imports |
| #2546–#2551, #2552–#2557 | `*/infinity/adaptive_intelligence.py` | Dropped unused optional symbols (`PulseMode`, `Anomaly`, `RepairStrategy`, `ReactiveState`, `ProbabilityVector`, `ThreatLevel`) |
| #1021, #1458 | `*/infinity/fluidic_gateway.py` | Removed unused `_global_causal_bus` import |
| #2478 | `Dimensional/path_validation.py` | Removed unused `Iterator` |
| #2409 | `api.py` | Removed unused `CapacityExceededError` import |
| #2331, #2328 | `Dimensional/hive/hive_core.py`, `bridge/bridge_core.py` | Removed unused `sqlite3` (uses `sqlite3_connect` helper) |
| #2172, #2118 | `shared_core/architecture/*_provider.py` | `# codeql[py/unused-import]` on barrel re-exports |
| #2149 | `src/event_bus/bus.py` | Import only `_event_type_to_subject` (not `NATSTransport`) |
| #958 | `src/neural/attention_router.py` | Removed dead numpy probe (`_HAS_NUMPY` never read) |
| #2332, #1897 | `src/personality/lnn.py`, `src/skills/code_generator.py` | Already valid / suppressed — close after rescan |

**Still deferred (structural / low priority):**

- `archive/` — legacy, not deployed; empty-except fixed for consistency only

## CodeQL CWE-209 — Information exposure through an exception

**Branch:** `cursor/codeql-exception-exposure-e51c`

**Pattern:** `log_server_error(exc, status_code, context=...)` in `Dimensional/error_handlers.py`
and `shared_core/error_handlers.py` logs the real exception server-side and returns static
client messages (never embeds `str(exc)`), satisfying CodeQL `py/exception-information-leakage`.

| Alert ID(s) | File | Fix |
|-------------|------|-----|
| #2492 | `src/routers/ecosystem.py:715` | Already static; sibling routes migrated to `log_server_error` |
| #2367, #2366, #2365 | `archive/api_enhanced.py` | `safe_error_detail` → `log_server_error`; no `result["error"]` passthrough |
| #2363, #2362 | `archive/api_ecosystem.py` | `str(e)` / `detail=str(e)` → `log_server_error` |
| #2135, #2134 | `workers/blender-worker/worker.py` | `_blender_response_body()` — stderr logged server-side only |
| #2133–#2129 | `workers/triposr-worker/worker.py` | All `/reconstruct` error paths use `log_server_error` |
| #2092 | `workers/health-aggregator/worker.py` | `_check_one` details use static message via `log_server_error` |
| #2065 | `src/routers/enhanced_capabilities.py` | All capability handlers use `log_server_error` |
| #839 | `workers/notifications/worker.py` | SSRF + dispatch failures use static messages |
| #346 | `workers/monitoring/worker.py` | `collect_health` unhealthy metadata via `log_server_error` |
| #550, #549, #548, #27 | `src/nexus/routes.py` | Publish/send/inference handlers |
| #345, #344 | `src/quantum/routes.py` | Quantum route handlers |
| #343, #342 | `src/bio_neural/routes.py` | Consciousness/neuromorphic handlers |
| #341 | `src/workflow/routes.py` | `run_workflow` handler |
| #336–#340 | `src/personality/turingshub/routes.py` | Personality spawn/list/matrix handlers |

**Post-merge:** Run CodeQL on `main` and close the above alerts after rescan confirms clearance.

## CodeQL CWE-117 — Log injection (`py/log-injection`)

**Branch:** `cursor/codeql-log-injection-e51c`

**Pattern:** User-controlled or external values (exceptions, stderr, workflow IDs, usernames,
URLs, client metadata) must not flow into log format strings via f-strings or `str.format`.
Use `%`-style logging with `sanitize_for_log(value)` from `Dimensional/sanitize.py` (or
`shared_core/sanitize.py` under `shared_core/`). Central handlers
`log_server_error()` in `Dimensional/error_handlers.py` and `shared_core/error_handlers.py`
sanitize `context`, exception type, and message before writing.

**Tooling (safe to keep):** `scripts/remediate_cwe117.py` (targeted replacements),
`scripts/remediate_cwe117_libcst.py` (libcst codemod for `logger.*` positional args).
Do **not** use `scripts/remediate_cwe117_ast.py` (`ast.unparse` corrupts formatting).

| Alert ID(s) | File | Fix |
|-------------|------|-----|
| #2578, #2577, #2573, #2572, #2136 | `workers/blender-worker/worker.py` | `sanitize_for_log` on returncode, stderr, scene paths |
| #2576, #2227 | `src/workflow/routes.py`, `src/workflow/executor.py` | Workflow ID + exception in `%s` logs |
| #2571 | `Dimensional/error_handlers.py` | `log_server_error` ref logging |
| #2570, #2367–#2365 | `archive/api_enhanced.py` | Request metadata + errors |
| #2493, #2483, #2231 | `src/mcp/server.py` | Client/tool identifiers in MCP logs |
| #2491, #2490 | `workers/infinity-one-service/worker.py` | Identity/session fields |
| #2489, #2488, #2487, #1891 | `workers/sentinel-station-service/worker.py`, `Dimensional/infinity/sentinel_station.py` | Threat/event context |
| #2486 | `workers/analytics-service/worker.py` | Query/event parameters |
| #2485, #2484 | `workers/gateway-service/worker.py` | Route/upstream identifiers |
| #2477, #2241–#2236, #541 | `workers/notifications/worker.py` | Channel, recipient, dispatch errors |
| #2406–#2404 | `src/compliance/ai_governance.py` | Policy/model identifiers |
| #2388–#2385 | `workers/users-service/worker.py` | User IDs and auth context |
| #2384, #2383, #2244–#2242, #1002–#1000 | `workers/infinity-auth/worker.py` | Token/session/username fields |
| #2382 | `src/database/vector_store.py` | Namespace/collection IDs |
| #2259 | `t2ance/tier_relay.py` | Relay peer metadata |
| #2258 | `trance_one/sovereign_controller.py` | Controller state |
| #2246, #2245 | `src/master_worker/zero_cost_enforcer.py` | Enforcement targets |
| #2235 | `workers/infinity-ws/worker.py` | WebSocket client info |
| #2234, #877 | `workers/api-gateway/worker.py` | Request path/client |
| #2233 | `src/cryptex/threat_detector.py` | Threat signatures |
| #2230 | `src/observability/routes.py` | *(already on `main`)* metric labels |
| #2229 | `src/library/knowledge_base.py` | Document/query IDs |
| #2228 | `src/nexus/hub.py` | Hub routing context |
| #2226 | `src/resonate/empathy.py` | *(already on `main`)* session fields |
| #2225 | `src/taimra/digital_twin.py` | *(already on `main`)* twin IDs |
| #2143 | `workers/ffmpeg-worker/worker.py` | FFmpeg stderr/args |
| #1890 | `Dimensional/security_automation/defense_engine.py` | Rule/threat context |
| #1889, #1888 | `Dimensional/infinity/abac.py` | ABAC subject/resource |
| #1438–#1436 | `Dimensional/hive/hive_core.py` | Queue/agent identifiers |
| #950 | `src/compliance/magna_carta.py` | *(already on `main`)* |
| #949 | `src/security/ip_protection.py` | IP/asset identifiers |
| #868, #867 | `src/citadel/routes.py` | *(already on `main`)* |
| #866, #865 | `src/artifactory/registry.py` | Artifact names |
| #864 | `src/devocity/portal.py` | Portal resource IDs |
| #863–#860 | `src/observability/observatory.py` | Service/metric labels |
| #859, #858 | `src/apimarket/marketplace.py` | *(already on `main`)* |
| #854 | `src/registry/file_registry.py` | *(already on `main`)* paths |
| #850 | `src/citadel/devops_hub.py` | DevOps action context |
| #847 | `src/lab/code_lab.py` | *(already on `main`)* |
| #387 | `src/chronos/scheduler.py` | *(already on `main`)* job IDs |
| #379 | `src/deepmind/planning.py` | Plan step metadata |
| #365 | `src/auth/db_user_manager.py` | Username/email fields |
| #71, #70 | `src/personality/spawner.py` | Spawn profile names |

**Residual Notes (optional follow-up):** A handful of `logger.debug("… %s", "unknown")` literals
and `exc_info=True`-only calls may still flag until CodeQL rescan; use `sanitize_for_log("unknown")`
or `# codeql[py/log-injection]` only where the value is provably static.

**Post-merge:** Run CodeQL on `main` and bulk-close the above after rescan confirms clearance.

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

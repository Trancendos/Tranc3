# Security Alert Register

Canonical triage for Forgejo/CodeQL/Trivy findings. Status values:

| Status | Meaning |
|--------|---------|
| **FIX** | Code or manifest change required |
| **FP** | False positive — documented with rule/suppression |
| **SUPPRESS** | Known issue with `.trivyignore` / CodeQL note |
| **ACCEPT** | Accepted risk with owner + review date |

Last updated: 2026-09-11

## Critical / High (sample from Forgejo export)

| ID | Source | Finding | Status | Action |
|----|--------|---------|--------|--------|
| #1539 | Trivy/Forgejo | Tiller CVE in `flux/base/deployments.yaml:251` | **FP** | Line 251 is `fmd-distiller` labels, not Tiller. No `tiller` image in repo. |
| #2127 | Dockerfile | `workers/ffmpeg-worker` runs as root | **FIX** | Non-root `tranc3` user added (Phase 1) |
| #1 | Trivy | `sentencepiece` CVE in requirements | **SUPPRESS** | Pinned `0.2.1`; documented in `.trivyignore` |
| #2638 | CodeQL | SSRF in `workers/notifications/worker.py` | **FIX** | `validate_webhook_url()` before `urlopen`; tests in `tests/test_url_validation.py`. Webhook target refusal now includes query containment (SEC-011) |
| #985 | CodeQL | SSRF in `workers/gateway-service/worker.py` | **FP** | Internal `httpx` to workflow service URL from env — not user-controlled fetch |

## Kubernetes (manifest hardening)

| Finding | Location | Status | Action |
|---------|----------|--------|--------|
| Missing `securityContext` | `src/nanoservices/igi_gitops/flux/base/deployments.yaml` | **FIX** | Pod + container hardening aligned with `flux/base/` |
| `hostIPC: true` | NSA broker, SHI gateway, DNF orchestrator (both flux trees) | **ACCEPT** | Required for POSIX shm IPC between nanoservice pods. See `docs/HOSTIPC_RISK_ACCEPTANCE.md` |
| `hostPath` `/dev/shm` | `igi_gitops` deployments | **ACCEPT** | Paired with hostIPC; mitigated by network policies + non-root |
| readOnlyRootFilesystem | Partial coverage | **FIX** | Applied where compatible; writable `/tmp` emptyDir where needed |

## Dependency hygiene

| Item | Status | Notes |
|------|--------|-------|
| `torch` / `sentencepiece` pins | **SUPPRESS** | Torch bootstrap optional; sentencepiece CVE tracked in `.trivyignore` |
| `pip-audit` gate | **WARN** | Logged in Forgejo `security-scan.yml` (`continue-on-error`); local gate matches (warn-only) |
| Framework pins (`fastapi`, `starlette`, `pydantic`, `uvicorn`, `redis`) | **GOVERNED** | Centrally governed via `scripts/align_framework_pins.py`. Both Dependabot and Renovate exclude these packages; `scripts/check_canonical_pin_governance.py` fails CI on drift |

## npm audit (Cloudflare Workers + tranc3-bots)

| Package | CVE / GHSA | Severity | Status | Expiry | Notes |
|---------|------------|----------|--------|--------|-------|
| `esbuild` (transitive via wrangler/miniflare) | GHSA-67mh-4wv8-2f99 | High | **FIX** | — | `overrides.esbuild >= 0.25.0` in all CF `package.json` |
| `ws` (transitive via miniflare) | GHSA-3h5v-q93c-6h6q | High | **FIX** | — | `overrides.ws >= 8.17.1` in all CF `package.json` |
| Dev-only wrangler CLI | remaining highs | High | **SUPPRESS** | 2026-09-14 | Dev dependency only; not shipped to Workers runtime. Re-run `npm audit` after overrides. |

Directories scanned in CI (audit levels per `security-scan.yml`):

| Directory | `--audit-level` |
|-----------|-----------------|
| `cloudflare/tranc3-ai` | moderate |
| `cloudflare/infinity-void` | moderate |
| `cloudflare/trancendos-api-gateway` | high |
| `tranc3-bots` | moderate |

## pip-audit suppressions (OSV)

Tracked in `.osv-scanner.toml` with `reason` + quarterly review per CVE. Reconcile after `pip-audit` on Linux/Python 3.11 in Forgejo CI (`security-scan.yml`, warn-only).

## SAST (Bandit / Semgrep / Ruff)

| Tool | CI scope | Gate | Register notes |
|------|----------|------|------------------|
| **bandit** | `src/`, `api.py`, `workers/infinity-auth`, `workers/infinity-ws`, `workers/api-gateway` | medium+ severity & confidence | `# nosec` only where justified (B104 Docker bind, B108 `/dev/shm`, B310 validated URLs, B102 workflow sandbox). Ceiling tracked in `config/immune/nosec_ceiling.txt` |
| **semgrep** | `src/` only | ERROR severity | Fix or inline `nosemgrep` with rule id |
| **ruff** | `src/`, `api.py` | warn-only (`--exit-zero`) | E501 ignored |

## Trivy / IaC (`.trivyignore`)

Every entry in `.trivyignore` requires a written rationale and a re-check trigger (per PR #1150). `.github/workflows/trivy.yml` runs weekly scheduled suppression freshness checks against OSV.

| CVE | Status | Review | Notes |
|-----|--------|--------|-------|
| CVE-2026-1260 | **ACCEPT** | 2026-09-14 | `sentencepiece==0.2.1` is the patched release; Trivy DB lag — see `.trivyignore`. Re-check: when Trivy stops reporting it, or pin moves below 0.2.1 |
| KSV118 | **FP** | 2027-03-01 | Helm Tiller false positive (pod name `fmd-distiller` contains substring "tiller"). Re-check: when `fmd-distiller` is renamed or Helm Tiller genuinely deployed |

## Forgejo code-scanning export

Run when `FORGEJO_TOKEN` is set (Forgejo UI must show **0 open Critical**):

```bash
export FORGEJO_URL="https://trancendos.com/the-workshop"
export FORGEJO_TOKEN="<token>"
export FORGEJO_REPO="Trancendos/Tranc3"
python scripts/export_forgejo_code_scan_alerts.py --merge
```

Without token: merge latest `logs/forgejo-code-scanning-alerts-*.json` after a manual UI export, or use CI artifact from `security-scan` workflow.

<!-- Forgejo export sections are appended below by export_forgejo_code_scan_alerts.py --merge -->

## Security guard calibration

`.forgejo/workflows/production-gate.yml` and `.github/workflows/production-gate.yml` run targeted mutation testing via `scripts/check_guard_calibration.py`. Each security guard is deleted in turn and its named tests must fail. Guards whose removal keeps the suite green are decorative and block the gate.

## Vulnerability census

Run history tracked in `docs/governance/vulnerability-census-history.jsonl`. Covers Python, npm, Go and Rust surfaces. Census routes findings to owning Locations per `config/estate/location_codes.yaml`.

## Verification commands

```bash
python scripts/security_score.py
python scripts/production_readiness_score.py
python -m pytest tests/test_url_validation.py tests/test_zero_cost_registry.py tests/test_adaptive_rotator.py -q
python scripts/pre_deploy_quality_gate.py
```

## CodeQL Advanced findings (Python)

`.github/workflows/codeql.yml` retains SARIF as a build artifact (30-day retention) so alerts can be read outside the Security tab. CodeQL suppressions require written adjudication; adjudicated path-injection alerts are filtered via `scripts/filter_codeql_alerts.py --strict-surprises`.

**Detailed findings from PR #1150 (SEC-009 through SEC-019) are documented in `SECURITY_ALERT_REGISTER.md` at repository root.** This includes:

- **SEC-009**: 5× `py/path-injection` in `workers/storage-service/worker.py` (fixed: `_contained()` via `safe_join`)
- **SEC-010**: `py/partial-ssrf` 9.1 in `workers/vault-service/worker.py` (fixed: `_vault_path()` path validation)
- **SEC-011**: `py/partial-ssrf` 9.1 in `workers/notifications/worker.py` (fixed: query separator restoration)
- **SEC-012**: `py/command-line-injection` 9.8 in `workers/tateking/worker.py` (fixed: `_contained_media()`)
- **SEC-013**: Scanner limitations — fixed vulnerabilities vs. cleared alerts
- **SEC-014**: `py/sql-injection` 8.8 ×2 in `src/vector/adapter.py` (FP: identifier allowlist; fix: `fullmatch` vs. `match`)
- **SEC-015**: `py/path-injection` 7.5 ×2 in `src/personality/spawner.py` (fixed: lexical containment before resolution)
- **SEC-016**: `py/path-injection` 7.5 ×3 in `workers/gateway-service/router.py` (defence-in-depth: middleware held, handler now guarded)
- **SEC-017**: `py/path-injection` 7.5 in `src/backup/engine.py` (fixed: `_worker_backup_dir`, `_contained_backup_file`, `_permitted_restore_target`)
- **SEC-018**: `py/clear-text-logging-sensitive-data` 7.5 ×4 (FP: variable names; real fix: userinfo redaction in `VaultClient`)
- **SEC-019**: `py/weak-sensitive-data-hashing` 7.5 in feature flags (FP: deliberate MD5 for bucketing; pinned in tests)

All critical alerts cleared as of `bc074c33` (run 34584659158). 13 high alerts remain open.

## Open items (not security blockers for P0)

- Marketing architecture terms (quantum, dimensional, transcendent) — **not implemented** as production services; excluded from security score.
- Full Forgejo export — run `python scripts/export_forgejo_code_scan_alerts.py --merge` with `FORGEJO_TOKEN` set; confirm **0 open Critical** in Forgejo UI.

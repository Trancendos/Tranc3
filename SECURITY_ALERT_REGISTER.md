# Security Alert Register

Canonical triage for Forgejo/CodeQL/Trivy findings. Status values:

| Status | Meaning |
|--------|---------|
| **FIX** | Code or manifest change required |
| **FP** | False positive — documented with rule/suppression |
| **SUPPRESS** | Known issue with `.trivyignore` / CodeQL note |
| **ACCEPT** | Accepted risk with owner + review date |

Last updated: 2026-06-14

## Critical / High (sample from Forgejo export)

| ID | Source | Finding | Status | Action |
|----|--------|---------|--------|--------|
| #1539 | Trivy/Forgejo | Tiller CVE in `flux/base/deployments.yaml:251` | **FP** | Line 251 is `fmd-distiller` labels, not Tiller. No `tiller` image in repo. |
| #2127 | Dockerfile | `workers/ffmpeg-worker` runs as root | **FIX** | Non-root `tranc3` user added (Phase 1) |
| #1 | Trivy | `sentencepiece` CVE in requirements | **SUPPRESS** | Pinned `0.2.1`; documented in `.trivyignore` |
| #2638 | CodeQL | SSRF in `workers/notifications/worker.py` | **FP** | `validate_webhook_url()` before `urlopen`; tests in `tests/test_url_validation.py` |
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
| **bandit** | `src/`, `api.py`, `workers/infinity-auth`, `workers/infinity-ws`, `workers/api-gateway` | medium+ severity & confidence | `# nosec` only where justified (B104 Docker bind, B108 `/dev/shm`, B310 validated URLs, B102 workflow sandbox) |
| **semgrep** | `src/` only | ERROR severity | Fix or inline `nosemgrep` with rule id |
| **ruff** | `src/`, `api.py` | warn-only (`--exit-zero`) | E501 ignored |

## Trivy / IaC (`.trivyignore`)

| CVE | Status | Review | Notes |
|-----|--------|--------|-------|
| CVE-2026-1260 | **ACCEPT** | 2026-09-14 | `sentencepiece==0.2.1` is the patched release; Trivy DB lag — see `.trivyignore` |

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

## Verification commands

```bash
python scripts/security_score.py
python scripts/production_readiness_score.py
python -m pytest tests/test_url_validation.py tests/test_zero_cost_registry.py tests/test_adaptive_rotator.py -q
python scripts/pre_deploy_quality_gate.py
```

## Open items (not security blockers for P0)

- Marketing architecture terms (quantum, dimensional, transcendent) — **not implemented** as production services; excluded from security score.
- Full Forgejo export — run `python scripts/export_forgejo_code_scan_alerts.py --merge` with `FORGEJO_TOKEN` set; confirm **0 open Critical** in Forgejo UI.

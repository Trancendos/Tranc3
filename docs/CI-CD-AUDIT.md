# Tranc3 CI/CD audit

Date: 2026-09-08

## Executive summary

The repository had three CI engines (GitHub Actions, Forgejo Actions, and
Woodpecker), 41 GitHub workflows, 27 Forgejo workflows, and multiple copies of
the same lint, test, security, and deployment paths. A live Actions review of
the 50 most recent runs found repeated deterministic failures mixed with
starter-template workflows that cancelled each other. That made a red check
ambiguous and allowed the main test gate to report success after a failing test.

GitHub Actions is now the primary merge-gate and cloud deployment plane. The
canonical CI workflow is strict, concurrency-aware, cache-aware, diagnosable,
and explicit about which failures may be retried. Forgejo and Woodpecker files
remain as documented disaster-recovery automation; they are not treated as
GitHub merge gates and should be reactivated only after an operator confirms
the self-hosted runner and secret inventory.

## Evidence

The live run sample was collected from `Trancendos/Tranc3` on 2026-09-08 and
covered runs created on 2026-09-07. The repeated failures included:

| Area | Evidence | Finding |
| --- | --- | --- |
| CI | 4/4 failures | Ruff found 71 existing violations; the test job was blocked by lint. |
| Test Suite | 3/3 failures | Both dependency installation and pytest were fail-open with `|| true`. |
| Workflow validation | CI failed in `check_workflow_placeholders.py` | SOOS contained `<YOUR-PROJECT-NAME>` and Synopsys IO contained `{{PROJECT_NAME}}`. |
| Security templates | Pyre, Pysa, Snyk, Synopsys, Frogbot, SOOS, Defender, and Syft had repeated failures | Optional or unconfigured vendor templates were acting as required checks. |
| Pages | Astro, Gatsby, Hugo, Jekyll, mdBook, Next, Nuxt, and static Pages runs cancelled | Multiple starter workflows shared the `pages` concurrency group. |
| CodeQL and Scorecard | Recent runs succeeded | Retained as configured security controls. |
| Cloud deploys | Cloudflare, Fly, and frontend workflows are operationally distinct | Retained; deploy concurrency remains serialized and deploys stay main-only. |

The CI failure was deterministic, not a runner outage: the live log showed
Ruff's 71 violations and the placeholder check identified two invalid workflow
files. Those failures are not suppressed by this change.

## Target architecture

| Plane | Owner | Trigger | Policy |
| --- | --- | --- | --- |
| Merge gate | `.github/workflows/ci.yml` | Pull requests, pushes to `main`/`develop`, manual | Ruff, topology, repository conformance, pytest, coverage; deterministic failures fail the check. |
| Application security | `codeql.yml`, `trivy.yml`, `scorecard.yml`, `supply-chain-watch.yml` | PR, main, or scheduled | Keep distinct signal types; pin third-party actions and upload SARIF where configured. |
| Optional vendor security | Black Duck, Endor Labs, Zscaler | Existing configured triggers | Skip loudly when their repository variables are absent; do not add unconfigured paid scanners to the merge gate. |
| Frontend and deployment | `frontend-build.yml`, `deploy-cloudflare.yml`, `deploy-fly.yml`, `production-gate.yml` | Path-aware PR/main/manual | Build once, deploy only from main, serialize external side effects. |
| Operations | `.github/workflows/ci-health.yml` | Weekly schedule/manual | Inspect canonical runs; remediation can only rerun a first-attempt dependency/bootstrap failure. |

All new remediation is bounded to three attempts and never retries tests,
lint, security findings, or deployments. `scripts/retry_transient.py` retries
only network/registry-style errors and returns deterministic exit codes
unchanged. `scripts/ci_diagnostics.py` records runner, commit, disk, and
working-tree context without dumping secrets. `scripts/ci_health.py` refuses
automatic remediation unless the failed step is a dependency/bootstrap step,
the run is a first attempt, and the workflow is canonical.

## Retired automation

| Retired | Why |
| --- | --- |
| `test.yml`, `codecov.yml` | Duplicated the canonical test run; both suppressed dependency or test failures. Coverage and Codecov upload now run from `ci.yml`. |
| Astro, Gatsby, Hugo, Jekyll, Jekyll Pages, mdBook, Next, Nuxt, and static Pages workflows | Unedited starter templates targeting the same Pages deployment; live runs cancelled each other and did not describe a real repository surface. |
| Anchore Syft starter workflow | Failed on the default Docker path and duplicated container/dependency security coverage without a maintained image contract. |
| Defender, Frogbot, NeuraLegion, Policy Validator, Pyre, Pysa, Snyk, SOOS, Synopsys Action, and Synopsys IO | Repeatedly failing unconfigured vendor templates, invalid placeholders, or analyzers with no repository contract. Retaining these as required checks would hide real signal. |

Forgejo and Woodpecker are intentionally not deleted in this PR because they
contain self-hosted deployment and recovery capabilities. They are outside
the GitHub merge gate and should be consolidated separately only after the
Citadel runner, Forgejo endpoint, credentials, and rollback runbook are
verified. The GitHub workflows that mirror them remain the cloud-primary path.

## Follow-up actions

1. Fix the existing Ruff violations in a focused code-quality change; the CI
   gate now reports them honestly.
2. Configure or remove optional vendor integrations deliberately, with a
   named owner and secret inventory, rather than restoring starter templates.
3. After this PR is merged, confirm one scheduled `CI Health` run and inspect
   its summary. Use manual remediation only for a registry/bootstrap outage.
4. Revisit Forgejo/Woodpecker in a separate migration PR if the self-hosted
   recovery plane is no longer required.

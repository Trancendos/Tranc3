# Dependency resolution: prevention and incident playbook

**Owner:** Platform CI / dependency governance; security review required for policy changes.

## Why this exists

On 2026-10-23 a single-package OpenTelemetry security bump advanced
`opentelemetry-api` to 1.45.1 while the SDK/exporters remained 1.45.0 and
instrumentation remained 0.66b0. The pip resolver correctly rejected that
inconsistent dependency tree. This blocked Pytest, container builds,
performance smoke checks and the production gate even though Townhall
PR #1449 did not introduce the mismatch. PR #1430 proposes the compatible
core 1.45.1 / instrumentation 0.66b1 family.

The **primary lesson** is to distinguish a **build prerequisite failure**
from a functional test failure, and to prevent automatic partial security
upgrades of coupled dependency families.

## Automated controls

1. `scripts/check_otel_lockstep.py` checks repository-wide OpenTelemetry
   version agreement without installing the application. It runs first in
   the new dependency preflight workflow. It is intentionally retained
   instead of implementing a second, divergent pin parser.
2. `scripts/check_dependency_bot_safety.py` ensures security alerts remain
   enabled while vulnerability PRs cannot be auto-merged, and verifies that
   the final Renovate package rule prevents unattended OpenTelemetry bumps.
   Its negative tests verify that attempts to disable alerts, enable
   vulnerability automerge or override the family rule are rejected.
3. `.github/workflows/dependency-preflight.yml` triggers when Python
   dependency manifests, bot policies or its own check logic change. It
   performs static checks, a Python 3.11 `pip install --dry-run
   --ignore-installed -r requirements.txt` resolution, and an **independent**
   dry-run resolution of `requirements-security.txt`. Separate jobs keep
   security-scanner pin conflicts visible even when the root OpenTelemetry
   check fails first. These dry runs do not install application dependencies.
4. The existing CI Service Topology and Pytest jobs, SBOM freshness gate,
   container-image scan, security analysis and production merge gate remain
   authoritative. Do not remove them or mark a PR ready merely because
   preflight passes.

**Scope:** the dry runs resolve the root and security requirements files
independently, not every worker lockfile, the root+security combined
environment, every platform/Python version or built container. Other
workers receive static lockstep protection; their real builds and tests are
still mandatory. This is a deliberately targeted, relatively low-cost
preflight rather than a claim of complete dependency verification.

**Branch protection caveat:** this workflow uses path filters. A check
that does not run on unrelated PRs must not be made globally required
without adding an always-running aggregator/status job. Verify the
repository ruleset separately before relying on this gate for merging.

## Incident response

1. Identify the *first* failed step and collect its exact exit code and
   error lines. `ResolutionImpossible` during pip installation is a
   dependency problem, **not** evidence that Townhall's regression tests
   failed. An image not built is **not** an image whose vulnerabilities
   were successfully scanned.
2. Compare core/instrumentation pins between `requirements.txt` and
   worker requirements. Do not override the resolver with `--no-deps`,
   install suppression or `|| true`.
3. Propose the **entire verified compatible family** in one reviewable
   change; test `python -m pip install --dry-run --ignore-installed -r
   requirements.txt`. Also check affected worker manifests and run
   `python -m pip check` after a successful actual install.
4. Regenerate source SBOM artifacts when dependency manifests change:
   `python scripts/build_container_sboms.py`. Confirm freshness using
   `python scripts/build_container_sboms.py --check`. A source SBOM is
   not a substitute for the final built-image SBOM/vulnerability scan.
5. Rerun focused tests, full required CI, security scanners and the
   production gate on the **same commit SHA**. Surface independent
   findings (e.g. stale SBOMs, Rust advisories, or security scanner
   constraints such as `safety<4 filelock` versus an incompatible 4.x pin)
   as separate blockers.
6. Keep draft PRs blocked until checks and mandatory human reviews pass.
   Avoid forced pushes, blind merges and repository-wide pin changes
   without a coordinated release/rollback review.

## Acceptance criteria

- The OpenTelemetry static guard reports no split-family pins.
- The pip dry run succeeds for the root manifest and affected workers are
  independently validated.
- The security bot policy and negative regression tests pass.
- Source SBOM freshness and final container scanning pass.
- Pytest executes the focused Townhall regressions (not merely installs
  dependencies), and the full required suite passes.
- No new untriaged critical/high security finding exists; reviewers
  explicitly approve any documented residual risks.
- The PR is current with its intended base; no unresolved merge conflict;
  authorised maintainers approve merge and separate deployment decisions.

## Rollback

Revert **this guardrail PR** to restore the previous bot/CI behaviour if
it creates unexpected false positives, retaining the evidence and incident
record. Prefer repairing a demonstrably incorrect preflight condition over
disabling compatibility checks. Never revert dependency security updates
without first assessing the original vulnerability exposure. No workflow in
this change automatically writes to `main`, merges, deploys or opens
remediation PRs.

## Follow-up ownership

- **Dependency maintainers:** PR #1430, compatible pins, worker resolution.
- **Build/CMDB owners:** generated source-SBOM drift and container scans.
- **Townhall/security reviewers:** PR #1449 behaviour and consumer contracts.
- **CI governance:** consider classifying failures by first failing stage and
  notifying only on materially new root causes; preserve the exact commit
  SHA, workflow URL, error category and recommended action in every alert.

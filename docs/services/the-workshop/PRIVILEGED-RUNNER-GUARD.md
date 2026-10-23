# Workshop privileged-runner guard (2026-10-23)

Status: proposed in a draft PR, **not production-enforced until the PR is merged and the corresponding required CI status check is enabled in branch protection**.

## Why this exists

The Workshop's Forgejo runner configured in `deploy/forgejo/act-runner-deploy.yml` uses the `deploy-host:host` label, and the Compose service mounts the host Docker socket. This grants materially more privilege than the isolated `self-hosted` job containers. A workflow can route new jobs to `deploy-host`; the label itself is not a security policy.

## Implemented guard

`scripts/check_workshop_runner_guard.py` performs a read-only, offline inspection of every YAML workflow in `.forgejo/workflows/` and the deploy-runner configuration.

- Denies deploy-host jobs lacking the **exact** job-level main-ref predicate (`github.ref == 'refs/heads/main'`), including permissive OR predicates.
- Allows only explicit `push`, `pull_request`, `schedule` and `workflow_dispatch` trigger contexts on privileged workflows; denies every other event type and missing triggers.
- Flags dynamic expressions mentioning deploy-host in the `runs-on` selector.
- Rejects unreadable or invalid workflow files and a missing/renamed privileged runner label.
- Emits machine-readable JSON with source path, job, finding code and explanation; exits nonzero on findings.
- Runs regression tests and the guard from **both** mirrored CI pipelines; neither gate has `|| true` or `continue-on-error`.

## Commands

```bash
python -m unittest tests.test_workshop_runner_guard -v
python scripts/check_workshop_runner_guard.py
python scripts/check_workshop_runner_guard.py --json
```

Requires the existing `PyYAML` dependency. The check reads repository files only, needs no secrets/network and makes no changes.

## Threat model and limitations

This is a policy drift check and **defense in depth, not a sandbox or production proof**.

- A contributor who can rewrite/disable the CI check itself or push/merge directly to main bypasses a repository-file guard. Require branch protection, approved reviews, rules restricting changes to workflow/guard files, and non-bypassable required checks.
- Real runner registration, secret permissions, Docker socket exposure, host configuration and recovery still require separate operational inspection.
- Matrix/dynamic runner-selection expressions mentioning deploy-host are rejected, but indirectly resolving deploy-host from a general expression may not be statically detectable. Keep privileged runner selection literal and restrict this label at the platform level where possible.
- A workflow can be invoked via future/new Forgejo event types; event allowlisting intentionally fails closed until each context is reviewed.
- The user-facing dashboard must never imply a green code check proves live deployment or host isolation.

## Next increments

1. Add an independent branch-protection verification against the live GitHub and Forgejo settings and include the result in an evidence record.
2. Add a nightly signed/non-secret health snapshot of runners, restores and workflows, with explicit `unknown` when the host cannot be reached.
3. Introduce a repair planner that proposes bounded changes, emits diffs and tests, and requires review before touching secrets, runners or deployment.
4. Optionally evaluate Temporal for durable, idempotent non-destructive workflows; GPU/NVIDIA acceleration remains opt-in.
5. Reconcile old standalone `the-workshop` (archived) with the active Tranc3 Forgejo deployment without automatically unarchiving or migrating it.

Tracking: https://github.com/Trancendos/Tranc3/issues/1433

# Release readiness — the real backlog

**Measured** 2026-09-10 against the live tracker and this checkout.

## The backlog is twelve issues

Three externally supplied assessments describe this repository as carrying "863
open issues" and propose triage machinery to sort them. Measured:

```
$ gh issue list --state open --limit 100 | wc -l
12
```

All twelve are listed below. Each is a self-written issue with evidence, a
named mechanism and, in most cases, a proposed fix. This is not a backlog that
needs sorting; it is a backlog that needs *doing*, and it is short enough to
read in one sitting. See `docs/governance/EXTERNAL-ASSESSMENT-REVIEW.md` for
why the external figure differs and what in those documents is worth acting on.

## The twelve, grouped by what has to be true before a release

### Group A — controls that do not act (release-blocking)

These are the estate's recurring defect class: **a control that exists, runs,
and reports — but does not act, block, or is never invoked.** A release signed
off on evidence from a control in this state is a release signed off on nothing.

---

**#995 — CodeQL never loads the repo's own barrier models**
`security` · blocking

`.github/codeql/tranc3-python-models/` declares 24 path-injection barriers, 12
SSRF barriers and a log-sanitisation set for the estate's own validators. No
scan has ever loaded it. Read against the workflow, there are **three
independent reasons**, and fixing any one alone will not make it work:

1. `codeql.yml` passes `packs: ${{ matrix.packs }}`, and the matrix sets that
   to `codeql/python-queries:AlertSuppression.ql`. The custom pack is not in
   the value, so it is not requested.
2. `packs:` resolves *published* pack references from a registry.
   `trancendos/tranc3-python-models` is an unpublished directory in this repo,
   so even if it were named there it would not resolve. Local packs need
   `--additional-packs` (via `CODEQL_ACTION_EXTRA_OPTIONS`) or publication.
3. `.github/codeql-config.yml` lists `**/path_validation.py` under
   `paths-ignore`. The barriers would still apply to *callers* — that is what a
   barrier model is for — but the validator itself is never analysed, so a
   defect introduced in the validator is invisible to the scan that exists to
   trust it.

**Not attempted in this branch.** A CodeQL configuration change cannot be
verified locally; the feedback loop is a full scan on a pushed commit. Landing
one untested alongside this branch's other work would make a regression in
either indistinguishable. It should be one commit, on its own, with the alert
count before and after.

**Done when:** a scan log shows the pack loaded, and removing one barrier from
the pack measurably raises the alert count. Anything short of that is the same
"exists and is never invoked" state in a new costume.

---

**#991 — the freshness gate goes red on `main` when a bot bumps a digest**
blocking

`scripts/build_service_review.py --check` derives an artefact from live repo
state including `docker-compose.production.yml`. Renovate and Dependabot edit
that file unattended; their pull requests do not regenerate the artefact; the
moment one merges, `main` fails its own gate and every unrelated pull request
inherits the red.

The general principle, and it is the one this estate keeps re-learning:
**gates must measure change, not state.** A gate on absolute state fails when
the measuring apparatus moves, and reports that as a defect in the thing
measured.

**Partly answered already.** `src/immune/grade.py`'s `--changed-only` mode is
this principle implemented for findings, and `docs/governance/IMMUNE-SYSTEM.md`
records it. The freshness gate itself is not yet converted. Two workable
shapes: regenerate-and-commit in the bot's own pull request, or compare
*content* rather than the digest string so a digest bump is not a difference.

**Done when:** a Renovate digest bump merges to `main` and the gate stays green
without anyone touching it.

---

**#969 — a scheduled supply-chain census is failing**

Both censuses are fail-closed, which is correct and is why the failure is
informative rather than noise. It means either a fixable vulnerability is open,
or a stranded dependency has no reasoned disposition.

**Substantially answered in this branch.** The production merge gate's ten
fixable findings were taken (wrangler 4.124.0→4.131.0 across three Cloudflare
surfaces, `@cloudflare/workers-types` 5.20260910.1, grpc 1.83.1→1.83.2), and
the npm registry canary in `scripts/vulnerability_census.py` now brackets the
sweep so a soft registry failure can no longer be reported as a clean surface.

**Done when:** the scheduled run is green, and a deliberately re-introduced
vulnerable pin takes it red.

---

### Group B — correctness and security (release-blocking)

**#337 — `path_validation.py` intermediate-component symlink race**

`validate_path()` resolves, checks containment, then re-opens by pathname —
a check-to-open window. `O_NOFOLLOW` (added in #335) closes the race on the
*final* component only. Intermediate components remain exchangeable. The fix
is `dir_fd`-based per-component traversal with `O_NOFOLLOW` at each step.

Note the interaction with **#995**: this file is in `paths-ignore`, so CodeQL
is not watching the validator whose correctness every path-injection barrier
depends on. Fix #995 first, or the regression test is the only guard.

**Done when:** an adversarial test that swaps an intermediate component
mid-traversal fails closed, and it fails against the current implementation.

---

**#284 — `api-gateway` routes AI traffic to legacy `tranc3-ai`**

The issue already contains its own correction, which is the valuable part: a
straight repoint is **unsafe** because `tranc3-ai` and `infinity-ai` do not
implement the same API surface. Swapping the route would return 404s on
endpoints that exist today.

**Done when:** OpenAPI specs for both are diffed, an adapter covers what
`infinity-ai` lacks, contract tests pass against the adapter, and the legacy
route is removed only after burn-in — not before.

---

**#334 — analytics-service DuckDB sequence reseeding and write dedup**
`worker` `tech-debt`

`CREATE SEQUENCE IF NOT EXISTS events_seq START 1` always starts at 1, so a
restore against existing rows collides. Plus ambiguous-write deduplication.

**Done when:** a restore-over-existing-data test produces no id collision, and
a duplicate write is idempotent.

---

### Group C — operability (release-blocking for a live service)

**#1146 — `misp-db` has no backup, restore, or DR runbook**

The mechanism named in the issue is structural, not an oversight: the estate's
backup engine is **SQLite-only**, and `misp-db` is MySQL. It is not that
somebody forgot to schedule a job; there is no code path that could run one.

This is the highest-consequence item on the list. A lost `misp-db-data` volume
is unrecoverable threat-intelligence state, and no amount of scanning
compensates.

**Done when:** a backup runs on a schedule, a restore has been performed into a
clean volume and verified, and RTO/RPO are written down. A backup nobody has
restored from is a belief, not a control — the same defect class as Group A.

---

**#990 — `build-storybook` is broken on `main`**

`src/stories/Configure.mdx` imports nine PNGs that were never committed. Ten
unresolved imports, build fails.

Cheap and mechanical: commit the assets or remove the imports, then put the
storybook build in CI so it cannot rot again unobserved. The general lesson is
worth keeping: **text-based review cannot see an absent binary.** A declarative
asset manifest is the sensor for what code review has no organ to detect.

---

### Group D — governance and debt (not release-blocking)

**#474** — ledger-service must partition INTERNAL vs EXTERNAL entries.
`compliance/capital_governance_binding.yaml` declares distinct ledgers per
`function_type` (`royal-bank-arcadia.operating-ledger` vs
`arcadian-exchange.trading-ledger`); both currently route through one worker.
A compliance-visible split, not a defect in behaviour today.

**#336** — `the-grid`'s `GridDatabase` / `WorkflowEngineRouter` are module
globals performing schema I/O at import time, so they cannot be instantiated
per-app and tests cannot isolate. Related in kind to
`scripts/check_import_time_filesystem.py`, which already guards this pattern
elsewhere.

**#174** — Renovate's Dependency Dashboard. Not an issue; a bot's standing
inventory. Do not count it as backlog and do not close it.

**#1180** — "GitHub Actions need review and fixing before this goes forward."
**This is what pull request #1150 is.** 48 workflow files reduced to 27, 24
firing per pull request reduced to 14, 38 jobs to 29; thirteen checks that
could never pass under any circumstances removed or gated; two gates that were
red on `main` itself fixed. See `docs/governance/CI-ESTATE-CONSOLIDATION.md`.

## What "ready to release" means here

A definition-of-done that can be checked, rather than asserted:

| Condition | How it is checked | State |
|---|---|---|
| No release-blocking issue open | Groups A–C above closed | 8 open |
| Every gate has been calibrated | inject the fault, prove the gate fails, restore, prove it passes | done for the immune gate, the nosec guard, the doc guard; **not** for CodeQL (#995) |
| No control that never runs | #995 closed; `scripts/check_guards_are_wired.py` green | #995 open |
| Backups restored, not just taken | #1146 closed with a performed restore | open |
| `main` stays green unattended | #991 closed; a bot digest bump merges without going red | open |
| Supply chain fail-closed and green | #969 closed; census green and a re-introduced vulnerable pin takes it red | census green locally, scheduled run unverified |
| Every deployed service has an owner | 52 unclaimed worker paths routed by the Town Hall | open — see below |

## The one thing not on the tracker

`scripts/triage_change.py` measured, on its first run:

```
worker directories:                                     90
claimed by a Location's worker_path:                    35
unclaimed:                                              55
   ...of which deployed in docker-compose.production.yml:  52
```

Fifty-two services are deployed and claimed by none of the 43 Locations.
`workers/cranbania/` is among them — The Town Hall's `worker_path` is
`src/townhall/`, so the submodule that *is* The Town Hall's deployed service is
attributed to nobody.

**This is not assigned here.** The owner's standing decision is that which
Location owns an item is a Town Hall decision recorded in the Backlog Routing
Register, not a lookup performed by judgement. It is raised here because a
release with 52 unowned running services has no answer to "who is paged", and
that question is not answered by any of the twelve issues.

## What this estate is actually good at, and should not be talked out of

Worth stating, because three external assessments in a row have described a
platform in crisis and the measurements do not support it:

- **Twelve open issues against 3,102 tracked files**, each with evidence and a
  named mechanism. Several correct their own original finding partway through
  (#284 is the clearest). That is a well-run tracker.
- **CodeFactor rates the repository A**, 99.4% A-grade files, zero open issues.
  This estate's own independent grader says A at 99.8%.
- **267 of 347 bandit suppressions carry a written reason**, and zero are bare.
- The gates that were found not to act have been found *by this estate*, and
  each has been fixed with a calibration proving it now acts.

The gap between that and "ready to release" is eight issues and an ownership
question — not a crisis, and not 863 of anything.

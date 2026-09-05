# SWOT & Forensic Assessment — Trancendos

**Assessed** 2026-09-05. Every number here was measured on this checkout on
that date; none is carried forward from an earlier report. Where a figure
replaces one previously published, the previous figure and why it was wrong
are stated rather than quietly corrected.

## Why this document exists at all

The estate already held **five** SWOT or forensic documents:

| Document | Dated | Reachable from |
|---|---|---|
| `wiki-content/Historical-SWOT_ANALYSIS.md` | May 2026 | nothing |
| `wiki-content/Historical-PHASE21_SWOT_FORENSIC.md` | Phase 21 | nothing |
| `wiki-content/Historical-PHASE23_FORENSIC_REPORT.md` | Phase 23, v0.7.0 | nothing |
| `wiki-content/Historical-SWOT_PHASE24_FORENSIC.md` | Phase 24 | nothing |
| `wiki-content/Historical-FORENSIC_ASSESSMENT_2026-05-31.md` | 31 May 2026 | nothing |

"Reachable from nothing" is measured, not rhetorical: no markdown link, no
backtick path mention, no code reference, and not swept into
`docs/governance/ACTION-BACKLOG.md`. Searching every tracked file in the
repository for each document's path *or* bare filename returns only itself.

They are genuine historical records and are **not** retired — a phase report
is evidence of what was true then. What they lacked was an index and a
successor. This document is the successor; the table above is the index.

## The measurement that frames everything else

**52 of 321 markdown documents (~530 KB) are named by nothing anywhere in the
repository.** Twenty-eight of those are `wiki-content/Historical-*` and
`wiki-content/Strategy-*`: phase reports, mind maps, SCAMPER analyses,
zero-cost assessments, branch-consolidation logs and three `Todo-*` lists.

This is the estate's characteristic failure, and it is not a documentation
problem — it is the same defect the engineering work keeps finding, in a
different medium: **something correct, present, and never invoked.** A guard
that runs and never blocks. A control that reports and never acts. A register
that is accurate and unread. The platform is very good at producing artefacts
and comparatively poor at wiring them to something that consumes them.

---

## SWOT

### Strengths

- **Controls that are calibrated, not merely present.** 49 guard scripts, 47
  of them wired into a workflow that runs, and the two that are not carry a
  written reason enforced by `scripts/check_guards_are_wired.py` — a
  meta-guard that includes itself in its own discovery. The estate's habit of
  proving a control acts by injecting the fault and watching the named test
  fail is unusual and is the single most valuable thing here.
- **A canonical register with a machine-checked alignment.**
  `src/entities/platform.py` and `src/config/id_registry.json` now agree on
  all 43 Locations, enforced by `scripts/check_id_registry_alignment.py`,
  which also fails when both agree on a path that is not on disk.
- **Deployment truth is derived, not asserted.** Ports, Traefik rules, build
  contexts and stripprefix middleware in the 43 solution packs are read out of
  `docker-compose.production.yml` at generation time. A pack cannot drift from
  the deployment without failing `--check`.
- **Ratcheted baselines.** `flow_baseline.json` and
  `import_writes_baseline.json` fail on regression *and* on an unrecorded
  improvement, so getting better is a visible act in the diff rather than a
  silent loosening.
- **Entrypoint hygiene is real.** All 89 worker Dockerfile `CMD`s were audited
  against the files present in each build context on 2026-09-05. Zero name a
  file that is not there.

### Weaknesses

- **82% of the recorded backlog is unrouted.** 163 open items swept from 44
  registers; **29 name a Location, 134 do not.** An item with no Location has
  no owner, no solution pack, and no accountable party — routing it is the
  first story in every one of those 134 cases.
- **The backlog sweeps tables only.** 81 unchecked checkbox items sit in 13
  documents — including all three `Todo-*` lists — and none of them reach the
  backlog, because `harvest()` reads markdown tables. A backlog that claims
  "every outstanding item the estate records" and cannot see `- [ ]` is
  overstating its coverage.
- **Forgejo is the declared primary CI and is dormant.** 32 workflow files, 57
  of 83 jobs pinned to a `self-hosted` runner that is not standing. The
  production merge gate exists in both trees and had already diverged
  materially before `scripts/check_workflow_drift.py` was written. The weaker
  gate is the one that takes over the day The Workshop returns.
- **Two registers of outstanding security work, one of them scored.**
  `SECURITY_ALERT_REGISTER.md` contributes 12 points to the readiness score
  through a substring test (`_register_complete()`) that checks four words are
  present. It passed while the register contained two entries filed under the
  same ID.
- **CodeFactor is red and its report is behind a login.** It has failed on
  this PR across every commit. The check run GitHub receives carries an empty
  summary and empty text, so the only signal available is the title
  "1 issue fixed. 4 issues found."

### Opportunities

- **Sweep checkbox work into the backlog.** A ~20-line addition to
  `harvest()` closes the 81-item blind spot and is the highest coverage gain
  per unit of effort available.
- **Route the 134.** Each is a small, mechanical decision, and every one
  converts an unowned item into an item with a Location, a pack, and an
  accountable name. This is the largest single improvement to the estate's
  answerability.
- **Index the 52 dark documents.** They do not need retiring; they need to be
  reachable. `wiki-content/_Sidebar.md` exists and is itself dark.
- **Turn the entrypoint audit into a standing guard.** It is currently green
  across 89 workers, which is exactly when a ratchet is cheapest to install.
- **~40 of 55 open PRs are bot dependency bumps.** Grouping and auto-merging
  the safe classes would cut the review surface by two thirds and is well
  within what Renovate and Dependabot already support.

### Threats

- **Branch sprawl obscures state.** Over 100 branches, of which six
  issue-branches (`174-`, `284-`, `334-`, `336-`, `337-`, `474-`) all sit at
  the identical commit `99f159e1` — created and never worked. Thirteen
  `cursor/production-readiness-*` branches and nine `bolt*` branches compound
  it. Nobody can tell live work from abandoned work by looking.
- **Funding-gated architecture.** Cloud Only is the default for all 43
  Locations because the local server needs money that is not available. Every
  Hybrid/Local plan in the estate is written as though it were scheduled.
  Reading those documents without that context overstates readiness.
- **Rate limits are the stated reason for the self-hosted posture, and the
  platform currently depends on both rate-limited services** — GitHub Actions
  is the only CI that runs, and ~26 Cloudflare Workers are live.
- **The register's own trust.** A generated document is believed for longer
  than a hand-kept one. Every generator in this estate must therefore be held
  to a higher standard than the documents it replaces — and two of them failed
  that standard this week (the backlog re-ingested its own output; the
  topology map's mount detector recognised one import spelling).

---

## Forensic findings

Ordered by what a reader should act on first. Each states the evidence, not a
judgement.

### F1 — The topology map invented two findings (fixed 2026-09-05)

`scripts/build_topology_3d.py`'s `mounted_in_api()` matched the single import
spelling `from src.X.routes import`. `api.py` mounts **39** routers; the regex
resolved **25**. The 14 it could not see are those whose module is not named
`routes` — `src.mcp.server` (The Spark), `src.personality.turingshub.routes`
(Turing's Hub), `src.monetisation.router`.

Consequence: The Spark — the MCP server mounted at `/mcp/*` since
`api.py:798` — was reported as a Location with nowhere to receive traffic, and
that was reported to the owner as a finding. Replaced with AST resolution of
every `include_router(<name>)` call back through the file's import bindings.

**Corrected: two Locations have nowhere to receive traffic, not five.**
Arcadia (`web/`, a frontend) and The Citadel (`deploy/`, the compose and
Traefik configuration). Both are correct as recorded; neither is a service.

### F2 — The Chaos Party's CMDB record named its test suite as its service (fixed)

`worker_path="tests/"`, `worker_port=None`, while
`docker-compose.production.yml:3825` builds `./workers/chaos-party`, publishes
8079, sets `PORT=8079`, and gives it its own Traefik host rule
(`chaos-party.trancendos.com` + PathPrefix `/chaos-party`) — one of the few
Locations with a dedicated host rather than a path prefix.

Its solution pack consequently stated the opposite of the truth about its
build context: it claimed the Location runs in-process under `api.py` and
*may* import from `src/`. It runs from `./workers/chaos-party`, where `src/`
is not in the image. That is the single most common cause of a worker that
passes tests and dies in the container.

This is the 23rd CMDB record corrected in this engagement, after the 22 found
by the ID-registry alignment work.

### F3 — The action backlog re-ingested its own output (fixed)

The generated backlog is a markdown document full of tables, so the sweep read
it as a register: 163 items became 326, then 489, compounding by 163 per run.
`--check` could never pass, because regenerating produced a different file
from the one just written — a gate failing on correct input, which is how a
gate gets switched off.

### F4 — `_ensure_parent` rejected a `str` (fixed)

The lazy-mkdir helper added to six SQLite workers annotated its argument
`Path` and used `path.parent`. `DB_PATH` is a configuration value and every
fixture in `tests/test_workers_p3.py` substitutes a plain string, so setup
raised `AttributeError` — 41 pytest collection errors, none naming a real
defect in the code under test.

### F5 — The Cloudflare overrides were floors, and `npm ci` ignores them anyway (fixed)

`overrides: {"esbuild": ">=0.25.0", "ws": ">=8.21.0"}` clears both advisories,
but `deploy-cloudflare.yml` runs `npm ci`, which installs the resolved tree in
`package-lock.json` and does not re-resolve against `overrides` at all. All
three committed locks carried esbuild 0.28.1 and ws 8.21.0/8.21.3 — versions
that happened to satisfy the ranges, so nothing forced them and nothing would
have reported it had a future install picked otherwise.

The test covering this asserted only that the `esbuild` and `ws` **keys** were
present, which `{"esbuild": "0.24.0"}` would have passed.

### F6 — Two register entries shared one ID (fixed)

`SECURITY_ALERT_REGISTER.md` filed the esbuild/ws entry as SEC-006, already
the nltk entry's ID. A disposition recorded "against SEC-006" lands on
whichever entry the reader reaches first. Renumbered SEC-008;
`scripts/check_doc_duplication.py` now fails on a repeated entry ID.

### F7 — 81 checkbox work items are outside every sweep (open)

| Document | Unchecked items |
|---|---|
| `wiki-content/Architecture-ARCHITECTURE_UPDATE.md` | 13 |
| `docs/DEPLOYMENT_RUNBOOK.md` | 11 |
| `docs/cab/APPROVAL_WORKFLOW.md` | 11 |
| `wiki-content/Strategy-DOC-14-Zero-Cost-Hosting.md` | 9 |
| `docs/change-request-process.md` | 7 |
| `docs/compliance/HIPAA-ALIGNMENT.md` | 7 |
| `docs/runbooks/disaster-recovery.md` | 7 |
| six others | 16 |

Not all 81 are backlog items — some are runbook procedure steps and template
placeholders, which are checklists rather than outstanding work. Separating
the two is the work; the current state is that none of them are visible.

### F8 — GitHub state (open, see the hygiene section)

---

## GitHub hygiene

Measured 2026-09-05 against `Trancendos/Tranc3`.

**55 open pull requests**, by origin:

| Origin | Count | Disposition |
|---|---|---|
| Dependabot / Renovate / pre-commit.ci | ~40 | Group and auto-merge the safe classes |
| Bolt (performance) | 6 | Review as one batch — all touch pure-Python vector math |
| Jules / Palette (tests, accessibility) | 3 | Review individually; two are accessibility fixes |
| CodeFactor autofix (#842) | 1 | 14 days stale — close or rebase |
| This engagement (#1150) | 1 | Active |

The five stalest are **#842** (14d), **#928** and **#879** (13d), **#774** and
**#519** (11d). #774 has been waiting on a close authorisation since before
this engagement.

**Over 100 branches.** Six issue-branches — `174-dependency-dashboard`,
`284-api-gateway-routes…`, `334-harden-analytics-service…`,
`336-the-grid…`, `337-path_validation…`, `474-ledger-service…` — all sit at
the identical commit `99f159e1`, meaning they were created from an issue and
never committed to. Thirteen `cursor/production-readiness-*` and nine `bolt*`
branches follow the same pattern of parallel attempts at one goal.

**11 open issues**, which is proportionate and mostly legitimate — three
labelled `worker`, three `tech-debt`, and one each `compliance`,
`infrastructure`, `supply-chain-watch`, `security`. Six predate this
engagement by 34–67 days (#174, #284, #334, #336, #337, #474) and each has a
branch at `99f159e1`, so the issue is open and the work never started.

**No forks were examined** — the repository-access scope for this session
covers `Trancendos/Tranc3`, `CranBania`, `magna-carta` and `infinitystyles`,
and fork enumeration was not run.

---

## What is not known

Stated so the confident parts above can be trusted.

- **CodeFactor's four issues.** The check run carries no output through
  GitHub and the report requires a login. Two error-class findings were
  identified and fixed by running the same linter locally; whether they are
  the same four is unverified.
- **Whether the 81 checkbox items are work or procedure.** Counted, not
  classified.
- **Runtime behaviour of anything.** Every finding here is from source,
  compose, and CI logs. No service was started and no endpoint was called.
- **The three unset repository secrets** (`FLY_API_TOKEN`, `CF_API_TOKEN`,
  `CF_ACCOUNT_ID`) mean the deploy workflows have never been observed to run.

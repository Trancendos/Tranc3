# SWOT & Forensic Assessment — Trancendos

**Assessed** 2026-09-05. Every number here was measured on this checkout on
that date; none is carried forward from an earlier report. Where a figure
replaces one previously published, the previous figure and why it was wrong
are stated rather than quietly corrected.

## Correction, issued the same day

**The first version of this document opened with a finding that was wrong, and
the error was in my own measuring tool.**

It claimed that five SWOT and forensic assessments existed in the estate and
that every one of them was unreachable — no link, no mention, nothing that
could lead a reader to them. It further claimed that **52 of 321 documents**,
about 530 KB, were in that state.

Both figures came from a reachability test that searched every tracked file
for a document's repository path or its bare filename. GitHub's wiki
convention addresses a page **without its extension** —
`[Tranc3 Infrastructure Build](Todo-todo_infra)`, not `Todo-todo_infra.md` —
and `wiki-content/Home.md` and `wiki-content/_Sidebar.md` index the entire
`wiki-content/` tree in exactly that form. My test could not see the one link
syntax those files use, so the whole tree read as orphaned.

**Corrected: 8 of 322 documents are named by nothing.** And all five prior
assessments are indexed, from both the wiki Home page and its sidebar. They
were never lost.

`scripts/check_doc_reachability.py` now matches the extension-elided stem, and
excludes its own baseline from the corpus it searches — the baseline lists
every path under test, so leaving it in made every recorded document appear
reachable. That is the action backlog's self-ingestion defect (F3 below)
reproduced in a new gate one commit later, which is worth stating plainly: a
generator or a gate whose own output is part of its input will always be
wrong, and it is worth checking for by habit rather than by accident.

## The five prior assessments

Kept and indexed here for continuity. They are point-in-time phase records —
evidence of what was true then — and are not superseded in the sense of being
wrong; this document simply carries the current measurements.

| Document | Dated |
|---|---|
| `wiki-content/Historical-SWOT_ANALYSIS.md` | May 2026 |
| `wiki-content/Historical-PHASE21_SWOT_FORENSIC.md` | Phase 21 |
| `wiki-content/Historical-PHASE23_FORENSIC_REPORT.md` | Phase 23, v0.7.0 |
| `wiki-content/Historical-SWOT_PHASE24_FORENSIC.md` | Phase 24 |
| `wiki-content/Historical-FORENSIC_ASSESSMENT_2026-05-31.md` | 31 May 2026 |

## The documents nothing names

The current set lives in `config/estate/doc_reachability_baseline.json`, and
it lives there rather than being tabulated in this document for a reason worth
recording.

The first attempt did tabulate them here — and the count immediately dropped
to zero, because a document that lists orphans makes them no longer orphans.
**That is the self-ingestion defect (F3) for the third time in three days**:
the action backlog swept its own output, the reachability gate searched its
own baseline, and then this assessment enumerated the very set it was
measuring. Three instances of one mistake, all three mine.

The general shape is worth stating once, because it will recur: *any artefact
that both measures a property and is itself part of the population being
measured will report the wrong answer.* The fix is the same each time — take
the artefact out of its own corpus — and so is the way to catch it: run the
generator twice and compare.

So the inventory sits in the baseline, which the gate excludes from its own
corpus, and this document characterises it instead. The set is small and
mostly architectural: an index that nothing indexes, two architecture
documents that no architecture document references, a DefStan standard, a
Mattermost webhook note, and a competitive analysis written during this
engagement. **The newest entries are mine**, which is the honest scale of it —
a list somebody can clear in a week, and unlike fifty-two, a true one.

## SWOT

### Strengths

- **Controls that are calibrated, not merely present.** 50 guard scripts, 48
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

- **85% of the recorded backlog is unrouted.** 201 open items swept from 51
  registers; **31 name a Location, 170 do not.** An item with no Location has
  no owner, no solution pack, and no accountable party — routing it is the
  first story in every one of those 170 cases. (This read 163/29/134 until
  the checkbox blind spot below was closed; F7 records the correction. The
  share got *worse*: 36 of the 38 items the sweep had been missing name no
  Location, and only 2 do — which is what an honest denominator does.)
- **The backlog swept tables only.** 81 unchecked checkbox items sat in 13
  documents — including all three `Todo-*` lists — and none reached the
  backlog, because `harvest()` read markdown tables. A backlog that claims
  "every outstanding item the estate records" and cannot see `- [ ]` was
  overstating its coverage. Closed; see F7.
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

- **Route the 170.** Every one converts an unowned item into an item with a
  Location, a pack, and an accountable name. This is the largest single
  improvement to the estate's answerability — and it is a decision, not a
  mechanical mapping: the Town Hall's routing register
  (`src/townhall/routing.py`, `/townhall/routing`) is now the place it is
  made, with a named authority and a written reason, so the queue is
  answerable rather than assignable by whoever regenerates the file.
- **Link the 8.** A week's work, not a programme. Two of them are an index
  nothing indexes (`docs/DEPLOYMENT_INDEX.md`) and two are architecture
  documents no architecture document references.
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

### F7 — 81 checkbox work items were outside every sweep (fixed)

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

Not all 81 were backlog items, and separating the two was the work. The
discriminator turned out to be a property of the **document's role**, not of
the item's wording: `- [ ] PRAGMA integrity_check returns ok` in
`docs/runbooks/disaster-recovery.md` is a step performed during a drill,
`- [ ] Step 2:` in the CAB form is a blank, and `- [ ] Authentication via
Infinity` in a Town Hall template is a prompt for whoever instantiates it.
None is work somebody has failed to do.

So the exclusion is drawn by path and written down —
`config/townhall/templates/`, `docs/runbooks/`, anything named `*RUNBOOK*`,
the CAB approval workflow and the change-request process — rather than guessed
per line. Sweeping those would have added roughly fifty procedure steps to the
backlog as unbuilt features, which is worse than missing the real ones: it
buries them and makes the total meaningless.

**38 genuine items now reach the backlog**, from seven documents: 13 unbuilt
middleware components in the architecture update, 9 zero-cost hosting setup
steps, 7 HIPAA alignment items, 4 vault-security items, and the three
`Todo-*` lists that exist for no other purpose and had been contributing
nothing. Zero come from the four procedure documents. The total moves
**163 → 201**, and the routed share **29/163 → 31/201**, which is the more
honest denominator.

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

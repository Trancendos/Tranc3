# Review of the external assessments of Tranc3

**Reviewed** 2026-09-10, against this checkout and the live repository on
GitHub. Three AI-generated documents have been supplied by the owner:

1. *Tranc3 Deep Dive — Forensic Assessment, SWOT & Remediation Roadmap*
2. *Tranc3 → Production-Ready: PLM-Style Agile Backlog & Delivery Plan*
3. *TRANC3 — Immune-System Architecture* (Kagi Assistant, supplied later the
   same day; reviewed in its own section at the end)

Every figure below was measured. Where a claim is marked wrong, the measured
value and the command that produced it are given, so the correction can be
re-checked rather than taken on trust.

## Summary

Both documents identify real themes and get almost every number wrong. Document
2 derives its epic sizing and sprint sequencing from Document 1's figures, so
its arithmetic inherits the same errors — E4 is built entirely on a backlog of
"851 CodeFactor issues + 863 GitHub issues", against **12 open issues**.

One claim is right, and is worse than either document says. It is not the one
they lead with.

## What was measured

| Claim | Source | Measured | Verdict |
|---|---|---|---|
| "2,259 files" | Doc 1 §3 | **3,118 tracked** (`git ls-files \| wc -l`, at `cd7f22a5`) | wrong |
| "863 GitHub issues" | Doc 1 §2, §3 | **12 open** | wrong by ~70× |
| "150 PRs" | Doc 1 §2 | **84 open** — and see *The bot fleet* below | wrong, and mischaracterised |
| "851 open CodeFactor issues" | Doc 1 §2, Doc 2 E4 | not verifiable from the repository; CodeFactor is external and its API is not reachable from here | **unverified** — Doc 2's largest epic rests on it |
| "48 abandoned dependencies" | Doc 1 §2, §3 | not verified; the named crates (`hex 0.4`, `ring 0.17`, `subtle 2.6`) **are** present | partly grounded |
| "releases page effectively empty" | Doc 1 | 7 releases; latest `v0.4.0`, 2026-05-23 | wrong in letter, right in spirit — 3.5 months stale |
| "29 Python/FastAPI workers" | Doc 1 §1 | **92** directories under `workers/` | understated ~3× |
| "45+ MCP tools" | Doc 1 §1 | not counted here; `src/mcp/` holds five tool modules | unverified |
| "0 npm vulnerabilities" (listed as a **strength**) | Doc 1 §2 | **9 fixable npm findings** in today's census | **wrong — and see below** |
| `Dimensional/` vs `shared_core/` `sentinel_station.py` | Doc 1 §2, §3 | both exist and **differ** — 797 vs 817 lines, 48 changed lines | real; the prescription is not |
| scale of that duplication | Doc 1 §3 | **75 files** exist in both trees and **not one pair is identical**; the report flagged one | badly understated |
| `tranc3-ts/src/core/definitions.ts` | Doc 1 §2 | exists | correct |
| `tranc3-api` / `tranc3-web` / `nsa-broker` / `shi-gateway` unresolvable | Doc 1 §3 | all four appear in `src/nanoservices/igi_gitops/flux/overlays/*` | correct that they exist |
| `ceph-csi` / `local-path-provisioner` unresolvable | Doc 1 §2 | both in `deploy/k3s/Chart.yaml` | correct that they exist |
| "three separate TODO files" | Doc 1 §2 | `Todo-todo.md`, `Todo-todo_infra.md`, `Todo-tranc3-ts-todo.md` | **correct** |
| "CI + security scans exist but are non-blocking" | Doc 1 §2, Phase 2 | outdated — `production-gate.yml` blocks on the census | superseded |

## The claim that is right, and why it is worse than stated

Document 1's forensic root cause #1 is *"Supply-chain blindness (critical) …
You cannot trust a dependency dashboard that can't see half your dependencies."*
That sentence is correct. Its diagnosis — missing Renovate registry credentials
— is not the mechanism.

**Two mechanisms were found, both measured.**

### 1. The census could report clean without having looked

`scripts/vulnerability_census.py` feeds the production merge gate. Its npm half
runs `npm audit --json`. Run twice over an unchanged tree it produced **2
fixable findings and then 9**, with `scanned_ok: true` and `errored: []` both
times; `cloudflare/infinity-void`, `cloudflare/tranc3-ai` and
`cloudflare/trancendos-api-gateway` each went from 0 findings to 3, together.

`npm audit` resolves the dependency tree locally from the lockfile and asks the
registry which packages carry advisories. When that endpoint answers with
nothing useful — a 200 with an empty body, a proxy that swallows the POST, an
endpoint degraded rather than down — npm prints
`{"auditReportVersion": 2, "vulnerabilities": {}, "metadata": {…}}` with the
dependency counts filled in from the lockfile, exit 0, no `error` key. That is
byte-for-byte the shape of a clean surface.

Injected and confirmed against a local server answering 200 with `{}`:
`_scan_npm("cloudflare/tranc3-ai")` returns `errored: False, findings: 0`. A
hard connection refusal is already caught — npm emits an error payload — so
only the *soft* failure was silent, and the gate reads silence as a pass.

Document 1's "0 npm vulnerabilities", filed under Strengths, is exactly the
output this failure produces. Nothing in the report could have told the
difference, because nothing in the census could either.

Fixed at `2f524a15`: `scripts/census_canary/` pins `minimist 0.0.8`, covered
permanently by GHSA-vh95-rmgr-6w4m. A canary audit reporting zero advisories
can only mean the endpoint is not answering, and every npm surface in that run
is then recorded unscanned rather than clean. The reading brackets the sweep, so
a registry that degrades mid-run invalidates it too.

### 2. Rust and Go were genuinely invisible — on `main`, today

The estate carries 9 `Cargo.toml` and 3 `go.mod` manifests. On `main` the census
scans pip and npm only, so all twelve are outside the merge gate — including the
crypto-adjacent crates Document 1 correctly flags as a threat.

This is already fixed on the working branch (`src/dvms/native_ecosystems.py`,
OSV-backed): twelve native surfaces are in **both** census scopes, and today's
run surfaces a real one — `aeonmind/go/go.mod`, `google.golang.org/grpc`,
GHSA-2v4p-qf9q-27wj. It reaches `main` when that branch merges, not before.

## What both documents miss entirely: the bot fleet

Of 84 open pull requests, roughly 72 are machine-authored, across at least seven
automations with overlapping mandates — Aikido, Dependabot, Renovate, Bolt,
Palette, pre-commit.ci and CodeFactor. They propose the same upgrades twice:

- `rand` 0.8.8 → 0.10.2 — #1171 (Aikido) and #1103 (Renovate)
- `google.golang.org/grpc` — #1148 (Dependabot, 1.83.1) and #1092 (Renovate, 1.83.2)

Three separate pull requests set out to remove the same unconfigured scanner
workflows: **#1152** (merged 2026-09-05), **#1175** and **#1177**, the latter two
still open and overlapping both each other and what #1152 already landed.

The supply side is the same story. `main` carries **47** workflow files, 28 of
them added since this branch's merge base and almost all unedited GitHub starter
templates — `astro.yml`, `gatsby.yml`, `hugo.yml`, `jekyll.yml`,
`jekyll-gh-pages.yml`, `mdbook.yml`, `nextjs.yml`, `nuxtjs.yml`, `static.yml`
for a repository that publishes none of those; `pyre.yml`, `pysa.yml`,
`neuralegion.yml`, `snyk-security.yml`, `soos-dast-scan.yml`,
`policy-validator-cfn.yml`, `synopsys-io.yml` for scanners nobody configured.
`label.yml` is the clearest specimen: its own header says "you will need to set
up a `.github/labeler.yml` file with configuration", that file has never
existed, and so the `label` check has been failing on every pull request in the
repository — including on `main`. Adding automation is not the same as
operating it.

"150 stale PRs" is not a human backlog anyone is failing to review. It is an
unarbitrated automation estate, and it is the same duplication pathology
Document 1 identifies in the source tree, one level up. The Backlog Routing
Register (`src/townhall/routing.py`) is the instrument that already exists for
deciding who owns what; nothing yet arbitrates between the bots.

## The other finding neither document could have made

There are **two Renovate configuration files**, both tracked:

- `.renovate.json` — 3.5 KB, 2026-08-24, extends the **deprecated** `config:base`
- `renovate.json` — 7.4 KB, 2026-09-04, extends `config:best-practices`

Renovate's documented file precedence puts `renovate.json` ahead of
`.renovate.json`, so the older file is read by nobody. Document 1's Phase 2
prescribes adding `config:best-practices` — which landed on 4 September in the
file that is actually live. The report was reading the dead one.

This is the same defect class as everything above: an artefact that exists, is
tracked, is maintained, and is never consulted. PR #1177 deletes it, correctly.

## Assessment of Document 2 (the PLM backlog)

The structure is sound and matches how the Town Hall already works — PRINCE2
stage gates over an agile lifecycle, eight epics, explicit tech-debt items.
Three problems:

1. **E4 ("Quality Gates & 851-Issue Burn-down", P0, Weeks 2–6)** is the largest
   epic and rests entirely on an unverified external figure. Against 12 open
   issues it is not a six-week epic.
2. **E1 ("Supply-Chain Visibility", P0, Week 1)** is the right priority for the
   wrong task. Its stories are Renovate registry credentials; the actual
   blindness was a scanner that could not say it had not looked, plus two
   unscanned ecosystems.
3. **E5 ("Release Engineering")** is under-prioritised at P1/Week 4. A 3.5-month
   release gap on a platform this active is the clearest measured signal in
   either document.

Sequencing that follows the measurements instead:

| | Work | Basis |
|---|---|---|
| 1 | Merge the native-ecosystem census and the registry canary | 12 manifests outside the gate; a gate that could pass blind |
| 2 | Arbitrate the bot fleet — one dependency automation, the rest disabled | 72 machine PRs, duplicate proposals, three competing workflow PRs |
| 3 | Consolidate the two Renovate configs | a live config and a dead one |
| 4 | Cut a release | latest is `v0.4.0`, 2026-05-23 |
| 5 | Measure the `Dimensional/` ↔ `shared_core/` divergence properly | 75 shared paths, **zero identical pairs**; "delete the shadow" would lose behaviour 75 times |
| 6 | Fold the three TODO files into the Action Backlog | the one planning-artefact finding that was simply correct |


---

## Document 3 — the immune-system architecture (added 2026-09-10)

A third assessment arrived from Kagi Assistant. Reviewing it changed the verdict
on all three, and the change matters more than any individual correction.

### Its issue-level findings are accurate. All of them.

Document 3 lists eleven findings, most citing an issue number. Checked against
the live tracker:

| Cited | Real issue | Verdict |
|---|---|---|
| api-gateway routes AI traffic to legacy `tranc3-ai` | **#284** | real, correctly described |
| `path_validation.py` symlink TOCTOU in intermediate components | **#337** | real, correctly described |
| `GridDatabase`/`WorkflowEngineRouter` are module globals | **#336** | real |
| analytics-service DuckDB reseeding and ambiguous-write dedup | **#334** | real |
| GitHub Actions broken / need review | **#1180** | real |
| CodeQL cannot load the repo's own barrier models | **#995** | real |
| Freshness gate red on `main` from bot digest bumps | **#991** | real |
| `build-storybook` broken — nine PNGs never committed | **#990** | real |
| `misp-db` has no backup/restore/DR runbook | **#1146** | real |
| Supply Chain Watch census failing | **#969** | real |
| ledger-service internal/external partitioning | **#474** | real |

Eleven for eleven. The twelfth open issue is **#174**, Renovate's Dependency
Dashboard, which Document 3 also mentions.

**It enumerated the entire open backlog, correctly, and then described that
backlog as "863 open issues".** Measured: 12.

That is a much more useful reading than "most of its figures are wrong", which
is what the first review of Documents 1 and 2 concluded and what this document
said until now. The substance was read from the real tracker. The aggregates
were not read from anywhere.

### What that changes

**Act on the issue-level findings.** They are this estate's real backlog, they
are already fully enumerated, and Document 3's Epics 1–4 are a reasonable
sequencing of them. Nothing in this review contradicts that sequencing.

**Do not run the triage blitz.** Document 3's story S4.2 — "bulk-triage the
863-issue backlog into epic/bug/debt labels; adopt stale-bot and triage
rotation" — and its "chronic-debt sweeper" that "batches the 863 backlog into
curable cohorts" are work for a backlog that does not exist. The 12 issues are
already individually titled, individually described, and short enough to read in
one sitting. Building machinery to sort them would cost more than fixing them.

The metaphor Document 3 builds on that figure — "your 863-issue backlog is
chronic inflammation" — is a diagnosis of a body that is not ill in that way.
Twelve open issues against 3,118 tracked files is not chronic inflammation. It
is a small, legible list.

A note on that figure, because this document of all documents cannot be sloppy
with one. It read 3,087 in the table above and 3,102 here, and neither was
wrong when written: the two were measured at different commits of a branch that
was still adding files. But a document whose argument is *external assessments
invent their aggregates* cannot carry two different numbers for the same
quantity and expect to be believed — the reader has no way to tell drift from
invention, which is precisely the distinction it is asking them to make.
Caught by cubic on PR #1150. Both now read 3,118, measured at `cd7f22a5`, and
the commit is named so the next reader can tell a stale measurement from a
false one. It will drift again; a dated number that drifts is honest, an
undated one is not.

### Where its architecture and this estate's converge, independently

Document 3 and the work landed in this branch were produced in parallel and
arrived at the same shape: innate sensors, adaptive memory, a self-hosted grade
replacing CodeFactor, path-triage replacing the labeler, and an explicit
autoimmunity guard. That convergence is worth something — two independent passes
over the same problem reaching the same structure is evidence the structure is
the natural one.

Three of its ideas were adopted directly and are named in
`docs/governance/IMMUNE-SYSTEM.md`:

- **Churn-weighted debt** (from CodeFactor) — `severity × change frequency`,
  extended here with blast radius.
- **Clean as You Code** (from SonarQube) — grade the change, not the tree.
  Document 3 correctly identifies this as the fix for **#991**, and it is: that
  gate went red because it measured absolute state.
- **Autoimmune protection** — its phrase, and the right one. Recorded as a
  first-class concept in `src/immune/memory.py`.

### Where it goes further than what is built

Its `tranc3-immune` worker — webhook on `workflow_run` failure, diagnose from
Loki, look up a cure in a defect knowledge base, draft a fix with a local model,
validate by re-running the failing job, propose a pull request and never
auto-merge — is a real design and is **not built**. The parts exist
(`scripts/adaptive_vulnerability_remediation.py`, `scripts/apply_repairs.py`,
`src/core/mape_k.py`, `src/observability/self_healer.py`) and are not joined.

Two cautions before anyone builds it, neither of which Document 3 raises:

1. **It requires The Workshop.** "Re-run the failing job in an isolated
   self-hosted runner" needs the Citadel act-runner that the cloud-only phase
   has not stood back up. On GitHub Actions the same loop consumes exactly the
   rate-limited minutes the estate's standing policy exists to avoid.
2. **Its own guard needs the probe property.** An auto-remediation agent that
   cannot reach the model, or whose validation run silently skips, will report
   "no cure found" identically to "nothing needed curing". Every layer of this
   estate has now been caught doing that once. The agent must declare what it
   could not do, in the same vocabulary the sensors use.

### Its citation quality

Document 3 cites real, openable URLs — codefactor.io, SonarQube comparisons,
self-healing CI write-ups, an arXiv paper. That is a genuine improvement on
Documents 1 and 2, whose `[^69d993#3703-3707]` anchors point at nothing anyone
here can open.

One of those citations turned out to be directly useful: **CodeFactor's public
repository page is machine-readable without a login.** It rates this repository
A on `5c69056`, 99.4% A-grade files, and reports **zero open issues** — which is
itself a small piece of evidence that "851 CodeFactor issues" in Document 1 came
from nowhere. That page is now a standing cross-check against this estate's own
grader; see `docs/governance/IMMUNE-SYSTEM.md`.

### Standing verdict across all three

Read the findings. Ignore the totals. The pattern is consistent enough across
three independent documents to state as a rule for this estate:

> **Externally generated assessments of this repository have reliably read the
> issue tracker and reliably invented the aggregates.** Every specific,
> checkable claim about a named artefact has held up. Every count has not.

## Standing caution

Both documents cite footnotes of the form `[^69d993#3703-3707]` — internal
retrieval anchors, not sources anyone here can open. Every quantitative claim
carrying one of those anchors and checked in this review was wrong. Treat that
citation form as decoration, not provenance.

The failure mode is worth naming, because it is the one this estate keeps
finding in its own controls: **a claim whose scope outruns its evidence, with
nothing in place to notice when the gap opens.**

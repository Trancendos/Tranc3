# Review of two external assessments of Tranc3

**Reviewed** 2026-09-10, against this checkout at `2f524a15` and the live
repository on GitHub. Two AI-generated documents were supplied by the owner:

1. *Tranc3 Deep Dive — Forensic Assessment, SWOT & Remediation Roadmap*
2. *Tranc3 → Production-Ready: PLM-Style Agile Backlog & Delivery Plan*

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
| "2,259 files" | Doc 1 §3 | 3,087 tracked (`git ls-files \| wc -l`) | wrong |
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

Three separate open PRs are currently removing the same unconfigured scanner
workflows: **#1152**, **#1175** and **#1177**. #1175 modifies
`scripts/check_workflow_placeholders.py`, a file that exists only on #1152's
branch.

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

## Standing caution

Both documents cite footnotes of the form `[^69d993#3703-3707]` — internal
retrieval anchors, not sources anyone here can open. Every quantitative claim
carrying one of those anchors and checked in this review was wrong. Treat that
citation form as decoration, not provenance.

The failure mode is worth naming, because it is the one this estate keeps
finding in its own controls: **a claim whose scope outruns its evidence, with
nothing in place to notice when the gap opens.**

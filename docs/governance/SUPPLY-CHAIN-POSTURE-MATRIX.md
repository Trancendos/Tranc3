# Supply Chain Posture Matrix

> **What this is.** The owner supplied Black Duck's **2026 OSSRA report** ("Software Governance in
> the AI Era", 44 pages) and asked whether anything in it could be implemented here. This document
> is the answer, and it is deliberately not a summary of the report. A benchmark report tells you
> what a population of audited codebases looks like; it cannot tell you what *this* estate looks
> like. So every claim in the report that could be turned into a measurement was turned into one,
> run against the actual repository, and recorded below next to the report's own figure — including
> the places where we came out worse than the industry average, and the one place where the report's
> own wording turned out to be inaccurate enough to have led us into a mistake.
>
> Same discipline as [SECURITY-POSTURE-MATRIX.md](SECURITY-POSTURE-MATRIX.md), which did this for
> CrowdStrike's 2026 Global Threat Report: verify against real code, state plainly what was found,
> what was built, and what is still an honest gap.

**Owner:** The Guardian (Marcus Magnolia) (Security pillar Steward AI, SUITE-SEC) ·
**Version:** 1.1.0 · **Last verified:** 2026-08-21

---

## 1. What a benchmark report can and cannot do for us

OSSRA's population is commercial codebases submitted to Black Duck's audit service — typically
because someone is doing due diligence on them. Trancendos is a single-operator, zero-cost,
self-hosted platform that has not yet been placed on any market. The population averages therefore
predict nothing about us in either direction, and quoting them at ourselves would be theatre.

What the report *is* genuinely good for is a **checklist of questions worth asking**, several of
which we had never asked. That is the value that transferred. Six of its themes turned into six
measurements; four of those measurements did not previously exist as anything, and building them
found real defects.

**What did not transfer:**

- The audit-services framing (snippet matching, binary analysis, manual review) assumes a paid
  engagement. `CLAUDE.md`'s zero-cost principle rules it out, and saying so is more useful than
  listing it as a "future consideration".
- Most of the industry-vertical breakdown (EdTech at 100%, Semiconductors at 59%) is interesting
  and inapplicable — Trancendos is not in any of the audited verticals in a way that would make the
  comparison mean anything.
- The final third of the report is Black Duck selling Black Duck (the portfolio pages, and "Signal").
  Recorded here as noted-and-skipped rather than pretended into a roadmap item.

## 2. The report's claims, measured against this estate

Every "Ours" figure below is a live measurement from a script in this repository, re-run on
2026-08-19. Where our figure is worse than the report's, it is shown as worse.

| # | OSSRA 2026 claim | Their figure | Ours, measured | Verdict |
|---|---|---|---|---|
| 1 | Codebases containing open source | 98% | 100% | No news. The interesting number is never *whether* |
| 2 | Codebases with at least one vulnerability | 86% | **0 fixable, 1 accepted** (`ecdsa` PYSEC-2026-1325, documented in `SECURITY_ALERT_REGISTER.md`) | Better — but only because the estate is small and the gate is real. `scripts/vulnerability_census.py` + the production gate |
| 3 | Components per application (mean) | 1,180 | **110 direct** across 6 manifest surfaces (59 pip, 51 npm — 46 of the npm in `web/`) | Much smaller. Scale is our advantage, and it is worth spending rather than banking |
| 4 | Share of components that are transitive | 64% | **90%** (`web/package-lock.json`: 46 declared, 458 resolved) | **Worse than the industry figure.** See §4 — this is our largest measured blind spot |
| 5 | Codebases with components 4+ years out of date | 92% | 1 of 110 direct deps (`pyswarms`, 2,053 days) | Better, and *measured* rather than assumed — `scripts/obsolescence_census.py` |
| 6 | Codebases with components showing no development in 2+ years ("zombies") | 93% | 5 stranded, **0 zombie** of 110 | Better. All 5 carry a written disposition in `OBSOLESCENCE-ACCEPTED.md` |
| 7 | Components not on the latest version | 93% | 10 lagging of 110 | Better. Renovate covers the routine case |
| 8 | Organisations shipping open-source AI/ML models | 49% | **Yes** — 6 model families, 16 references, 2 hosted providers | Applies to us. Nothing in any manifest named them until `config/ai_models.yaml` existed |
| 9 | Licence conflicts at an all-time high | max 2,675 in one codebase | 0 conflicts; **1 non-permissive licence family** (Llama Community) | Applies differently: our issue is an unmet *obligation*, not a conflict |
| 10 | Components found outside package management | 16% | Unmeasured | **Honest gap.** All our scanners are manifest-based, so this 16% is invisible to every control below |

## 3. Six controls, and what each one is allowed to fail on

The response was six pieces of work, five of them new. Each is described here by what it *cannot*
tell you, because that is the part that gets forgotten.

| Control | Code | Answers | Cannot answer |
|---|---|---|---|
| Vulnerability census | `scripts/vulnerability_census.py` | "Is a fixable CVE open in any declared surface?" across 6 manifests | Anything about a component that arrived outside a manifest |
| Security score gate | `scripts/security_score.py` | Caps the production score below green whenever a fixable CVE is open **or the census could not be read** | Whether the fix is safe to apply |
| Obsolescence census | `scripts/obsolescence_census.py` | Two axes — upstream liveness × our lag — over 110 direct deps | Transitive components (§4) |
| AI-BOM | `scripts/ai_bom.py` + `config/ai_models.yaml` | Which models we consume, under what licence, executing where, with what data egress | Model *weights* provenance; whether a hosted provider swapped the model behind a route |
| Install-hook hardening | `--ignore-scripts` in every CI npm install | Blocks the step Shai-Hulud and PhantomRaven execute in | Anything that runs at import rather than install |
| CRA profile | `compliance/magna-carta/docs/compliance/EU-CRA-PROFILE.md`, MC-042–MC-047 | Which obligations bind, when, and what evidence exists | Nothing about MC-045 — it is recorded as an unstarted gap, deliberately |

Full detail lives in [AI-BOM.md](AI-BOM.md), [OBSOLESCENCE-ACCEPTED.md](OBSOLESCENCE-ACCEPTED.md),
and the CRA profile. This document is the map between them.

## 4. The finding that matters most: 90% of our npm surface is transitive

The report's 64% figure is an average. `web/package-lock.json` declares **46** dependencies and
resolves **458** packages — 90% of what actually installs was never chosen by anyone here.

That number is worse than the industry average, and it is the honest scope limit on almost
everything above:

- The obsolescence census walks **direct** dependencies. That is enough for the CRA's Annex I SBOM
  floor, which asks for "top-level dependencies", and it is **not** the full reach of Art. 13(5),
  whose due-diligence duty covers integrated components generally. MC-044 is marked partial for
  exactly this reason rather than being allowed to look complete.
- The vulnerability census reads manifests, so a CVE in a transitive package is caught only if the
  scanner's own resolution reaches it — which for `pip-audit` against an unhashed
  `requirements.txt` is a weaker guarantee than it looks.

Why it isn't simply fixed today: a transitive maintenance-trajectory census means ~458 registry
lookups per run for the npm surface alone, against registries that rate-limit. `CLAUDE.md`'s
standing policy is to avoid exactly that kind of sustained external call. The honest answer is that
this needs a cache and a budget, not a bigger loop — see §8, item 1.

## 5. Where the report itself was wrong, and it cost us

Page 24, on the CRA's 24-hour clock:

> "Initial notification within 24 hours of becoming aware of a vulnerability known to be exploitable
> (e.g., proof-of-concept code is available)"

The parenthetical is not the legal test. Article 14(1) attaches to a vulnerability that is **being
actively exploited**. Published proof-of-concept code is evidence that a vulnerability *could* be
exploited — a different and far more common event. An organisation that adopted the report's gloss
would start a 24-hour regulatory clock on a large number of occasions where no clock is running.

The first draft of MC-045 copied that gloss verbatim. It was caught in review, corrected against the
regulation text, and the correction is now recorded in the register entry itself rather than quietly
edited out. Two related corrections came from the same round: the severe-incident final report runs
one month from the **submission** of the incident notification (Art. 14(4)(c)), not from the expiry
of the 72-hour window; and a manufacturer does not "designate a CSIRT" — Art. 14(7) routes the
notification to the coordinating CSIRT of the Member State of the manufacturer's *main
establishment*.

**The rule this leaves behind:** a benchmark report is a source of questions, never a source of
legal wording. Where a control encodes a deadline, the citation goes to the regulation.

## 6. The design rule that runs through all six controls

Every one of these controls draws the same distinction, and it is the reason they are usable rather
than ignored:

> A **reviewed** risk passes. An **unexamined** risk fails.

- `SECURITY_ALERT_REGISTER.md` — an accepted CVE passes; an undocumented one caps the score.
- `OBSOLESCENCE-ACCEPTED.md` — a dormant component with a written disposition passes; one without
  fails the gate.
- `config/ai_models.yaml` — a declared model passes; a model that appears only in code fails the
  drift check.

The alternative design — a threshold that simply fails on any dormancy, any CVE, any model —
produces a report full of `clsx` and gets muted within a month. The register is what makes the gate
survivable, and the gate is what makes the register get written.

## 7. Fail-closed, and the defect class that made it necessary

Every one of these tools was written against a specific failure that kept recurring during this
work: **a tool reporting "clean" while having read less than it claimed, and exiting 0.** It
happened more than ten times across the session, in different forms — a truncated registry response,
a scanner that skipped an unreadable manifest, a regex that matched an f-string format spec
(`phi:.2f`) and a cache key (`llama3.2:user`) and called them models.

So each control is built so that **an unknown renders as unknown**:

- The census reports `errored` surfaces separately from clean ones, and the security score is capped
  whenever the census file cannot be read at all — a missing census is treated as a failure, not as
  a pass.
- The obsolescence census counts errored packages and fails the gate on them. During development,
  wrangler's ~29 MB npm document truncated mid-read; it was correctly reported as errored rather
  than healthy. (The underlying bug — `http.client.IncompleteRead` descends from `HTTPException`,
  **not** `OSError`, so it escaped a retry loop catching `OSError` — was then fixed. Fail-closed is
  what surfaced it.)
- The AI-BOM emits a Llama licence as CycloneDX `license.name`, never `license.id`, because
  expressing `llama3.2` as an SPDX identifier would file a non-OSI licence alongside Apache-2.0 —
  reproducing, inside the BOM, the exact confusion the BOM exists to prevent.

## 8. Forward posture — ranked, with the reason each sits where it does

Ranked by risk reduction per unit of effort, not by appeal.

**1. Transitive maintenance census, cached.** The largest measured gap (§4) and the one the CRA's
Art. 13(5) actually reaches. The shape that works within the zero-cost constraint: a local,
content-addressed metadata cache keyed by `(ecosystem, name, version)` with a long TTL, so a weekly
run re-fetches only what changed. Registry metadata for a *released* version is immutable, which
makes it near-perfectly cacheable — the cost is one cold run, not one run per week. Natural home:
**The Artifactory** (`workers/artifactory-service/`, port 8047), which already fronts an OCI registry
and is the only service in the estate whose job is already "hold artefact metadata durably".

**2. Hash-pinned Python lockfiles.** All 59 direct pins in `requirements.txt` are exact (`==`) —
better than most estates manage — but across the four root requirements files **79 exact pins carry
zero `--hash=` between them**, and transitive versions are not pinned at all. That is precisely the
gap `npm ci` closed on the JavaScript side in the work this document accompanies: an exact version
pin says *which release* to fetch, a hash says *which bytes*, and only the second survives a
compromised or re-uploaded artefact.

An earlier revision of this section costed this at "half a day". **That was wrong, and the correction
matters**, because half a day reads as a quick win somebody should just do. Measured on 2026-08-21:

| | Count |
|---|---|
| Root requirements files | 4 (79 exact pins, 0 hashes) |
| Worker requirements files | 84 |
| Install paths invoking `pip install -r` | 114 |
| Resolved distributions behind those pins | ~266 |

The reason those numbers bite is that **`--require-hashes` is all-or-nothing per invocation**: if a
single requirement in the file lacks a hash, the install fails outright. So it cannot be applied
incrementally *within* a file, and every one of the 88 requirements files needs its own compiled
lockfile before the flag can be turned on anywhere that reads it. The transitive tree also has to be
pinned as a side effect — which is a genuine improvement (§4's blind spot narrows) and a genuine
increase in upgrade friction, since Renovate then has a lockfile to regenerate rather than a line to
bump.

The staged path that avoids a big-bang change:

1. `pip-compile --generate-hashes` (or `uv lock`) on the **four root files only**, emitting
   `requirements.lock` alongside rather than replacing the existing `.txt`. Nothing breaks, because
   nothing reads the new file yet.
2. Switch the **production gate** — one install path, the one that matters most — to the lock with
   `--require-hashes`, and leave the other 113 alone. This is where the integrity return actually
   lands, because it is the path that produces a release.
3. Extend to workers **only if** step 2 holds through a full Renovate cycle without becoming a
   maintenance tax. The per-worker return is much lower: workers install from pinned root-aligned
   sets already (`scripts/align_framework_pins.py`), so they inherit most of the benefit.

Steps 1–2 are a day or two, not half a day, and step 3 should be a separate decision taken with
evidence from step 2 rather than committed to up front. **Not started** — the staging is the
recommendation, not a completed plan.

**3. Per-release SBOM retention.** SBOMs are generated today (syft, dual-format, in
`security-scan.yml`) but retained as CI artefacts on a rolling window. MC-042 is partial for this
reason. The CRA expects the SBOM for a *released version* to remain current and available across the
support period. This is the prerequisite that makes a 24-hour "which shipped versions contain
component X?" answer a lookup rather than a scan — enabling MC-045 without gating it, since the
Art. 14 clocks run from awareness regardless.

**4. Advisory intake wired to the inventory.** Today a new CVE reaches us through Dependabot and a
weekly scheduled scan. The 24-hour standard is a *lookup* interval, not a *scan* interval: a process
that begins by running a scan cannot meet it. **Cryptex** (`src/cryptex/`, threat intel) is the
existing home for advisory intake, and the EUVD is the feed the CRA itself points at. Wiring
EUVD/OSV intake → inventory lookup → escalation FSM is the difference between a control that exists
and a clock that runs.

**5. "Built with Llama" attribution.** The one *currently unmet* licence obligation in the estate
(AI-BOM §4). It applies from first release, costs an afternoon in Arcadia's footer or an
about/credits panel, and is awkward to retrofit into a released UI and a published set of
screenshots. Cheap now, annoying later — the definition of a pre-go-live item.

**6. Model-integrity verification.** The AI-BOM records *which* models we consume; it does not
verify that the artefact we pull is the one we recorded. OSSRA's model-risk section notes models can
be "modified from origin". Pinning a Hugging Face revision SHA (rather than `main`, which
`src/search/query_expansion.py` currently uses for `t5-small`) is the cheap first step, and it is a
one-line change with a real integrity return.

**7. The 16% blind spot.** Components arriving outside package management — vendored code,
copy-pasted snippets. Genuinely unmeasured here. A full answer needs snippet matching, which is a
paid capability. A partial, zero-cost answer exists: flag vendored directories and large unattributed
source files for human review. Listed last because it is the least tractable, not because it is the
least real.

## 9. Automation and connectivity — what runs, when, and how it fails

The user's brief asked for proactive management, automation and connectivity rather than documents.
This is the honest state of that, including where the connection is a plan rather than a wire.

| Control | Trigger | Cadence | Gate | Failure mode |
|---|---|---|---|---|
| Vulnerability census | PR + production gate | every PR | blocks green | fail-closed (unreadable census caps the score) |
| Security score | production gate | every PR | blocks release | fail-closed |
| Vulnerability census (scheduled) | `supply-chain-watch.yml` (GitHub) | daily 05:00 UTC | alerts, does not gate | fail-closed; failure opens a tracking issue |
| Obsolescence census | `supply-chain-watch.yml` (GitHub) | weekly Mon 05:30 UTC | `--fail-on stranded` | fail-closed on errored packages |
| Obsolescence census (twin) | `dependency-audit.yml` (Forgejo) | weekly + on manifest change | `--fail-on stranded` | **dormant — see below** |
| AI model drift | `ci.yml` topology job | every PR | blocks merge | fail-closed (code-only model fails) |
| Dependency override sync | `ci.yml` topology job | every PR | blocks merge | fail-closed |
| Install-hook blocking | all CI npm installs | every run | n/a — preventive | n/a |
| CRA obligation review | `legislation_register.yaml` | scheduled review + go-live gate | go-live gate | manual |

Three deliberate placements worth stating:

- **The obsolescence census is weekly and manifest-triggered, not per-PR.** It is network-dependent
  and fail-closed, which is the right combination for a scheduled job and the wrong one for a PR
  gate: a transient npm outage must not redden an unrelated pull request. Obsolescence also arrives
  *without a commit* — a component crosses the dormancy line while nobody touches the repo — so a
  commit-triggered check would structurally miss the thing it exists to catch.
- **The scheduled scans run on GitHub, against standing policy, because the alternative was not
  running at all.** This is stated plainly in §9.1 rather than buried, because it is a deliberate
  exception to the avoid-GitHub-Actions rule and should be revisited when The Workshop returns.
- **The AI-BOM lands inside the existing SBOM pipeline**, as CycloneDX 1.6 `machine-learning-model`
  components feeding the same Dependency-Track upload, rather than beside it. One supply-chain
  inventory, not two.

### 9.1 Built, running, and not running — the runner dependency

There is a third category between *built* and *planned*, and this estate sat in it: **built, wired,
and dormant**. It is worth separating out because it reads as coverage on paper and provides none.

GitHub reads only `.github/workflows/`; it never reads `.forgejo/workflows/`. Measured on
2026-08-21:

| | Workflow files | Scheduled | Observed firing |
|---|---|---|---|
| `.github/workflows/` | 17 | 5 | yes — 74 scheduled runs in the visible window |
| `.forgejo/workflows/` | 33 | 16 (14 needing `runs-on: self-hosted`) | no — The Workshop is awaiting server funding |

Every scheduled supply-chain control lived in the second row. The scans were correct, fail-closed,
well-triggered — and had no runner. That is the same defect class §7 describes: a control that
exists, reports, and does not fire. It is easier to miss here than in code, because a workflow file
looks identical whether or not anything executes it.

`supply-chain-watch.yml` is the narrow correction: the two measurements whose answer changes with
the passage of time rather than with a commit, on GitHub's runners, alerting rather than gating. The
Forgejo originals keep their broader job set and are left in place, so that when The Workshop is
deployed the two run side by side as cross-verification — the pattern `bot-health-watchdog.yml`
already established — rather than one silently replacing the other.

**This was not hypothetical.** The first live run of the new daily census found a fixable
vulnerability (`datasets` PYSEC-2026-3716) that the 19 August census had not seen, because it was
disclosed after that run. Renovate — a GitHub App, and therefore one of the few proactive controls
actually executing — had already patched it on `main` in #840. The lesson is not that the estate was
exposed; it is that between two commits on a branch, the *only* thing that noticed was a control
running on infrastructure that happened to be up.

**Connectivity that is planned, not built** — named here so it is not mistaken for existing: Cryptex
advisory intake → inventory lookup (§8.4); The Artifactory as the transitive metadata cache (§8.1);
the escalation FSM as the Art. 14 clock; **The Observatory** as the immutable record of a
notification having been sent; `/roles` for a CRA Reporting Officer; CranBania for the SLA card.
Each of those is a *candidate* mapping based on what the service is for. None has been verified
against what the service actually does, and each needs that check before it is scheduled as
integration work.

## 10. What is deliberately not being done

- **Paid SCA tooling**, including Black Duck's own. Rules out snippet matching and binary analysis,
  which is the honest reason §2 item 10 stays unmeasured.
- **Quarterly external penetration testing.** Already listed as a recommendation in
  `ARCHITECTURE_THREAT_MODEL.md` §8.3 and still not realistic at zero budget with one operator.
  Repeating it here as a plan would not make it one.
- **A dormancy threshold with no register.** Considered and rejected — see §6.
- **Failing PRs on obsolescence.** Considered and rejected — see §9.

## 11. Review triggers

Re-read this document when any of the following happens, rather than on a calendar:

- The next OSSRA edition, or an equivalent benchmark, is published — and re-measure rather than
  re-quote.
- Anything is placed on a market. Several rows above are scoped by the fact that nothing is
  released yet; that scoping expires on the day it stops being true.
- A transitive census exists — §2 item 4 and §4 both need rewriting when it does.
- A model family is added, or an existing variant's size changes. The Qwen family is not uniformly
  Apache-2.0 across sizes, so that is a licence question wearing the costume of a config tweak.
- **11 September 2026** — CRA Article 14 reporting becomes mandatory. The nearest hard date in this
  document.

## Related

- [SECURITY-POSTURE-MATRIX.md](SECURITY-POSTURE-MATRIX.md) — the same exercise against CrowdStrike's
  2026 Global Threat Report
- [AI-BOM.md](AI-BOM.md) · [OBSOLESCENCE-ACCEPTED.md](OBSOLESCENCE-ACCEPTED.md) ·
  [BOM-MATRIX.md](BOM-MATRIX.md)
- `compliance/magna-carta/docs/compliance/EU-CRA-PROFILE.md` — obligation mapping, MC-042–MC-047
- `SECURITY_ALERT_REGISTER.md` — accepted vulnerabilities

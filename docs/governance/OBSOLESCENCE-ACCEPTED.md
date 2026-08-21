# Obsolescence — Accepted Components

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-08-19

This register records dependencies that `scripts/obsolescence_census.py` reports as
**dormant** — no upstream release in 730 days or more — together with the decision to
keep carrying each one.

## Why a register rather than a threshold tweak

A quiet project is not automatically an abandoned one. Small, finished libraries stop
releasing because there is nothing left to fix; that is maturity, not neglect. If the
census treated every silence as a defect, the report would fill with `clsx` and be
ignored — which is the outcome it exists to prevent.

So the census does not decide. It states a checkable fact ("no release in N days") and
asks for a human judgement once, here. A dormant dependency that appears in this file is
a **reviewed** risk; one that does not is an **unexamined** one, and the CI gate only
fails on the second kind. That is the same distinction `SECURITY_ALERT_REGISTER.md` draws
between an accepted vulnerability and an ignored one.

## What the states mean

| State | Meaning | Register expectation |
|---|---|---|
| `healthy` | Upstream is releasing; we are current | not listed |
| `lagging` | Upstream is releasing; we are ≥365 days behind | not listed — this is our work, tracked by Renovate |
| `stranded` | We hold the latest release; upstream has gone quiet | listed, with a disposition |
| `zombie` | We are behind **and** upstream has gone quiet | listed, and normally remediated rather than accepted |

## Dispositions

`ACCEPT` — the dormancy is understood and tolerable; no action planned.
`MONITOR` — tolerable today, but the trajectory is a concern; revisit on the stated date.
`EXIT` — a replacement or removal is planned; the date is the target.

---

## Accepted components

| Package | Ecosystem | State | Last release | Disposition | Reasoning |
|---|---|---|---|---|---|
| `clsx` | npm | stranded | 848d | ACCEPT | A ~200-line className concatenator with a single, fully-specified job and no network, filesystem, or parsing surface. Used once, in `web/src/lib/utils.ts`, behind `twMerge`. There is no plausible future release because there is no remaining behaviour to add. Replacement is trivial (the function is a one-liner) if it ever becomes necessary, so the lock-in risk is nil. |
| `openpyxl` | pip | stranded | 782d | ACCEPT | Build-time tooling only — its sole importer is `scripts/build_master_service_matrix.py`, which generates the EA workbook `.xlsx`. It is not imported by `api.py`, any worker, or any runtime path, so it ships in no product placed on any market and carries no CRA support-period obligation. A vulnerability would be reachable only by whoever is already running our build. Release cadence has historically been sporadic rather than terminal. |
| `defusedxml` | pip | stranded | 1055d | ACCEPT | Deliberately complete: a small hardening shim whose entire purpose is to refuse the XML features that make parsers dangerous. "No new features" is the intended end state for that kind of library, not a warning sign. Single use site — `src/monetisation/billing.py:729`, annotated `# nosec B405` — parsing provider callback payloads. **Caveat worth stating:** it is a *security* dependency, so dormancy matters more here than for a utility. If it ever fails on a newer Python, the exit is to stdlib parsing with the equivalent entity/DTD restrictions applied explicitly rather than to seek another shim. |
| `ncps` | pip | stranded | 734d | MONITOR — revisit 2027-02 | Liquid/closed-form-continuous-time networks (`CfC`, `AutoNCP`) used by `src/personality/lnn.py`. Only just crossed the 730-day line, so "dormant" is currently a threshold artefact more than an established trend; a research library going a couple of years between releases is unremarkable. Imported inside a `try`, so absence degrades rather than breaks. Revisit in six months: if there is still no release, reclassify as EXIT and plan the removal, since an unmaintained numerical library is not something to discover a CVE in. |
| `pyswarms` | pip | stranded | 2053d | **MONITOR — revisit 2026-11** | The genuine concern in this list. Five and a half years without a release is past any reasonable reading of "mature" and into unmaintained. Used for particle-swarm optimisation in `src/evolution/adaptive_tuner.py`, behind an optional import, so the blast radius is bounded and the estate already runs without it. It is accepted **only** because that import is optional and the code path is not on any request-serving route. It is not accepted as a healthy dependency. If a vulnerability is ever disclosed against it there will be no upstream fix, and the answer will be removal, not a patch — so the standing plan is to treat the optional import as the exit ramp it already is. |

---

## Review cadence

The census runs in CI on every pull request, so a **new** dormant component fails the
build the day it crosses the threshold and cannot accumulate unnoticed. This file is for
the ones already reviewed.

The entries themselves need periodic re-reading, because a disposition written against a
784-day dormancy means something different at 1,500 days. Re-verify on each `MONITOR`
date above, and re-read the whole file at least annually.

## Relationship to the EU Cyber Resilience Act

The CRA expects a manufacturer to evaluate a component's maintenance trajectory *at
selection time* and to track it continuously thereafter, across a support period of at
least five years. This register plus the census is that evidence: the census supplies the
continuous measurement, and this file supplies the recorded judgement. See
`docs/compliance/EU-CRA-PROFILE.md` for the full obligation mapping.

Note the scope distinction the CRA cares about and that this table already makes:
`openpyxl` is build-time tooling, not a component of a product placed on the market, and
is annotated as such.

## Adding an entry

1. Run `python scripts/obsolescence_census.py` and confirm the component's state.
2. Establish what it is actually used for and whether that path ships.
3. Add a row with a real reason. "Still works" is not a reason — the question is what
   happens when it stops, or when a CVE lands and no one is there to fix it.
4. Choose `MONITOR` with a date over `ACCEPT` whenever the honest answer is "probably
   fine, but I would want to look again".

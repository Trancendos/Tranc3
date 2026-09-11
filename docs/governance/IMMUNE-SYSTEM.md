# The Immune System

**Measured** 2026-09-10 against `claude/cloud-only-production-ready-25usvd`.
Every figure below was produced by a command named beside it.

## The instruction

Three workflows were deleted from this estate because they needed an account it
does not have: `policy-validator-cfn` wanted an AWS role, `defender-for-devops`
wanted an Azure tenant and a `windows-latest` runner, and CodeFactor's detail
sits behind a login. Deleting them removed the cost and did not replace the
capability.

The owner's instruction was to learn what those systems actually do and build it
here — generic, independent, zero-cost — and framed it this way:

> Think of GitHub Actions at the moment like white blood cells (antibodies) and
> Trancendos as the Person. The code you're placing in is good and bad food,
> experiences and items — these aspects contain bugs or issues. The GitHub
> Actions are there to help reduce damage and stop illnesses. We need our white
> blood cells to be able to protect our bodies and carry on learning and
> experiencing things to grow and develop.

That framing is not decoration. It is a good engineering model, and it has been
followed literally, including the parts of immunology that are inconvenient.

## The one property that separates this from what it replaces

An immune system that is present but unresponsive is called **anergic**. From
outside, an anergic body and a healthy body look identical: no inflammation, no
fever, nothing to report. The difference only shows when something arrives that
should have been fought.

Every scanner this estate deleted had that shape, and so do most that remain:

| Failure | What the tool reports | What is true |
|---|---|---|
| `npm audit` against a soft registry failure | `{"vulnerabilities": {}}`, exit 0 | nothing was checked |
| `pip-audit` behind a blocked proxy, with `\|\| true` | job green | nothing was checked |
| MSDO with no Azure onboarding | no new alerts on the Security tab | nothing was uploaded |
| CodeFactor on a private repo without the app | no issues | nothing was analysed |

**A sensor that cannot see reports exactly what a clean estate reports.** Closing
that is the whole design.

### Probes

`config/immune/sensors.yaml` lets a sensor declare a **probe**: a known defect,
planted in a temporary directory, that the sensor must flag. Only clean runs are
probed — a sensor that found something has already demonstrated it can see, and
probing it would spend a subprocess to learn nothing.

A sensor that reports the real tree clean **and** fails its own probe is recorded
`blind`, and a required blind sensor fails the run.

Calibrated with two sensors that are identical in every observable way:

```
liar      -> blind   blocking=True   probe planted a known defect and the sensor reported clean
unprobed  -> ok      blocking=False  clean; no probe declared
```

Same command. Same empty output. Same exit code. Only the probed one is caught.
Every commercial scanner in the deleted set was permanently in the second state,
at any price.

This generalises the npm registry canary already in
`scripts/vulnerability_census.py` from one scanner to every sensor in the
manifest.

## What each vendor taught, and what was built instead

### AWS IAM Access Analyzer → the baseline

The deleted `policy-validator-cfn` ran three checks. Two are AWS-specific.
The third, `CHECK_NO_NEW_ACCESS`, is a general idea worth more than the tool:
*compare a policy against a committed reference and fail if the new one grants
more.* Not "is this good" — **"is this worse than what we already agreed".**

`config/immune/baseline.json` is that reference, generalised from IAM policies
to every finding the estate can produce. New findings fail the gate; existing
ones do not, because a gate that fails on the backlog fails on every pull
request and gets bypassed rather than satisfied.

Three ways it declines to cry wolf, each of which was a defect in an earlier
draft of this code:

- **Fingerprints exclude the line number**, so a finding survives code moving
  down the file. That collapses repeats, so occurrences are counted as well: a
  fourth instance of a rule the baseline saw three times *is* new.
- **Findings from a sensor the baseline never ran are reported and not gated.**
  A newly installed scanner's first output is a first measurement, not a
  regression by whichever pull request happened to run next.
- **`sensor` (which instrument) is tracked separately from `tool` (what that
  instrument calls itself)** and excluded from the fingerprint, so a vendor
  renaming its SARIF driver cannot orphan a baseline.

### Microsoft Security DevOps → SARIF as one bloodstream

MSDO's value was never the analysers it bundled; this repository already runs
ruff, bandit, semgrep, gitleaks, trivy, pip-audit and CodeQL. Its value was
making them **speak one language and report to one place**.

SARIF 2.1.0 is that language, it is an OASIS standard, and it has no vendor
attached. `src/immune/sarif.py` normalises every sensor's native output:
severity vocabularies onto four levels, paths onto repo-relative form, and
rule-level severity read when a result omits its own.

What MSDO does not do, and this does: **refuse to absorb an unreadable file.**
`load_sarif` raises `SarifUnreadable` rather than returning an empty run,
because an empty run is indistinguishable from a clean scan and would be
believed.

### CodeFactor → a grade that shows its working

CodeFactor's four real products are an A–F grade, new-vs-fixed per change,
churn-weighted debt, and a worst-files list. All four are reproducible from
findings the estate already has. `src/immune/grade.py` computes them with a
formula written in Python that prints its own arithmetic:

```
grade         A
density       0.046 weighted findings per 1,000 lines
weighted      36.0 from 36 finding(s)
lines counted 788,195 across 3,044 graded file(s)
weights       error=10, warning=3, note=1
thresholds    A<=2, B<=5, C<=10, D<=20, else F
```

Three things it does that the vendors do not:

**It grades the change, not the tree.** A whole-repository grade barely moves
whatever you do, so it stops carrying information and reviewers stop looking.
`--changed-only` grades the files this change touched. This is the principle
SonarQube calls *Clean as You Code*, and it is also the fix for a defect this
estate has hit for real: a freshness gate that measured absolute state went red
on `main` because a bot bumped a digest, blocking pull requests that had touched
nothing. **Gates must measure change, not state.**

**It refuses to claim more than it saw.** Any *required* sensor that came back
blind, failed, absent or unreadable caps the letter at C and marks it
provisional. The first version of this file capped on `blind` alone and printed
`grade A` on a run whose required security sensor had exited 2 without scanning
a single file.

**It ranks debt by what keeping it costs**, not by count:
`severity × how often the file changes × how many modules import it`. The middle
factor is CodeFactor's churn weighting; the third is this estate's addition.

```
195.0  F  src/nanoservices/self_deployment_agent/self_deployment_agent.py  (15 × 12 changes × 0 importers)
 72.0  C  src/platform/intelligent_scanner.py                              (4 × 5 changes × 2 importers)
 48.0  C  src/cryptex/bounty_hunter.py                                     (3 × 7 changes × 1 importers)
```

#### Keep reading CodeFactor anyway

CodeFactor's **public** repository page is machine-readable without a login. It
rates this repository **A** on commit `5c69056`, with 99.4% A-grade files, 0.4%
B, 0.1% F, and zero open issues.

This grader, independently, over a different sensor set, says **A** with 99.8%
A-grade files.

Two different formulas agreeing is worth more than either alone. The point of
building your own grade is not to stop reading a free public one; it is to stop
*depending* on it, and to have something to compare against when it moves. The
divergence (99.4% vs 99.8%) is real and expected — different sensors, different
rules — and it is the number to watch, not the letter.

### `actions/labeler` → triage that knows what a path means

`label.yml` runs on `pull_request_target`, which reads the workflow **and its
configuration** from the base branch. A pull request that creates or fixes
`.github/labeler.yml` therefore cannot make its own check pass. That is not a
bug in the action; it is the security model working as designed. But it means
the check stays red until the change merges, and a check that is always red
teaches reviewers to ignore red.

`scripts/triage_change.py` runs inside `ci.yml` on `pull_request`, against the
pull request's own tree. It reads **the same `.github/labeler.yml`** — one
vocabulary, not two, because two vocabularies for the same question diverge and
the divergence is invisible since each looks correct alone — and adds what a
path glob cannot know:

- **Which of the 43 Locations the change lands in**, derived from
  `src/entities/platform.py`'s `worker_path` rather than a second hand-kept
  list, so a Location whose path moves is re-attributed automatically.
- **Which declared risk surfaces it crosses** — the merge gate, a suppression
  file, auth, secret custody, routing, dependency pins, the entity register —
  each with a written reason a reviewer can act on.

It applies no labels and needs no token. It writes to the job summary, which is
free, works on forks, and cannot be blocked by a permissions model. `label.yml`
is kept; it will apply labels normally once this merges.

## What building it found

Not a plan. Things that were true, that nothing was looking at.

### 1. Bandit's `# nosec` is token-matched, so English can disable it

The first calibration probe carried this comment beside a deliberate shell
injection:

```python
return subprocess.call(user_input, shell=True)  # nosec-free on purpose
```

bandit 1.9.4 reported B404 (importing subprocess) and said **nothing** about
B602 (the shell injection, HIGH severity). Measured: bandit splits comments on
non-word characters, so `nosec` followed by a hyphen is still the token.
`# nosec-free`, `# nosec-style`, `# nosec: see ticket` all silence the line.
`# nosecure` does not — that is one word.

A phrase in English can disable a security check, and the check's own silence is
the only evidence.

`scripts/check_nosec_specificity.py` enforces that every suppression names the
rule it silences and says why, in two severities:

| | Count | Treatment |
|---|---|---|
| Bare `# nosec` — silences **every** rule on that line, forever | **0** | Blocking. The job is to keep it at zero |
| Names a rule, gives no reason | **80** | Ceiling in `config/immune/nosec_ceiling.txt` — may fall, may not rise |
| Names a rule and gives a reason | **267** | Fine |

The README describes "80 documented nosec suppressions". Measured, 80 is exactly
the count of the **un**documented ones. Nobody wrote that deliberately; it is a
figure that was true of something once and kept its wording.

### 1a. The cross-check earned its keep on the first day

CodeFactor's public page went from **5 issues to 7** the moment the immune
system landed. Two of the seven were functions written that afternoon:
`scripts/immune_scan.py:main` and `scripts/check_nosec_specificity.py:main`.

This estate's own grader said **A** and saw neither. Asking why found something
worth more than the two functions.

All seven CodeFactor findings are one rule — cognitive complexity. Nothing in
this estate's sensor set measures it. ruff *can*, via `C901`, and
`pyproject.toml` said this:

```toml
"C901",   # complexity — warned, not blocked
```

**It was not warned either.** An `ignore` entry means ruff never runs the rule,
so nothing warned anywhere. Measured:

| max-complexity | Functions over it |
|---|---|
| 10 (ruff default) | **183** |
| 15 | 43 |
| 20 | 14 |
| 30 | 7 |

One hundred and eighty-three functions exceed the default threshold and no
control in this estate has ever reported one of them. The comment described a
warning that does not exist — a control labelled as on, and off.

That is the same defect class as everything else in this document, and it was
found by keeping a free vendor grade to compare against rather than only
replacing it. **The point of a second opinion is the disagreement.**

**What was done.** `C901` stays ignored in `pyproject.toml`, because 183 lint
errors on every pull request is a gate people bypass rather than satisfy — the
same reasoning as the nosec ceiling. It is measured instead, by a `complexity`
sensor in `config/immune/sensors.yaml` at a threshold of 20: reported,
baselined so it cannot grow, ranked by churn. The comment now says what is
true.

The three functions this work itself added were fixed rather than baselined.

And the ranking immediately said something a raw count cannot:

```
10944.0  A  api.py   (weight 3 x 151 changes x 23 importers)
  825.0  B  Dimensional/hive/hive_core.py   (weight 3 x 24 changes x 10 importers)
  780.0  B  Dimensional/nexus/nexus_core.py  (weight 3 x 25 changes x 9 importers)
```

`api.py`'s `lifespan` scores 53 against a threshold of 20, has changed 151 times
in six months, and is imported by 23 modules. It is not the most complex
function in the estate and it is comfortably the most expensive one to keep.

### 1b. A gate that would have failed everywhere except here

Calibrating the complexity sensor — planting a deliberately tangled function
and checking the gate went red — worked, and the failure line read:

```
NEW warning C901   home/user/Tranc3/src/immune/_cx_probe.py:1
```

That path is wrong, and the way it is wrong matters. **ruff always reports
absolute paths.** A finding's fingerprint includes its path, so an un-stripped
checkout prefix makes the fingerprint machine-specific: a baseline written on a
laptop under `/home/user/Tranc3` matches nothing on a runner under
`/home/runner/work/Tranc3/Tranc3`, and **every finding reads as new**.

The gate would have passed here and failed on every pull request in CI, for a
reason nobody reading the output could see. `_relativise` now strips the
checkout root, and falls back to cutting through the last segment matching the
repository's directory name — which handles the runner's doubled layout and a
container mount alike. Both are regression-tested.

**Verified by moving the checkout, not by argument.** The baseline was written
under `/home/user/Tranc3`. The same commit was then scanned from two git
worktrees at unrelated paths:

```
/tmp/.../portability/Tranc3            -> 0 new, 49 already known
/tmp/.../portability/some-other-name   -> 0 new, 49 already known
```

The second matters more than the first: its directory is not named after the
repository, so it never exercises the name-matching fallback — it proves the
primary path, `_REPO_ROOT` derived from the module's own location, carries the
whole job. A portability claim resting on a fallback that happens to fire is not
a portability claim.

This is the second time in this document that a path normalisation bug produced
a confident, wrong answer; the first buried 13,712 findings behind a
distribution of all-A. Paths are where scanners lie without meaning to.

### 1c. The estate's biggest scanner reports where the estate cannot read

`codeql.yml` runs CodeQL, writes SARIF to `sarif-results/`, uploads it to the
Security tab, and **discards the file**. The alerts are then readable in exactly
one place, behind an authenticated web page, by exactly the people who can
already open it.

The cost of that is measurable. **"5 high / 14 medium" was reported on nine
consecutive commits of pull request #1150** and nobody — human or agent — could
say *which five*. A finding you cannot enumerate cannot be triaged, adjudicated,
or argued with. It is a number that produces anxiety and no action.

Fixed by retaining the SARIF as a workflow artifact. It costs nothing, changes
no gate, and makes the alerts readable by anything that reads SARIF — which now
includes this estate's own scanner:

```bash
gh run download <run-id> -n codeql-sarif-python
python scripts/immune_scan.py --merge sarif-results/*.sarif
```

The artifact is taken **after** the adjudication filter, so what you download is
what the Security tab shows; the filter step prints every alert it drops and
fails on a surprise, so the suppressed set stays auditable from the job log.

One detail that would have made this silently useless: **CodeQL puts severity on
the rule, not on the result.** A reader that only inspects `result.level` grades
every CodeQL finding at the fallback severity — turning five `error` alerts into
five `warning`s and dropping them below the grading threshold. `_rule_levels`
handles it, and a round-trip test now holds it.

### 2. The pre-commit documentation described a gate that does not exist

It described the pre-commit gate as running **black** and **isort**. Neither is
configured. This repository formats with `ruff-format`, honouring
`[tool.ruff] line-length = 100` against black's default of 88.

Anyone — person or agent — who read that section and ran `black` had every file
reformatted back on the next push, with no error message anywhere saying why.
That happened twice in the session that wrote this document, before anyone read
the config instead of the documentation.

The same section omitted six hooks that do run, including two local ones
(`security-scanner`, `security-autofix`) that **modify files**. A contributor
reading only the documentation would experience those as their code changing by
itself.

`scripts/check_precommit_documented.py` compares the two in both directions.

### 3. Bandit run without the repository's own config is autoimmune

The first real run of the bandit sensor, before it was pointed at
`[tool.bandit]` in `pyproject.toml`, returned **13,712 findings**, of which
**12,770 were B101** — bandit objecting to `assert` inside the test suite, which
is what a test suite is made of.

That is not detection. It is the immune system attacking healthy tissue, and it
would have buried the one genuine error-level finding under 13,711 others.

The estate had already decided this, with written reasons, in `[tool.bandit]`.
The sensor was overriding a considered decision by not reading it. With the
config: **36 findings**, one of them error-level.

`src/immune/memory.py` detects the general case: one rule adjudicated a false
positive across three or more unrelated files means the **rule** is the problem,
and the fix is to tune the sensor rather than add a fourth suppression.

### 4. 52 deployed workers are claimed by no Location

```
worker directories:                                90
claimed by a Location's worker_path:               35
unclaimed:                                         55
   ...of which deployed in docker-compose.production.yml:  52
```

`workers/cranbania/` is among them: The Town Hall's `worker_path` is
`src/townhall/`, so the CranBania submodule that *is* The Town Hall's deployed
service is attributed to nobody.

**This is not assigned here.** The owner's standing decision is that which
Location owns an item is a Town Hall decision recorded in the Backlog Routing
Register, not a lookup someone performs by judgement. `triage_change.py` reports
unclaimed service paths by name on every pull request that touches one, so the
queue is visible; the answers belong to the Town Hall.

### 5. The existing learning store learned from its own test suite

`.security_learning/suppress.json` carries adjudications keyed on paths like
`/tmp/pytest-of-root/pytest-1/test_suppression_filtering0/test_bare.py` —
directories that existed for the duration of one test run in May 2026 and can
never exist again. `patterns.json` has the same shape.

Those entries will match nothing, forever, and nothing in the estate notices —
because nothing ever reads the store back and asks whether its entries still
mean anything.

`config/immune/adjudications.yaml` is what replaces it, and the difference is
not the format:

- **Provenance and an expiry are mandatory.** An expired adjudication still
  suppresses — nobody should wake to a wall of red — but it is reported on every
  run until someone renews or drops it. A decision nobody will ever revisit is
  not a decision, it is a leak.
- **Rot is a finding.** An entry whose file is gone, or that matched nothing,
  is reported. That is how the pytest-tmpdir entries would have been caught the
  week after they were written.
- **It is a text file in git**, so every entry arrives in a commit that argues
  for it and every removal shows in a diff.

## The layers

| Biology | Code | What it does |
|---|---|---|
| Innate immunity | `src/immune/sensors.py` | Fast, generic sensors that fire on shapes, not on known attacks. Each reports whether it could actually **see** |
| Circulation | `src/immune/sarif.py` | One bloodstream: every output normalised to SARIF 2.1.0, so the estate reads in one language |
| Adaptive memory | `src/immune/memory.py` | What was met and how it was adjudicated — with an expiry, and with its own autoimmunity detected |
| Vitals | `src/immune/grade.py` | The health check: a grade, its arithmetic, and the direction of travel |
| Barrier | `.pre-commit-config.yaml` | Twenty-two hooks that stop things before they enter |
| Triage | `scripts/triage_change.py` | Which organ this landed in, and what it crossed |

Not built, and named here so the gap is a decision rather than an omission:

- **Antibodies** — automated fix pull requests per defect class. The parts exist
  (`scripts/adaptive_vulnerability_remediation.py`, `scripts/apply_repairs.py`,
  `src/core/mape_k.py`, `src/observability/self_healer.py`) and are not joined
  to the sensor layer. The right next step, and the one with the most autoimmune
  risk, which is why it is not a side effect of this work.
- **Vaccination** — deliberately injecting known-defect mutants across the whole
  sensor set on a schedule and measuring the detection rate as a service level.
  The probe mechanism is exactly this, per-sensor and on demand; making it a
  scheduled estate-wide measurement is a small step from here.

## Running it

```bash
python scripts/immune_scan.py                      # full sweep
python scripts/immune_scan.py --changed-only       # grade the diff, not the tree
python scripts/immune_scan.py --debt               # what the backlog costs to keep
python scripts/immune_scan.py --gate               # exit 1 on regression or blind sensor
python scripts/immune_scan.py --sarif out.sarif    # one merged SARIF document
python scripts/immune_scan.py --write-baseline     # redefine "self", deliberately

python scripts/check_nosec_specificity.py          # suppressions name what they silence
python scripts/check_precommit_documented.py       # the docs match the gate
python scripts/triage_change.py                    # who owns this change
```

`--write-baseline` refuses to run when a required sensor came back blind or
failed, because that would record "we could not see" as "self".

## Why this is cheaper than what it replaces

Nothing here needs an account, a tenant, a token or a runner this estate does
not already have. It runs on tools already installed, inside a job that already
runs, and adds no workflow file — which matters, because the estate's standing
policy is to avoid GitHub Actions where possible and the consolidation that
preceded this took the workflow count from 48 to 27.

The tests are calibration tests: each plants the defect its guard exists to
catch and proves the guard fires, and four are marked `REGRESSION` against
defects that were real in this code on its first run. Every one of those looked
exactly like success.

One of the calibrations initially passed on a broken probe — the planted file
was untracked and the guard reads `git ls-files`, so it scanned nothing and
reported clean. It is recorded in the test suite because **"guard missed" and
"probe never ran" produce the same green**, and that is the failure this whole
subsystem exists to make impossible.

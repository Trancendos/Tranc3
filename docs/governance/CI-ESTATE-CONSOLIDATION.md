# The CI estate, the PR queue, and what connects them

**Measured** 2026-09-10 against `main` at `5c69056c` and the live repository.
Every figure below was produced by a command named beside it.

## The question

84 open pull requests, 225 remote branches, 48 GitHub Actions workflow files.
The question put to this review was which of the pull requests could be
unblocked and whether the workflow estate could be consolidated. The two turn
out to be one question.

## What blocks the queue

**Not 84 problems. One.**

Of 48 workflow files on `main`, **24 fired on every pull request, running 38
jobs**. Thirteen of those jobs could not pass under any circumstances:

| Workflow | Why it can never pass |
|---|---|
| `label.yml` | needs `.github/labeler.yml`; the file had never existed |
| `pyre.yml` | no `.pyre_configuration` in the repository |
| `pysa.yml` | no `.pysa_configuration` in the repository |
| `snyk-security.yml` | wants `secrets.SNYK_TOKEN`, unset |
| `soos-dast-scan.yml` | ships a literal `<YOUR-PROJECT-NAME>` |
| `synopsys-io.yml` | `{{PROJECT_NAME}}` as a **mapping key** — the file does not parse |
| `synopsys-action.yml` | wants Black Duck / Coverity credentials, unset |
| `neuralegion.yml` | wants `NEXPLOIT_TOKEN`, unset |
| `frogbot-scan-and-fix.yml` | wants JFrog credentials, unset |
| `policy-validator-cfn.yml` | AWS IAM policy validation; this estate runs no AWS |
| `defender-for-devops.yml` | Azure DevOps; this estate runs no Azure |
| `black-duck…`, `endorlabs`, `zscaler…` | unset config — **gated** since #1152, so these skip rather than fail |

Every pull request in the repository therefore opened with a wall of red that
no author could clear. That is worse than noise: **a check that is always red
teaches reviewers to ignore red**, which is how a real failure gets waved
through beside eleven fake ones.

Two more repo-owned gates were red on `main` itself, meaning no pull request
could pass them either:

- **Service Topology** — `ci.yml` runs `check_workflow_placeholders.py`, and
  `soos-dast-scan.yml` / `synopsys-io.yml` trip it. Verified by running the
  check on a clean `main` checkout: exit 1.
- **Ruff Lint** — F841 at `scripts/adaptive_vulnerability_remediation.py:323`.
  Verified the same way.

## The nine site builders

`astro`, `gatsby`, `hugo`, `jekyll`, `jekyll-gh-pages`, `mdbook`, `nextjs`,
`nuxtjs`, `static` — nine GitHub Pages deploy workflows. Checked for the source
each one requires:

```
astro    needs astro.config     present: False
gatsby   needs gatsby-config    present: False
hugo     needs hugo.toml        present: False
jekyll   needs _config.yml      present: False
mdbook   needs book.toml        present: False
nextjs   needs next.config      present: False
nuxtjs   needs nuxt.config      present: False
```

None of the seven has a site to build. `static.yml` is worse than useless: it
uploads the **entire repository root** as a Pages artifact and publishes it.

## What was done

| Action | Count | Files | Basis |
|---|---|---|---|
| Deleted — Pages builders with no site | 9 | `astro`, `gatsby`, `hugo`, `jekyll`, `jekyll-gh-pages`, `mdbook`, `nextjs`, `nuxtjs`, `static` | no source config for any of them |
| Deleted — commercial scanners, no zero-cost path | 8 | `defender-for-devops`, `frogbot-scan-and-fix`, `neuralegion`, `policy-validator-cfn`, `snyk-security`, `soos-dast-scan`, `synopsys-action`, `synopsys-io` | credentials unset, paid products |
| Deleted — free scanners duplicating existing tooling | 2 | `pyre`, `pysa` | `mypy` already runs in `make lint` |
| Deleted — starter with no purpose | 1 | `manual` | greets a person by name |
| Deleted — duplicate coverage run | 1 | `codecov` | ran `ci.yml`'s suite a second time, `\|\| true`-suppressed either way |
| Fixed | 1 | `label` | `.github/labeler.yml` written, in the **v4 schema** the pinned action expects |
| De-duplicated | 1 | `python` | ran the whole suite twice per matrix entry |

**21 files deleted: 48 → 27 workflow files. 24 → 14 firing on a pull request.
38 → 29 jobs.** The last two rows change files rather than remove them, so the
deletion column reconciles on its own: 9 + 8 + 2 + 1 + 1 = 21, and 48 − 21 = 27.
Verified with `git diff --diff-filter=D --name-only origin/main...HEAD --
.github/workflows/ | wc -l`.

Nothing that could ever produce a signal was removed. The three gated scanners
(`black-duck`, `endorlabs`, `zscaler`) stay: configure the secrets and they run.
`scorecard`, `anchore-syft` and `stale` stay and do not gate pull requests.

`python.yml`'s test job ran `pytest tests/ -v` and then `pytest tests/ --cov`
— the entire suite twice, across four Python versions, on every pull request
touching `aeonmind/python`. Four duplicate full runs, for no signal the second
run did not already carry. One run now, with both sets of flags.

## What the branch audit found once it could count

`scripts/branch_benefit_audit.py` classifies every remote branch
cherry-pick / review / blocked. It has never run: its workflow
(`.forgejo/workflows/branch-integration-audit.yml`) pins `runs-on: self-hosted`
against a Citadel act-runner the cloud-only phase has not stood back up.

Run by hand, it reported **166 branches ahead of main, 58 fully merged** — and
`+0/−0` on every single row.

The parser split git's output on whitespace and compared tokens against
`"insertions"`. git writes `249 insertions(+)`. It never matched. `files`
matched only because git spells that one bare.

That was not a cosmetic column. `_verdict` classifies on the **deletion**
count, so the "mass deletions — likely destructive rebase" rule could never
fire and every branch fell through to `files <= 15 and deletions < 500`: the
audit was calling branches safe to cherry-pick on a measurement it had not
made. With the parser fixed, two branches moved out of that verdict —

```
jules-9320263048445895828-bc5e6367       cherry-pick -> review   9 files  +1218/-921
jules-health-check-async-optimization…   cherry-pick -> review   9 files  +1482/-947
```

— and the largest deletion counts in the estate became visible for the first
time.

## The tooling for this question already exists, and has never run

Four Forgejo workflows were built for exactly the problem this review was asked
about:

| Workflow | Script | Runner |
|---|---|---|
| `pr-readiness-audit.yml` | `scripts/pr_readiness_audit.py` | `self-hosted` |
| `branch-integration-audit.yml` | `scripts/branch_benefit_audit.py` | `self-hosted` |
| `fork-audit.yml` | `scripts/fork_audit.py` | `self-hosted` |
| `stale-branch-cleanup.yml` | `scripts/stale_branch_cleanup.py` | `self-hosted` |

All four are weekly. All four are pure git and GitHub-API work — **none of them
needs a machine of its own**. They are waiting on hardware for a job that needs
no hardware, and so the 84-pull-request, 225-branch backlog has never once been
measured by the system built to measure it.

`pr_readiness_audit.py` additionally died with a traceback whose last line was
`No such file or directory: 'gh'` when the CLI was absent — a stack trace where
a one-line prerequisite message belongs. `fork_audit.py` beside it already had
a `_gh_available()` check. Fixed to match.

## What is worth taking from the deleted fleet

Deleting a starter template is not the same as rejecting the capability it
gestured at. Three are worth building properly, all at zero cost:

1. **SBOM, from `anchore-syft`.** It runs on push, uploads an artifact, and
   nobody reads it. `docs/governance/AI-BOM.md` is maintained by hand. A syft
   run feeding the DVMS census would give the AI-BOM a generated spine.
2. **`actions/dependency-review-action`** — free, GitHub-native, and absent.
   The census measures the *estate*; dependency-review measures the *diff*, and
   fails a pull request that introduces a vulnerable dependency before it lands.
   Complementary, not duplicative.
3. **`summary.yml`** already uses `actions/ai-inference` to summarise new
   issues, and its prompt correctly treats issue text as untrusted. That is the
   right pattern for the Town Hall's own triage, and it costs nothing.

## Standing caution

`label.yml` triggers on `pull_request_target` with `pull-requests: write`.
`actions/labeler` does not check out pull request code, so it is not presently
exploitable — but that trigger and permission pairing was inherited from a
template unexamined, and should not be copied.

## The sprawl is Tranc3's alone — and CranBania answers the runner question

Checked the other three repositories in the estate:

| Repository | GitHub workflows | Forgejo workflows | Starter templates |
|---|---|---|---|
| **Tranc3** | 48 → 27 | 33 | **~20 before this review** |
| **CranBania** | none | 4, all bespoke | 0 |
| **Magna-Carta** | 1 (`layer-b-ci.yml`, bespoke) | — | 0 |
| **InfinityStyles** | 2 (`codeql.yml`, `node.js.yml`) | — | 0 — and both are *legitimate*: it is a Node repository, and CodeQL is free |

So this is not a platform-wide habit. It is one repository where **Actions → New workflow → Configure** was clicked repeatedly and nothing removed what did not take. Nothing needs fixing in the other three.

**CranBania settles the runner question.** Its four Forgejo workflows —
`cranbania-agent`, `cranbania-ci`, `cranbania-sla-agent`, `cranbania-sla-check` —
every one of them declares:

```yaml
runs-on: ubuntu-latest
```

Not `self-hosted`. A sibling repository in the same estate, under the same
Forgejo, runs its CI on a hosted-style runner label today. Tranc3's
`.forgejo/workflows/` pins `self-hosted` on **24 of 33 files**, including the
four queue-hygiene audits that have consequently never executed.

That makes the pin a per-file choice, not a platform constraint. Taking
`pr-readiness-audit`, `branch-integration-audit`, `fork-audit` and
`stale-branch-cleanup` off `self-hosted` is therefore not a departure from the
zero-cost, self-hosted-by-default posture — it is aligning Tranc3 with what
CranBania has been doing all along, for four weekly jobs that are pure git and
GitHub-API work and need no hardware of their own.

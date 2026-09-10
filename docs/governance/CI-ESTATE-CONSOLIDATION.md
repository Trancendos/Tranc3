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

| Action | Count | Basis |
|---|---|---|
| Deleted — Pages builders with no site | 9 | no source config for any of them |
| Deleted — commercial scanners, no zero-cost path | 6 | credentials unset, paid products |
| Deleted — free scanners duplicating existing tooling | 2 | `pyre`/`pysa`; `mypy` already runs in `make lint` |
| Deleted — starter with no purpose | 1 | `manual.yml` greets a person by name |
| Fixed | 1 | `.github/labeler.yml` written, in the **v4 schema** the pinned action expects |
| De-duplicated | 1 | `python.yml` ran the whole suite twice per matrix entry |

**48 → 27 workflow files. 24 → 14 firing on a pull request. 38 → 29 jobs.**

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

# Pull Request Queue Triage

Measured 2026-09-12 across the four repositories in scope. This records what was
merged, what was closed, what is held, and the reason in each case. It is a
decision register, not a status page: a row here is an answer someone can argue
with, not a number.

## What the sweep actually found

178 open pull requests: **100** in Tranc3, **30** in Magna-Carta, **27** in
InfinityStyles (first page), **21** in CranBania.

In Tranc3, 72 of the 100 conflicted with `main`. The conflict was the least
interesting property. Three findings only appear by walking the refs, and
`scripts/triage_pull_requests.py` now does that walk on demand:

### 1. Six branches would delete files that are live on main

Not stale-branch noise — committed deletions, carried forward by any rebase.

| PR | title says | would delete |
|---|---|---|
| #994 | "Vector similarity calculation optimization" | **20 live files, 8 of them test suites**, including all of `src/exchange/`, `src/cmdb/blast_radius.py`, `src/cmdb/identity.py`, and `scripts/check_workflow_drift.py` |
| #1177 | "ci: consolidate GitHub Actions" | `anchore-syft.yml`, `test.yml`, both renovate configs |
| #1000 | "Optimize cosine similarity calculation" | `scripts/check_ai_register.py`, `tests/test_safeguarding.py` |
| #1151 | "Optimize pure-Python vector math" | `tests/test_perf_opt.py` |
| #1176 | "Optimize cosine similarity" | `black-duck-security-scan-ci.yml` |
| #1179 | "[performance improvement]" | `label.yml` |

`scripts/check_workflow_drift.py` is the guard that keeps the GitHub and Forgejo
copies of the production gate in lockstep — the guard whose absence let the two
copies diverge in the first place (`CI-ESTATE-CONSOLIDATION.md`). A performance
PR removing it, plus eight test suites, is not a change anyone reviewed.

The pattern to keep: **a performance branch that deletes the performance test**
(#1151) is the same defect class as a sensor that cannot see reporting what a
clean estate reports. The suite that would have measured the claim is the thing
that goes.

### 2. Dependency bumps main has already passed

Renovate has not rebased in weeks, so several "updates" now move backwards:

| PR | proposes | main has | verdict |
|---|---|---|---|
| #1090 | `lucide-react ^0.577.0` | `^1.0.0` | downgrade |
| #1073 | `@cloudflare/workers-types 5.20260828.1` | `5.20260910.1` | downgrade, 13 days |
| #1092 | `grpc v1.83.2` | `v1.83.2` | already applied |

### 3. Duplicate clusters

Thirteen open PRs optimise the same pure-Python vector maths (#1211, #1182,
#1179, #1178, #1176, #1173, #1153, #1151, #1144, #1136, #1001, #1000, #994).
Four of them rewrite the same 204 lines of
`scripts/adaptive_vulnerability_remediation.py`. Two implement the same
delete-confirmation dialog (#1181, #999).

## Decisions taken

### Merged (7)

| PR | why |
|---|---|
| #1197 | undici 8.10.0→8.10.2 — closes 10 advisories, 3 HIGH |
| #1209 | SEC-005 retired: semgrep moved its `mcp` pin to 1.29.0 |
| #1201 | security alert register made canonical; pin-governance exception recorded |
| #1210 | 67th remediated CVE; its undici row conflicted with #1197 and was resolved to main's measured versions |
| #1198 | workers safe-updates — polars, sse-starlette ×7, boto3 |
| #1211 | distillation MSE via `operator.sub`/`mul` over `map` — arithmetically identical |
| #1149 | fflate 0.4.8→0.4.9, lockfile only |

On #1198: it moves `workers/the-lab/requirements.txt` ruff 0.15.8→0.16.6. That
looked like it would break `scripts/check_ruff_pin_alignment.py`. It does not,
and the reason matters — that guard holds **eleven** surfaces in lockstep (CI
workflows, pre-commit, the runner Dockerfile), and The Lab's ruff is its
*verification sidecar* for linting user code, deliberately outside that set.
Verified by running the guard against the merge result rather than assuming.

### Closed (8)

| PR | why |
|---|---|
| #994 | deletes 20 live files including 8 test suites and the workflow-drift guard |
| #1000 | deletes `check_ai_register.py` and `tests/test_safeguarding.py` |
| #1151 | deletes `tests/test_perf_opt.py` |
| #1090 | downgrades lucide-react |
| #1073 | downgrades `@cloudflare/workers-types` |
| #1092 | already applied on main |
| #1181 | degraded duplicate of #999: +1 line of implementation, −26 lines of `.Jules/palette.md` |
| #842 | every change already on main; the only unique file is a CircleCI `say-hello` stub |

In each case the *named* improvement is small and can be reapplied from a branch
cut at current `main`. None of these branches is recoverable by rebasing, because
the deletions are committed content.

### What #842 surfaced, which outlives the PR

CodeFactor was right that `riskScore` is never reassigned in The Lighthouse's
`ScannerBot`. That is the defect, not the style:

```ts
const riskScore = 0;                 // never computed
const recommendation =
  riskScore >= 75 ? 'revoke' :
  riskScore >= 50 ? 'investigate' :
  riskScore >= 25 ? 'renew' : 'valid';
```

`ScannerBot` pushes three hardcoded `severity:'info'` findings regardless of
input and never scores them, so the ladder always resolves to `valid`. **The
token scanner cannot fail a token.** Two more of the same shape:
`ArchivistAgent.missing` is hardcoded `0`, so the artifact integrity check can
never report a missing artifact; `SwarmAgent.targetNodes` is always `[]`.

Same class as the sensors in `IMMUNE-SYSTEM.md`. These need real scoring plus
probes, not a `const` keyword.

## Held, with the reason

| PR(s) | held because |
|---|---|
| #999 | carries unrelated `:latest@sha256` digest churn across two compose files; the UI fix is wanted, the digest drift is unreviewed scope |
| #1200 | bumps semgrep 1.173.0→1.176.1 while #1207 aligns all pins to 1.177.0; also torch 2.13→2.14 and transformers 5.15→5.16 |
| #1203, #1199, #1132, #1128, #1133 | major-version jumps (react 19, vite 8, bullmq 6, mypy 2) against a `web/` peer graph that is already unresolvable |
| #1010, #1078, #1079, #1081 | move the estate from Python 3.11 to 3.14 across 92 Dockerfiles and every workflow — a platform decision, not a dependency bump |
| #1183–#1196 (14) | charliecreates daemons: each adds one `.agents/daemons/*/DAEMON.md`. Inert markdown unless a vendor agent runtime reads them. Adopting a vendor agent framework is a governance decision the estate has not taken |
| #1154–#1167 (13) | aikido security autofixes — several are genuinely worth taking (pin third-party actions, narrow workflow permissions, SSRF, file inclusion). All conflict; each needs reading on its merits |

## The tool

`scripts/triage_pull_requests.py` answers the question the merge button does
not: *what does main lose if this lands?* It is offline — it reads
`refs/remotes/pr/*` and `origin/main` from the local clone, costs no API calls,
and exits non-zero when any surveyed PR would delete a live file, so it can gate
a queue rather than describe one.

```bash
git fetch origin '+refs/pull/*/head:refs/remotes/pr/*'
python3 scripts/triage_pull_requests.py 994 1000 1151
python3 scripts/triage_pull_requests.py --from-json open_prs.json --json
```

Two subtleties are worth knowing before trusting it, because both produced wrong
verdicts during its construction:

- **Rename detection is capped.** `diff.renameLimit` decides how many paths git
  will pair; above the cap every move is reported as a plain delete. The
  `Dimensional/` → `Dimensionals/` rename in #1207 is 95 files renamed *and*
  edited in one commit, so without `-M -l0` the sweeper called the one large
  correct PR the most destructive in the queue — while an equivalent two-file
  rename in a test looked clean. Same operation, opposite verdicts, decided by
  size.
- **Similarity has a floor.** A one-line `__init__.py` whose single line was
  rewritten during the move scores 0% and can never pair. Those are reported as
  `relocated` — the basename reappears elsewhere in the head — and deliberately
  do not trip the exit code. A sweeper that flags every refactor gets switched
  off, which is the failure mode that matters.

Both are covered by probes in `tests/test_triage_pull_requests.py`: each builds
a real throwaway repository, and each rename case is paired with a real deletion
under identical git config, so the tool has to show it can still fail closed.

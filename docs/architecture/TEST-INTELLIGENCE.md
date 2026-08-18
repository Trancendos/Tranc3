# Test intelligence — the CircleCI question, answered in-platform

**Date:** 2026-08-18. **Decision:** do not adopt CircleCI. Build the two features
worth having into The Chaos Party, from telemetry the estate already produces.

## 1. What prompted this

`circleci-project-setup` was the one branch in the whole estate carrying a file
`main` genuinely lacked (see `BRANCH-SALVAGE-ANALYSIS.md`). On inspection, that
file is CircleCI's onboarding scaffold — a `say-hello` job that runs
`echo Hello, World!`. There is no project-specific functionality in it to port.

The underlying question is still worth answering: is CircleCI free, and if it is
not, can the capability be built here instead?

## 2. Cost

CircleCI's Free plan is real but metered — **6,000 build minutes/month, up to 5
active users**, 30x concurrency. Above that, Performance starts at $15/month for
30,000 credits, with additional credits at $15 per 25,000. On Linux Medium
(10 credits/min) those 30,000 credits are ~3,000 minutes.

So: free at low volume, metered thereafter. Metering is precisely the exposure
`CLAUDE.md`'s standing policy exists to avoid — *"avoid GitHub Actions and
Cloudflare Workers wherever possible (both carry rate limits that bite under
prolonged/heavy use)"*. Adding a third CI system that meters would work against
the reason the estate is self-hosted-by-default, and it would sit alongside
Forgejo (primary) and GitHub Actions (GitHub-native checks) as a third place CI
config has to be kept correct.

## 3. What CircleCI actually sells that Forgejo does not have

Most of the comparison is a wash — containers, matrices, caching, artifacts and
approval gates all exist in Forgejo Actions. Two things do not:

| Capability | In Forgejo? | Worth building? |
|---|---|---|
| Split a suite across N runners by **historical timing** | no | **yes** — this is the wall-clock win |
| **Flaky-test detection** from run history | no | **yes** — cheap once results are correlated |
| Orbs (reusable config packages) | no | no — composite actions cover it |
| SSH into a failed build | no | no — reproducible locally |
| Insights dashboards | no | partly — The Observatory already ingests runs |

## 4. The data was already there

`conftest.py` writes one JSON line per test to `logs/test_results.jsonl`, and
`.forgejo/workflows/ci.yml` archives that file for 30 days. **Nothing read it.**
The estate was already collecting the exact telemetry a commercial CI vendor
builds these two features on, then discarding it on a retention timer.

`scripts/test_intelligence.py` consumes it.

## 5. Timing-based sharding

Longest-processing-time-first (LPT): sort tests by descending median duration,
place each on the shard with the least accumulated time. Provably within 4/3 of
optimal — far inside run-to-run timing noise, so an exact partition would be a
knapsack solve for nothing.

Measured against the naive alternative on a realistic distribution (400 fast unit
tests plus 12 heavy integration tests, 64.7s serial):

| Shards | LPT longest | LPT imbalance | Count-balanced longest | Count imbalance | Speed-up |
|---:|---:|---:|---:|---:|---:|
| 2 | 32.3s | 1.00 | 61.7s | 1.91 | 1.91x |
| 4 | 16.2s | 1.00 | 60.0s | 3.71 | 3.71x |
| 8 | 8.1s | 1.00 | 59.3s | 7.33 | **7.32x** |
| 16 | 8.1s | 2.00 | 58.9s | 14.58 | 7.28x |

At 16 shards LPT stops improving because a single 8.1s test cannot be split —
that is the theoretical floor, not a defect. Count-balancing degrades steadily
because the heavy tests cluster alphabetically and all land together.

**Why the timing profile is committed.** `.test-timings.json` lives in the repo
rather than in a vendor. The split is therefore deterministic, reviewable in a
diff (you can see a test get 30x slower), and works with no service reachable.
That is the part that improves on the SaaS model rather than reproducing it.

A test with no timing history is assigned the median of known tests — the same
assumption CircleCI makes, and the right one: assuming zero piles every new test
onto one shard.

## 6. Flaky means disagreeing with itself at one commit

The naive definition — "has both passed and failed at some point" — labels every
test that was ever broken and then fixed. A flaky report full of already-fixed
tests gets ignored, which is worse than having none.

So `conftest.py` now records the **commit** and a **run id** with each result,
and a test is called FLAKY only when it produced both a pass and a fail *at the
same commit*. Disagreement across different commits is reported separately and
weakly as `unstable_across_commits`, because the code genuinely changed in
between. Records predating the commit field carry `"unknown"` and are excluded
from adjudication rather than guessed at.

Verified against a fixture covering all four cases: same-commit disagreement →
flaky; fail-then-pass across commits → not flaky; commit-less legacy records →
excluded; consistent pass → silent.

## 7. Usage

```console
python scripts/test_intelligence.py                    # report
python scripts/test_intelligence.py --update-timings   # (re)build the profile
python scripts/test_intelligence.py --check            # CI: has the profile rotted?
python scripts/test_intelligence.py --shard 0 --of 4   # nodeids for shard 0
python scripts/test_intelligence.py --publish          # -> The Chaos Party /runs/batch
```

A sharded CI job body:

```yaml
strategy:
  matrix:
    shard: [0, 1, 2, 3]
steps:
  - run: python scripts/test_intelligence.py --shard ${{ matrix.shard }} --of 4 > ids.txt
  - run: python -m pytest $(cat ids.txt)
```

## 8. Adoption state

- **Landed:** the tool, the commit/run-id telemetry, and a `--check` step in the
  `topology` CI job.
- **Not yet landed:** the timing profile itself, and the sharded matrix job.

`--check` is deliberately a **no-op while no profile exists** — failing CI for a
feature nobody has turned on yet is noise. It starts guarding the moment
`.test-timings.json` is committed. `--check --require-profile` makes adoption
itself a gate, for when that is wanted.

Bootstrapping the profile needs one full-suite run (`pytest tests/` then
`--update-timings`); it is deliberately left as a separate step so the profile is
generated from a real, complete run rather than the partial one that happened to
be available when this landed. A 15-test profile is worse than none.

## 9. A defect this work caught

The first implementation read nodeids by parsing `pytest --collect-only -q`
output. In this pytest version that flag combination prints one `file: count`
summary line per module and **no nodeids at all**, so the parser returned zero
tests — and zero tests reads exactly like "there are no tests". A sharded job
built on it would have run nothing and exited 0.

Collection now goes through pytest's `pytest_collection_modifyitems` hook, which
is public API and returns real nodeids (5,851 of them), in a subprocess so the
suite's `conftest.py` cannot affect the calling process. Verified as a true
partition: 4 shards, 5,851 tests total, zero duplicated, zero missing.

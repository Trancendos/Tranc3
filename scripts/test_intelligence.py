#!/usr/bin/env python3
"""Test intelligence for The Chaos Party — timing-based sharding and flaky detection.

WHY THIS EXISTS

`conftest.py` already writes one JSON line per test to `logs/test_results.jsonl`
(nodeid, outcome, duration, failure reason, commit, run id), and `.forgejo/
workflows/ci.yml` already archives it for 30 days. Nothing ever read it. The two
things a commercial CI service sells on top of exactly this data are:

  1. splitting a suite across N runners by historical timing, so wall-clock time
     falls to roughly total/N instead of being set by whichever shard happened to
     collect the slow tests; and
  2. telling you which failures are flaky rather than real.

Both are computable from the file the estate is already producing and discarding.
CircleCI's free tier is 6,000 build minutes and 5 active users per month, after
which it meters — and metered third-party CI is the exposure `CLAUDE.md`'s
standing policy exists to avoid. The Chaos Party's own worker docstring already
states the position: "Zero-cost: FastAPI + SQLite. No external CI services
required." This is that sentence made true for the two features worth having.

HOW THE SPLIT WORKS, AND WHY IT IS NOT THE OBVIOUS ONE

Round-robin or alphabetical splitting balances *test counts*, which is the wrong
quantity — one 40-second integration test outweighs two hundred 2ms unit tests.
This partitions by measured duration using longest-processing-time-first (LPT):
sort tests by descending median duration, then repeatedly place the next test on
the shard with the least accumulated time. LPT is the standard greedy scheduler
and is provably within 4/3 of optimal, which is far inside the noise of run-to-run
timing variance — an exact partition would be a knapsack solve for no real gain.

Median, not mean: a single cold-cache or contended run would otherwise drag a
fast test's estimate up permanently.

WHY THE TIMING PROFILE IS COMMITTED

`.test-timings.json` is written to the repo rather than recomputed from scratch in
CI. That makes the split deterministic and reviewable — you can see in a diff that
a test got 30x slower — and it means shard assignment does not depend on a service
being reachable. This is the part that improves on the SaaS model rather than
merely reproducing it: there, the timing data lives in the vendor and the split is
opaque.

A test absent from the profile (newly added, never yet timed) is assigned the
median of all known tests. That is the same assumption CircleCI makes, and it is
the right one: assuming zero would pile every new test onto one shard.

FLAKY MEANS DISAGREEING WITH ITSELF AT ONE COMMIT

The naive definition — "this test has both passed and failed at some point" —
labels every test that was ever broken and then fixed. That is not flakiness, and
a flaky-test report full of already-fixed tests gets ignored, which is worse than
having none.

So a test is FLAKY only when it produced both a pass and a fail *at the same
commit*. Disagreement across different commits is reported separately and much
more weakly, as `unstable_across_commits`, because the code genuinely changed
between those runs. Records predating the commit field carry "unknown" and are
excluded from flaky adjudication rather than guessed at.

USAGE

    python scripts/test_intelligence.py                      # report
    python scripts/test_intelligence.py --update-timings     # refresh the profile
    python scripts/test_intelligence.py --check              # CI: profile fresh?
    python scripts/test_intelligence.py --shard 0 --of 4     # nodeids for shard 0
    python scripts/test_intelligence.py --publish            # -> The Chaos Party

In CI, a sharded job body is:

    python scripts/test_intelligence.py --shard ${{ matrix.shard }} --of 4 > ids
    python -m pytest $(cat ids)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "logs" / "test_results.jsonl"
TIMINGS = REPO / ".test-timings.json"

# Below this share of currently-known tests present in the profile, the split
# degrades toward count-balancing and the profile is worth regenerating.
# Overridable per-suite via --min-coverage or TEST_INTELLIGENCE_MIN_COVERAGE:
# `tranc3-bots/` carries its own pytest config and may reasonably want a
# different bar from the main suite, and tuning that should not need a code edit.
DEFAULT_MIN_COVERAGE = 0.80

PASS, FAIL = "passed", "failed"


def _env_min_coverage() -> float:
    """Coverage bar from the environment, falling back to the default.

    A malformed value is ignored rather than fatal: this is a tuning knob, and
    a typo in CI env should not take down a check that would otherwise run.
    """
    raw = os.environ.get("TEST_INTELLIGENCE_MIN_COVERAGE", "").strip()
    if not raw:
        return DEFAULT_MIN_COVERAGE
    try:
        value = float(raw)
    except ValueError:
        print(
            f"[WARN] TEST_INTELLIGENCE_MIN_COVERAGE={raw!r} is not a number; "
            f"using {DEFAULT_MIN_COVERAGE:.2f}",
            file=sys.stderr,
        )
        return DEFAULT_MIN_COVERAGE
    if not 0.0 <= value <= 1.0:
        print(
            f"[WARN] TEST_INTELLIGENCE_MIN_COVERAGE={value} is outside [0, 1]; "
            f"using {DEFAULT_MIN_COVERAGE:.2f}",
            file=sys.stderr,
        )
        return DEFAULT_MIN_COVERAGE
    return value


def load_records(path: Path) -> list[dict]:
    """Every well-formed record in the JSONL, skipping corrupt lines.

    A truncated final line is normal — CI can be cancelled mid-write — and must
    not take down a reporting tool.
    """
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("test"):
            out.append(rec)
    return out


def median_durations(records: list[dict]) -> dict[str, float]:
    """test nodeid -> median duration in ms, over runs where it actually ran."""
    by_test: dict[str, list[float]] = defaultdict(list)
    for r in records:
        # A skipped test's duration is ~0 and says nothing about its real cost;
        # including it would drag the median toward zero and under-weight the
        # test on whichever shard later has to actually run it.
        if r.get("outcome") == "skipped":
            continue
        try:
            by_test[r["test"]].append(float(r.get("duration_ms") or 0.0))
        except (TypeError, ValueError):
            continue
    return {t: round(statistics.median(v), 2) for t, v in by_test.items() if v}


def find_flaky(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """(flaky, unstable_across_commits).

    Flaky: both a pass and a fail at the SAME commit — the code did not change
    between those runs, so the test disagreed with itself.

    Unstable: pass and fail at DIFFERENT commits only. Usually a break and its
    fix, occasionally a flake caught in different runs. Reported, not alarmed on.
    """
    # test -> commit -> set of outcomes
    seen: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in records:
        outcome = r.get("outcome")
        if outcome not in (PASS, FAIL):
            continue
        seen[r["test"]][str(r.get("commit") or "unknown")].add(outcome)

    flaky, unstable = [], []
    for test, per_commit in seen.items():
        # "unknown" cannot adjudicate same-commit disagreement: two unknowns may
        # be different commits. Excluded rather than guessed.
        conflicted = [c for c, o in per_commit.items() if c != "unknown" and {PASS, FAIL} <= o]
        if conflicted:
            flaky.append({"test": test, "commits": sorted(conflicted)})
            continue
        outcomes: set[str] = set()
        for o in per_commit.values():
            outcomes |= o
        if {PASS, FAIL} <= outcomes:
            unstable.append({"test": test, "commits": sorted(per_commit)})
    return (
        sorted(flaky, key=lambda d: d["test"]),
        sorted(unstable, key=lambda d: d["test"]),
    )


def plan_shards(tests: list[str], timings: dict[str, float], shards: int) -> list[list[str]]:
    """Partition tests into `shards` buckets balanced by duration (LPT greedy)."""
    if shards < 1:
        raise ValueError("shards must be >= 1")
    known = [v for v in timings.values() if v > 0]
    fallback = statistics.median(known) if known else 1.0

    # Sort by descending cost, tie-broken by nodeid so the plan is deterministic
    # across machines and Python's hash seed.
    ordered = sorted(tests, key=lambda t: (-timings.get(t, fallback), t))

    buckets: list[list[str]] = [[] for _ in range(shards)]
    totals = [0.0] * shards
    for test in ordered:
        i = totals.index(min(totals))
        buckets[i].append(test)
        totals[i] += timings.get(test, fallback)
    return buckets


def shard_totals(buckets: list[list[str]], timings: dict[str, float]) -> list[float]:
    known = [v for v in timings.values() if v > 0]
    fallback = statistics.median(known) if known else 1.0
    return [round(sum(timings.get(t, fallback) for t in b), 1) for b in buckets]


# Collection is scoped to `tests/` because that is what CI actually runs
# (`pytest tests/` in both ci.yml workflows). Repo-wide collection walks every
# worker, aeonmind and submodule tree and takes over two minutes; scoped it takes
# about fifteen seconds. Every sharded job pays this cost before running a single
# test, so the difference is per-shard wall clock, not a one-off.
DEFAULT_COLLECT_PATH = "tests"


def collect_test_ids(path: str = DEFAULT_COLLECT_PATH) -> list[str]:
    """Every test pytest can currently see under `path`.

    Driven through pytest's `pytest_collection_modifyitems` hook rather than by
    parsing `--collect-only` text. That output is not a stable interface: with
    `-q` this pytest prints one `file: count` line per module and no nodeids at
    all, so a text parser silently yields zero tests -- which reads identically
    to "there are no tests" and would have shipped a sharding tool that quietly
    ran nothing. The hook is public API and returns real nodeids.

    Run in a subprocess so importing the suite's conftest (which sets env vars
    and touches the filesystem) cannot affect this process.
    """
    import subprocess

    driver = (
        "import sys, pytest\n"
        "class _C:\n"
        "    def pytest_collection_modifyitems(self, items):\n"
        "        for i in items:\n"
        "            sys.stdout.write('NODEID\\t' + i.nodeid + '\\n')\n"
        "sys.exit(pytest.main(['--collect-only', '-q', '--no-header', '-p', 'no:cacheprovider',\n"
        "                      sys.argv[1]], plugins=[_C()]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", driver, path],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    ids = [
        line[len("NODEID\t") :] for line in proc.stdout.splitlines() if line.startswith("NODEID\t")
    ]
    if not ids and proc.returncode != 0:
        sys.stderr.write(proc.stderr[-2000:] + "\n")
    return ids


def publish(records: list[dict], url: str, secret: str, suite_id: int | None) -> int:
    """POST the run to The Chaos Party's /runs/batch. Returns rows inserted.

    Fail-open by contract, matching the worker's own Observatory bridge: test
    telemetry must never be the reason a build fails.
    """
    status_map = {PASS: "pass", FAIL: "fail", "skipped": "skip"}
    runs = [
        {
            "name": r["test"],
            "status": status_map.get(r.get("outcome"), "error"),
            "duration_ms": float(r.get("duration_ms") or 0.0),
            "error_msg": (r.get("reason") or "")[:2000],
            "ran_by": "test_intelligence",
            "metadata": {"commit": r.get("commit", "unknown"), "run_id": r.get("run_id", "")},
        }
        for r in records
    ]
    if not runs:
        return 0
    body = json.dumps({"suite_id": suite_id, "runs": runs}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/runs/batch",
        data=body,
        headers={"Content-Type": "application/json", "X-Internal-Secret": secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(json.loads(resp.read()).get("inserted", 0))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[WARN] could not publish to The Chaos Party: {exc}", file=sys.stderr)
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Test intelligence: sharding + flaky detection.")
    ap.add_argument("--results", default=str(RESULTS), help="path to test_results.jsonl")
    ap.add_argument("--timings", default=str(TIMINGS), help="path to the committed timing profile")
    ap.add_argument("--update-timings", action="store_true", help="rewrite the timing profile")
    ap.add_argument("--check", action="store_true", help="CI: fail if the profile is too stale")
    ap.add_argument("--shard", type=int, help="print nodeids for this shard index (0-based)")
    ap.add_argument("--of", type=int, help="total shard count (use with --shard)")
    ap.add_argument("--publish", action="store_true", help="send this run to The Chaos Party")
    ap.add_argument(
        "--url",
        default=os.getenv("CHAOS_PARTY_URL", "http://localhost:8079"),
        help="The Chaos Party base URL",
    )
    ap.add_argument("--suite-id", type=int, default=None, help="Chaos Party suite id")
    ap.add_argument(
        "--collect-path",
        default=DEFAULT_COLLECT_PATH,
        help=f"path pytest collects from (default: {DEFAULT_COLLECT_PATH})",
    )
    ap.add_argument(
        "--require-profile",
        action="store_true",
        help="with --check, fail when no timing profile exists at all",
    )
    ap.add_argument(
        "--min-coverage",
        type=float,
        default=_env_min_coverage(),
        help=(
            "with --check, the share of collected tests the profile must cover "
            f"(default: {DEFAULT_MIN_COVERAGE:.2f}, or TEST_INTELLIGENCE_MIN_COVERAGE)"
        ),
    )
    args = ap.parse_args()

    if not 0.0 <= args.min_coverage <= 1.0:
        ap.error("--min-coverage must be a fraction between 0 and 1")

    if (args.shard is None) != (args.of is None):
        ap.error("--shard and --of must be given together")
    if args.update_timings and args.check:
        # --update-timings makes the profile current; --check reports on a profile
        # that was not. Together they would rewrite the file and then pass
        # trivially, which is a green tick over an unread question.
        ap.error("--update-timings and --check are mutually exclusive")

    records = load_records(Path(args.results))
    timings_path = Path(args.timings)
    stored = {}
    if timings_path.is_file():
        try:
            stored = json.loads(timings_path.read_text()).get("timings", {})
        except (json.JSONDecodeError, AttributeError):
            stored = {}

    # --- shard listing: the one mode whose stdout is consumed by another program
    if args.shard is not None:
        if not 0 <= args.shard < args.of:
            ap.error(f"--shard must be in [0, {args.of})")
        ids = collect_test_ids(args.collect_path)
        if not ids:
            print("[ERROR] pytest collected no tests", file=sys.stderr)
            return 1
        merged = {**stored, **median_durations(records)}
        for nodeid in plan_shards(ids, merged, args.of)[args.shard]:
            print(nodeid)
        return 0

    measured = median_durations(records)

    if args.update_timings:
        merged = {**stored, **measured}
        timings_path.write_text(
            json.dumps(
                {
                    "_comment": "Median per-test durations (ms), used to balance CI shards. "
                    "Regenerate with: python scripts/test_intelligence.py --update-timings",
                    "tests": len(merged),
                    "timings": dict(sorted(merged.items())),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"timing profile written: {len(merged)} test(s) -> {timings_path.name}")
        return 0

    if args.check:
        # An absent profile means the feature has not been adopted yet, which is
        # not a regression -- sharding simply falls back to uniform weights. A
        # profile that EXISTS and has rotted is a regression, and is what this
        # guard is for. `--require-profile` turns adoption itself into a gate.
        if not timings_path.is_file():
            msg = f"no timing profile at {timings_path.name}"
            if args.require_profile:
                print(
                    f"[ERROR] {msg}, and --require-profile was given.\n"
                    f"        Bootstrap it with: python scripts/test_intelligence.py "
                    f"--update-timings",
                    file=sys.stderr,
                )
                return 1
            print(f"[INFO] {msg} — sharding falls back to uniform weights. Not a failure.")
            return 0
        ids = collect_test_ids(args.collect_path)
        if not ids:
            print(
                "[ERROR] pytest collected no tests, so coverage cannot be judged", file=sys.stderr
            )
            return 1
        known = [t for t in ids if t in stored]
        coverage = len(known) / len(ids)
        if coverage < args.min_coverage:
            print(
                f"[ERROR] timing profile covers {coverage:.0%} of {len(ids)} collected test(s); "
                f"{args.min_coverage:.0%} required.\n"
                f"        Shard balance degrades toward count-balancing below this.\n"
                f"        Refresh with: python scripts/test_intelligence.py --update-timings",
                file=sys.stderr,
            )
            return 1
        print(f"Test timing profile: PASSED ({coverage:.0%} of {len(ids)} tests timed)")
        return 0

    if args.publish:
        secret = os.getenv("INTERNAL_SECRET", "").strip()
        if not secret:
            print("[ERROR] INTERNAL_SECRET is not set; refusing to publish.", file=sys.stderr)
            return 1
        n = publish(records, args.url, secret, args.suite_id)
        print(f"published {n} run(s) to The Chaos Party at {args.url}")
        return 0

    # --- default: report
    if not records:
        print(f"No results at {args.results}. Run pytest first.")
        return 0

    flaky, unstable = find_flaky(records)
    merged = {**stored, **measured}
    runs = len({r.get("run_id") for r in records})
    total = sum(measured.values())

    print(f"records {len(records)}  tests {len(measured)}  runs {runs}  total {total / 1000:.1f}s")

    slowest = sorted(measured.items(), key=lambda kv: -kv[1])[:10]
    if slowest:
        share = sum(v for _, v in slowest) / total * 100 if total else 0
        print(f"\nSlowest 10 ({share:.0f}% of total runtime):")
        for name, ms in slowest:
            print(f"  {ms:>9.1f}ms  {name}")

    print(f"\nFlaky (disagreed with itself at one commit): {len(flaky)}")
    for f in flaky[:15]:
        print(f"  {f['test']}  @ {', '.join(f['commits'][:3])}")
    if unstable:
        print(f"\nUnstable across commits (likely broken-then-fixed): {len(unstable)}")
        for u in unstable[:10]:
            print(f"  {u['test']}")

    print("\nShard balance from the current profile:")
    for n in (2, 4, 8):
        totals = shard_totals(plan_shards(sorted(merged), merged, n), merged)
        if not totals:
            continue
        longest, mean = max(totals), sum(totals) / len(totals)
        print(
            f"  {n} shards -> longest {longest / 1000:>6.1f}s  "
            f"imbalance {longest / mean:.2f}x  (serial {total / 1000:.1f}s)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run the estate's immune scan: sense, normalise, remember, grade.

    python scripts/immune_scan.py                     # full sweep, report only
    python scripts/immune_scan.py --changed-only      # grade the diff vs main
    python scripts/immune_scan.py --sarif out.sarif   # write merged SARIF
    python scripts/immune_scan.py --write-baseline    # redefine "self"
    python scripts/immune_scan.py --gate              # exit non-zero on regression
    python scripts/immune_scan.py --merge sarif/*.sarif   # merge, do not run

EXIT CODES
    0  no regression against the baseline, and every required sensor could see
    1  a regression, or a required sensor that could not see
    2  the scan itself could not be trusted to run

WHAT `--gate` FAILS ON, AND WHY THAT LIST IS SHORT
--------------------------------------------------
It fails on findings NEW against the baseline, and on required sensors that
came back `absent`, `failed`, `unreadable` or `blind`. It does not fail on the
estate's existing findings, because a gate that fails on the backlog fails on
every pull request, and a gate that fails on every pull request is one
reviewers learn to bypass. The backlog is ranked (`--debt`) and worked down
deliberately; the gate's job is to stop it growing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.immune import grade as grading  # noqa: E402
from src.immune.memory import (  # noqa: E402
    apply_memory,
    baseline_sensors,
    load_adjudications,
    load_baseline,
    split_by_baseline,
    split_unmeasured,
    write_baseline,
)
from src.immune.sarif import SarifUnreadable, load_sarif, merge  # noqa: E402
from src.immune.sensors import (
    Outcome,
    SensorResult,
    load_manifest,
    run_sensor,
)  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def tracked_files(root: Path, *, changed_against: str = "") -> list[str]:
    if changed_against:
        args = [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=d",
            f"{changed_against}...HEAD",
        ]
    else:
        args = ["git", "ls-files"]
    proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
        args, cwd=str(root), capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return []
    # An unresolved merge makes `ls-files` emit one entry per stage, so the
    # same path arrives two or three times and every per-file figure derived
    # from it is inflated. Deduplicate rather than trusting the line count.
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def head_commit(root: Path) -> str:
    proc = subprocess.run(  # noqa: S603,S607
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _sense(args: argparse.Namespace) -> list[SensorResult]:
    if args.merge:
        results: list[SensorResult] = []
        for pattern in args.merge:
            for path in sorted(Path().glob(pattern)) or [Path(pattern)]:
                name = path.stem
                try:
                    results.append(SensorResult(name, Outcome.OK, load_sarif(path, tool_hint=name)))
                except SarifUnreadable as exc:
                    results.append(SensorResult(name, Outcome.UNREADABLE, detail=str(exc)))
        return results
    only = set(args.sensor or [])
    return [
        run_sensor(sensor, cwd=ROOT, verify_probe=not args.no_probe)
        for sensor in load_manifest(ROOT / "config/immune/sensors.yaml")
        if not only or sensor.name in only
    ]


def _print_sensors(results: list[SensorResult]) -> None:
    print("── sensors ─────────────────────────────────────────────────")
    for result in results:
        mark = {
            Outcome.OK: "ok  ",
            Outcome.ABSENT: "gap ",
            Outcome.FAILED: "FAIL",
            Outcome.UNREADABLE: "FAIL",
            Outcome.BLIND: "BLIND",
        }[result.outcome]
        need = " (required)" if result.required else ""
        print(f"  {mark:5} {result.name:12}{need:11} {result.detail}")


def _print_memory(report) -> None:
    if report.suppressed:
        print("\n── memory ──────────────────────────────────────────────────")
        print(f"  {len(report.suppressed)} finding(s) suppressed by adjudication")
    problems = report.expired or report.rotted or report.malformed or report.autoimmune
    if not problems:
        return
    print("\n── memory needs attention ──────────────────────────────────")
    for adj in report.expired:
        print(
            f"  EXPIRED   {adj.rule_id} {adj.path or '(rule-wide)'} — review_by {adj.review_by or 'never set'}"
        )
    for adj, why in report.rotted:
        print(f"  ROTTED    {adj.rule_id} {adj.path or '(rule-wide)'} — {why}")
    for adj, defects in report.malformed:
        print(f"  MALFORMED {adj.rule_id or '(no rule)'} — {'; '.join(defects)}")
    for rule, paths in report.autoimmune.items():
        print(
            f"  AUTOIMMUNE {rule} adjudicated false-positive in {len(paths)} files — "
            "tune or drop the rule rather than suppressing each instance"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--merge",
        nargs="*",
        help="merge existing SARIF files instead of running sensors",
    )
    parser.add_argument("--sensor", action="append", help="run only this sensor (repeatable)")
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="skip probe verification (faster, weaker)",
    )
    parser.add_argument(
        "--changed-only",
        metavar="REF",
        nargs="?",
        const="origin/main",
        help="grade only files changed against REF (default origin/main)",
    )
    parser.add_argument("--sarif", metavar="PATH", help="write the merged SARIF document here")
    parser.add_argument("--json", metavar="PATH", help="write a machine-readable summary here")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the current findings as 'self'",
    )
    parser.add_argument("--debt", action="store_true", help="print churn-weighted debt ranking")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero on regression or blind sensor",
    )
    args = parser.parse_args(argv)

    results = _sense(args)
    _print_sensors(results)

    blocking = [r for r in results if r.blocking]
    blind = [r.name for r in results if r.outcome is Outcome.BLIND]
    # Anything REQUIRED that did not produce a trustworthy reading caps the
    # grade -- not only the sensors a probe caught lying. Failed, absent and
    # unreadable are the same epistemic situation as blind: the estate did not
    # look. The first version of this file capped on `blind` alone and printed
    # "grade A" on a run whose required security sensor had exited 2 without
    # scanning a single file.
    unseeing = [f"{r.name} ({r.outcome.value})" for r in results if r.blocking]
    usable = [r for r in results if r.outcome is Outcome.OK]
    if not usable:
        print(
            "\nNo sensor produced a usable reading. This is not a clean estate; "
            "it is an estate nothing looked at.",
            file=sys.stderr,
        )
        return 2

    report = merge((r.name, r.findings) for r in usable)
    findings, memory = apply_memory(
        report.findings,
        load_adjudications(ROOT / "config/immune/adjudications.yaml"),
        repo_root=ROOT,
    )
    _print_memory(memory)

    baseline_path = ROOT / "config/immune/baseline.json"
    baseline = load_baseline(baseline_path)
    # A finding from a sensor the baseline never ran is not a regression, it is
    # a first measurement. Gating on it would blame the next pull request for
    # whatever a newly installed scanner happens to notice.
    measured, unmeasured = split_unmeasured(findings, baseline_sensors(baseline_path))
    new, known = split_by_baseline(measured, baseline)

    population = tracked_files(ROOT, changed_against=args.changed_only or "")
    required = [r for r in results if r.required]
    confidence = (
        sum(1 for r in required if r.outcome is Outcome.OK) / len(required) if required else 1.0
    )
    graded = grading.grade(
        findings,
        tracked=population,
        repo_root=ROOT,
        unseeing=unseeing,
        confidence=confidence,
    )

    print("\n── vitals ──────────────────────────────────────────────────")
    print("  " + graded.explain().replace("\n", "\n  "))
    dist = graded.distribution()
    print("  distribution  " + "  ".join(f"{k}:{v}" for k, v in dist.items()))
    scope = f"changed vs {args.changed_only}" if args.changed_only else "whole tree"
    print(f"  scope         {scope} ({len(population)} file(s))")

    print("\n── against baseline ────────────────────────────────────────")
    if not baseline:
        print(
            "  no baseline recorded — everything counts as known. "
            "Run --write-baseline on a commit you are willing to defend."
        )
    else:
        print(f"  {len(new)} new, {len(known)} already known ({len(baseline)} in baseline)")
        if unmeasured:
            by_sensor: dict[str, int] = {}
            for finding in unmeasured:
                key = finding.sensor or finding.tool
                by_sensor[key] = by_sensor.get(key, 0) + 1
            print(
                "  not gated — no baseline has ever included these sensors: "
                + ", ".join(f"{k} ({v})" for k, v in sorted(by_sensor.items()))
            )
            print("  regenerate the baseline to bring them under the gate")
        for finding in sorted(new, key=lambda f: (-f.rank, f.path))[:15]:
            print(f"    NEW {finding.level:7} {finding.rule_id:24} {finding.located}")
        if len(new) > 15:
            print(f"    ... and {len(new) - 15} more")

    if graded.worst():
        print("\n── worst files ─────────────────────────────────────────────")
        for fg in graded.worst(8):
            if fg.weighted <= 0:
                break
            print(f"  {fg.grade}  {fg.density:7.2f}/KLOC  {fg.findings:3} finding(s)  {fg.path}")

    if args.debt:
        print("\n── debt, ranked by what keeping it costs ───────────────────")
        for item in grading.rank_debt(graded, repo_root=ROOT, limit=15):
            print(
                f"  {item.priority:9.1f}  {item.grade}  {item.path}"
                f"   (weight {item.weighted:.0f} x {item.changes} changes x {item.importers} importers)"
            )

    if args.sarif:
        target = Path(args.sarif)
        target.parent.mkdir(parents=True, exist_ok=True)
        merged = merge([("immune", findings)])
        target.write_text(json.dumps(merged.to_sarif(), indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {target} ({len(findings)} finding(s))")

    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "grade": graded.grade,
                    "provisional": graded.provisional,
                    "density": round(graded.density, 4),
                    "findings": len(findings),
                    "new_against_baseline": len(new),
                    "distribution": dist,
                    "confidence": round(confidence, 3),
                    "sensors": {r.name: r.outcome.value for r in results},
                    "memory": {
                        "suppressed": len(memory.suppressed),
                        "expired": len(memory.expired),
                        "rotted": len(memory.rotted),
                        "malformed": len(memory.malformed),
                        "autoimmune": sorted(memory.autoimmune),
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}")

    if args.write_baseline:
        if blocking or blind:
            print(
                "\nRefusing to write a baseline from a scan with blind or failed "
                "required sensors — that would record 'we could not see' as 'self'.",
                file=sys.stderr,
            )
            return 2
        count = write_baseline(
            findings,
            baseline_path,
            commit=head_commit(ROOT),
            sensors=[r.name for r in usable],
        )
        print(f"\nbaseline written: {count} fingerprint(s) at {head_commit(ROOT)[:12]}")
        return 0

    if args.gate:
        reasons = []
        if blocking:
            reasons.append(
                "required sensor(s) could not see: "
                + ", ".join(f"{r.name} ({r.outcome.value})" for r in blocking)
            )
        if baseline and new:
            reasons.append(f"{len(new)} finding(s) new against the baseline")
        if reasons:
            print("\nGATE FAILED:", file=sys.stderr)
            for reason in reasons:
                print(f"  - {reason}", file=sys.stderr)
            return 1
        print("\nGATE PASSED: no regression, and every required sensor reported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

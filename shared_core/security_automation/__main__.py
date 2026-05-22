"""
shared_core.security_automation.__main__ — CLI entry point.

Usage:
    # Scan for violations:
    python -m shared_core.security_automation scan src/

    # Scan with severity threshold:
    python -m shared_core.security_automation scan --severity high src/

    # Auto-fix violations (dry run):
    python -m shared_core.security_automation fix --dry-run src/

    # Auto-fix violations (for real):
    python -m shared_core.security_automation fix src/

    # Generate compliance report:
    python -m shared_core.security_automation report src/

    # Run quality gate (exit 1 on failure):
    python -m shared_core.security_automation gate src/

    # Watch mode (continuous scanning):
    python -m shared_core.security_automation watch src/
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

from shared_core.security_automation.remediator import AutoRemediator
from shared_core.security_automation.scanner import Category, SecurityScanner, Severity, Violation
from shared_core.security_automation.telemetry import (
    QualityGate,
    ScanResult,
    SecurityTelemetry,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="security_automation",
        description="Proactive Security Automation Framework — "
                    "prevents recurrence of CodeQL security violations",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- scan ---
    scan_parser = subparsers.add_parser("scan", help="Scan for security violations")
    scan_parser.add_argument(
        "paths", nargs="+", help="Paths to scan (files or directories)"
    )
    scan_parser.add_argument(
        "--severity", "-s",
        choices=["critical", "high", "medium", "low", "info"],
        default="low",
        help="Minimum severity to report (default: low)",
    )
    scan_parser.add_argument(
        "--category", "-c",
        choices=[c.value for c in Category],
        help="Filter by category (e.g., CWE-117, PY-001)",
    )
    scan_parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    scan_parser.add_argument(
        "--output", "-o",
        help="Write output to file instead of stdout",
    )
    scan_parser.add_argument(
        "--save-telemetry",
        action="store_true",
        help="Save scan results to telemetry store",
    )
    scan_parser.add_argument(
        "--telemetry-dir",
        default=".security_telemetry",
        help="Telemetry storage directory (default: .security_telemetry)",
    )

    # --- fix ---
    fix_parser = subparsers.add_parser("fix", help="Auto-fix security violations")
    fix_parser.add_argument(
        "paths", nargs="+", help="Paths to fix (files or directories)"
    )
    fix_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        default=True,
        help="Report fixes without modifying files (default: True)",
    )
    fix_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply fixes (overrides --dry-run)",
    )
    fix_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create .bak files before fixing",
    )
    fix_parser.add_argument(
        "--severity", "-s",
        choices=["critical", "high", "medium", "low", "info"],
        default="low",
        help="Minimum severity to fix (default: low)",
    )

    # --- report ---
    report_parser = subparsers.add_parser("report", help="Generate compliance report")
    report_parser.add_argument(
        "paths", nargs="+", help="Paths to scan for report"
    )
    report_parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown"],
        default="markdown",
        help="Report format (default: markdown)",
    )
    report_parser.add_argument(
        "--output", "-o",
        help="Write report to file instead of stdout",
    )
    report_parser.add_argument(
        "--telemetry-dir",
        default=".security_telemetry",
        help="Telemetry storage directory (default: .security_telemetry)",
    )
    report_parser.add_argument(
        "--save",
        action="store_true",
        help="Save scan results to telemetry store",
    )

    # --- gate ---
    gate_parser = subparsers.add_parser("gate", help="Run quality gate check")
    gate_parser.add_argument(
        "paths", nargs="+", help="Paths to scan for gate check"
    )
    gate_parser.add_argument(
        "--max-critical", type=int, default=0,
        help="Max allowed critical violations (default: 0)",
    )
    gate_parser.add_argument(
        "--max-high", type=int, default=0,
        help="Max allowed high violations (default: 0)",
    )
    gate_parser.add_argument(
        "--max-medium", type=int, default=50,
        help="Max allowed medium violations (default: 50)",
    )
    gate_parser.add_argument(
        "--max-low", type=int, default=100,
        help="Max allowed low violations (default: 100)",
    )
    gate_parser.add_argument(
        "--max-total", type=int, default=150,
        help="Max allowed total violations (default: 150)",
    )
    gate_parser.add_argument(
        "--telemetry-dir",
        default=".security_telemetry",
        help="Telemetry storage directory",
    )
    gate_parser.add_argument(
        "--save",
        action="store_true",
        help="Save scan results to telemetry store",
    )

    # --- watch ---
    watch_parser = subparsers.add_parser(
        "watch", help="Watch for file changes and re-scan"
    )
    watch_parser.add_argument(
        "paths", nargs="+", help="Paths to watch"
    )
    watch_parser.add_argument(
        "--interval", "-i",
        type=float,
        default=30.0,
        help="Scan interval in seconds (default: 30)",
    )
    watch_parser.add_argument(
        "--severity", "-s",
        choices=["critical", "high", "medium", "low", "info"],
        default="low",
        help="Minimum severity to report (default: low)",
    )
    watch_parser.add_argument(
        "--telemetry-dir",
        default=".security_telemetry",
        help="Telemetry storage directory",
    )

    return parser


def _severity_from_string(s: str) -> Severity:
    """Convert string to Severity enum."""
    return Severity(s)


def _filter_violations(
    violations: List[Violation],
    min_severity: Severity,
    category: Optional[str] = None,
) -> List[Violation]:
    """Filter violations by severity and category."""
    severity_order = [
        Severity.INFO, Severity.LOW, Severity.MEDIUM,
        Severity.HIGH, Severity.CRITICAL,
    ]
    min_idx = severity_order.index(min_severity)

    filtered = []
    for v in violations:
        v_idx = severity_order.index(v.severity)
        if v_idx < min_idx:
            continue
        if category and v.category.value != category:
            continue
        filtered.append(v)
    return filtered


def _format_violations_text(violations: List[Violation]) -> str:
    """Format violations as human-readable text."""
    if not violations:
        return "✅ No security violations found!"

    lines = []
    for v in violations:
        lines.append(
            f"[{v.category.value}] {v.severity.value.upper()} "
            f"{v.file}:{v.line}:{v.col} — {v.message}"
        )
        if v.suggestion:
            lines.append(f"  💡 {v.suggestion}")
    return "\n".join(lines)


def _format_violations_json(violations: List[Violation]) -> str:
    """Format violations as JSON."""
    import json
    from dataclasses import asdict
    return json.dumps([asdict(v) for v in violations], indent=2, default=str)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> int:
    """Handle the 'scan' command."""
    scanner = SecurityScanner()
    all_violations = []

    for path in args.paths:
        p = Path(path)
        if p.is_file():
            all_violations.extend(scanner.scan_file(str(p)))
        elif p.is_dir():
            all_violations.extend(scanner.scan_path(str(p)))
        else:
            print(f"Warning: {path} not found, skipping", file=sys.stderr)

    # Apply filters
    min_sev = _severity_from_string(args.severity)
    violations = _filter_violations(all_violations, min_sev, args.category)

    # Format output
    if args.format == "json":
        output = _format_violations_json(violations)
    else:
        output = _format_violations_text(violations)

    # Write to file or stdout
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Results written to {args.output}")
    else:
        print(output)

    # Save telemetry
    if args.save_telemetry:
        telemetry = SecurityTelemetry(storage_dir=args.telemetry_dir)
        result = ScanResult.from_violations(
            violations,
            commit=SecurityTelemetry.get_commit_sha(),
            branch=SecurityTelemetry.get_branch(),
        )
        saved_path = telemetry.save(result)
        print(f"Telemetry saved to {saved_path}")

    # Print summary
    print(f"\nScan complete: {len(violations)} violations found "
          f"(of {len(all_violations)} total before filtering)")

    # Return exit code based on findings
    critical_high = [v for v in violations if v.severity in (Severity.CRITICAL, Severity.HIGH)]
    return 1 if critical_high else 0


def cmd_fix(args: argparse.Namespace) -> int:
    """Handle the 'fix' command."""
    scanner = SecurityScanner()
    all_violations = []

    for path in args.paths:
        p = Path(path)
        if p.is_file():
            all_violations.extend(scanner.scan_file(str(p)))
        elif p.is_dir():
            all_violations.extend(scanner.scan_path(str(p)))

    # Apply severity filter
    min_sev = _severity_from_string(args.severity)
    violations = _filter_violations(all_violations, min_sev)

    fixable = [v for v in violations if v.fixable]
    unfixable = [v for v in violations if not v.fixable]

    print(f"Found {len(violations)} violations ({len(fixable)} auto-fixable)")

    if unfixable:
        print(f"\n⚠️  {len(unfixable)} violations require manual review:")
        for v in unfixable:
            print(f"  [{v.category.value}] {v.file}:{v.line} — {v.message}")

    if not fixable:
        print("No auto-fixable violations found.")
        return 0

    # Determine if we're actually applying fixes
    dry_run = not args.apply
    backup = not args.no_backup

    remediator = AutoRemediator(dry_run=dry_run, backup=backup)
    fixes = remediator.remediate(fixable)

    if dry_run:
        print(f"\n🔧 DRY RUN — {len(fixes)} files would be modified:")
    else:
        print(f"\n✅ Applied fixes to {len(fixes)} files:")

    for fix in fixes:
        status = "would fix" if dry_run else "fixed"
        print(f"  {status} {fix['file']} ({fix['violations_fixed']} violations)")

    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Handle the 'report' command."""
    start_time = time.time()

    scanner = SecurityScanner()
    all_violations = []

    for path in args.paths:
        p = Path(path)
        if p.is_file():
            all_violations.extend(scanner.scan_file(str(p)))
        elif p.is_dir():
            all_violations.extend(scanner.scan_path(str(p)))

    scan_duration = time.time() - start_time

    # Build scan result
    result = ScanResult.from_violations(
        all_violations,
        commit=SecurityTelemetry.get_commit_sha(),
        branch=SecurityTelemetry.get_branch(),
        scan_duration=scan_duration,
    )

    # Compute diff if telemetry exists
    telemetry = SecurityTelemetry(storage_dir=args.telemetry_dir)
    diff = None
    previous = telemetry.load_latest()
    if previous:
        diff = telemetry.diff(before=previous, after=result)

    # Generate report
    if args.format == "json":
        output = telemetry.generate_json_report(result)
    elif args.format == "text":
        output = telemetry.generate_text_report(result)
    else:
        gate = QualityGate()
        gate_result = gate.evaluate(result)
        output = telemetry.generate_markdown_report(result, diff=diff, gate_result=gate_result)

    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report written to {args.output}")
    else:
        print(output)

    # Save telemetry
    if args.save:
        saved_path = telemetry.save(result)
        print(f"Telemetry saved to {saved_path}")

    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    """Handle the 'gate' command."""
    scanner = SecurityScanner()
    all_violations = []

    for path in args.paths:
        p = Path(path)
        if p.is_file():
            all_violations.extend(scanner.scan_file(str(p)))
        elif p.is_dir():
            all_violations.extend(scanner.scan_path(str(p)))

    result = ScanResult.from_violations(
        all_violations,
        commit=SecurityTelemetry.get_commit_sha(),
        branch=SecurityTelemetry.get_branch(),
    )

    gate = QualityGate(
        max_critical=args.max_critical,
        max_high=args.max_high,
        max_medium=args.max_medium,
        max_low=args.max_low,
        max_total=args.max_total,
    )
    gate_result = gate.evaluate(result)

    # Print gate status
    if gate_result.passed:
        print("✅ Quality gate PASSED")
        print(f"   Total violations: {result.total_violations} "
              f"(C:{result.critical} H:{result.high} M:{result.medium} "
              f"L:{result.low} I:{result.info})")
    else:
        print("❌ Quality gate FAILED")
        for failure in gate_result.failures:
            print(f"   {failure}")
        print(f"   Total violations: {result.total_violations} "
              f"(C:{result.critical} H:{result.high} M:{result.medium} "
              f"L:{result.low} I:{result.info})")

    # Save telemetry
    if args.save:
        telemetry = SecurityTelemetry(storage_dir=args.telemetry_dir)
        telemetry.save(result)

    return 0 if gate_result.passed else 1


def cmd_watch(args: argparse.Namespace) -> int:
    """Handle the 'watch' command — continuous scanning."""
    min_sev = _severity_from_string(args.severity)
    scanner = SecurityScanner()

    print(f"👀 Watching for security violations (interval: {args.interval}s)")
    print("   Press Ctrl+C to stop\n")

    try:
        while True:
            all_violations = []
            for path in args.paths:
                p = Path(path)
                if p.is_file():
                    all_violations.extend(scanner.scan_file(str(p)))
                elif p.is_dir():
                    all_violations.extend(scanner.scan_path(str(p)))

            violations = _filter_violations(all_violations, min_sev)

            if violations:
                critical_high = [
                    v for v in violations
                    if v.severity in (Severity.CRITICAL, Severity.HIGH)
                ]
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"⚠️  {len(violations)} violations "
                    f"({len(critical_high)} critical/high)"
                )
                for v in critical_high[:5]:
                    print(f"  [{v.category.value}] {v.file}:{v.line} — {v.message}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] ✅ No violations")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n👋 Watch stopped")
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "scan": cmd_scan,
        "fix": cmd_fix,
        "report": cmd_report,
        "gate": cmd_gate,
        "watch": cmd_watch,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

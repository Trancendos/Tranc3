"""
shared_core.security_automation.telemetry — Security telemetry collector.

Tracks security compliance trends over time so teams can measure improvement
and detect regressions. Data is stored as JSON files that can be consumed by
dashboards, alerting systems, or CI quality gates.

Features:
    - Scan result persistence with timestamps
    - Trend analysis (violations over time)
    - Category-level breakdown and severity distribution
    - Diff between scans (new, fixed, persistent violations)
    - Quality gate evaluation (pass/fail thresholds)
    - JSON and text report generation
    - Markdown dashboard report for CI artifacts
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared_core.security_automation.scanner import Severity, Violation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """A single scan result with metadata."""

    timestamp: str
    commit: str
    branch: str
    total_violations: int
    critical: int
    high: int
    medium: int
    low: int
    info: int
    by_category: Dict[str, int]
    by_file: Dict[str, int]
    violations: List[Dict[str, Any]]
    scan_duration_seconds: float = 0.0

    @classmethod
    def from_violations(
        cls,
        violations: List[Violation],
        *,
        commit: str = "unknown",
        branch: str = "unknown",
        scan_duration: float = 0.0,
    ) -> "ScanResult":
        """Create a ScanResult from a list of Violations."""
        now = datetime.now(timezone.utc).isoformat()
        sev_counts = Counter(v.severity for v in violations)
        cat_counts = Counter(v.category.value for v in violations)
        file_counts = Counter(v.file for v in violations)

        return cls(
            timestamp=now,
            commit=commit,
            branch=branch,
            total_violations=len(violations),
            critical=sev_counts.get(Severity.CRITICAL, 0),
            high=sev_counts.get(Severity.HIGH, 0),
            medium=sev_counts.get(Severity.MEDIUM, 0),
            low=sev_counts.get(Severity.LOW, 0),
            info=sev_counts.get(Severity.INFO, 0),
            by_category=dict(cat_counts),
            by_file=dict(file_counts),
            violations=[asdict(v) for v in violations],
            scan_duration_seconds=scan_duration,
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "ScanResult":
        """Deserialize from JSON string."""
        d = json.loads(data)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class QualityGate:
    """Thresholds for CI quality gate evaluation.

    All thresholds are maximum allowed counts. A scan passes the gate
    if all counts are at or below the configured thresholds.
    """

    max_critical: int = 0
    max_high: int = 0
    max_medium: int = 50
    max_low: int = 100
    max_total: int = 150

    def evaluate(self, result: ScanResult) -> "GateResult":
        """Evaluate a scan result against this quality gate."""
        failures = []

        if result.critical > self.max_critical:
            failures.append(f"Critical violations: {result.critical} > max {self.max_critical}")
        if result.high > self.max_high:
            failures.append(f"High violations: {result.high} > max {self.max_high}")
        if result.medium > self.max_medium:
            failures.append(f"Medium violations: {result.medium} > max {self.max_medium}")
        if result.low > self.max_low:
            failures.append(f"Low violations: {result.low} > max {self.max_low}")
        if result.total_violations > self.max_total:
            failures.append(f"Total violations: {result.total_violations} > max {self.max_total}")

        return GateResult(
            passed=len(failures) == 0,
            failures=failures,
            gate_config=asdict(self),
        )


@dataclass
class GateResult:
    """Result of quality gate evaluation."""

    passed: bool
    failures: List[str]
    gate_config: Dict[str, Any]


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------


@dataclass
class ScanDiff:
    """Difference between two scans — new, fixed, and persistent violations."""

    new_violations: List[Dict[str, Any]]
    fixed_violations: List[Dict[str, Any]]
    persistent_violations: List[Dict[str, Any]]
    new_count: int = 0
    fixed_count: int = 0
    persistent_count: int = 0
    delta_total: int = 0

    @property
    def improved(self) -> bool:
        """Whether the codebase improved (more fixed than new)."""
        return self.fixed_count > self.new_count


@dataclass
class TrendPoint:
    """A single data point in a trend series."""

    timestamp: str
    total: int
    critical: int
    high: int
    medium: int
    low: int
    info: int


# ---------------------------------------------------------------------------
# SecurityTelemetry — main class
# ---------------------------------------------------------------------------


class SecurityTelemetry:
    """Security telemetry collector and analyzer.

    Persists scan results, computes trends, diffs scans, and generates
    reports. Designed to be used in CI pipelines to track security
    compliance over time.

    Usage:
        telemetry = SecurityTelemetry(storage_dir=".security_telemetry")

        # After a scan:
        result = ScanResult.from_violations(violations, commit=sha, branch=branch)
        telemetry.save(result)

        # Trend analysis:
        trends = telemetry.trend()
        print(f"Average violations over {len(trends)} scans: {statistics.mean(t.total for t in trends):.1f}")

        # Diff two most recent scans:
        diff = telemetry.diff()
        print(f"New: {diff.new_count}, Fixed: {diff.fixed_count}")

        # Quality gate:
        gate = QualityGate(max_critical=0, max_high=0, max_medium=20)
        result = gate.evaluate(latest_result)
        if not result.passed:
            sys.exit(1)
    """

    def __init__(self, storage_dir: str = ".security_telemetry") -> None:
        """Initialize the telemetry collector.

        Args:
            storage_dir: Directory to store scan results. Created if needed.
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------

    def save(self, result: ScanResult) -> Path:
        """Save a scan result to disk.

        Args:
            result: The scan result to persist.

        Returns:
            Path to the saved file.
        """
        # Use timestamp + commit for unique filename (microseconds for uniqueness)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        commit_short = result.commit[:8] if len(result.commit) >= 8 else result.commit
        filename = f"scan_{ts}_{commit_short}.json"
        filepath = self.storage_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.to_json())

        # Also maintain a "latest" symlink/copy for easy access
        latest_path = self.storage_dir / "latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(result.to_json())

        return filepath

    def load_latest(self) -> Optional[ScanResult]:
        """Load the most recent scan result."""
        latest_path = self.storage_dir / "latest.json"
        if latest_path.exists():
            with open(latest_path, "r", encoding="utf-8") as f:
                return ScanResult.from_json(f.read())
        return None

    def load_all(self) -> List[ScanResult]:
        """Load all saved scan results, sorted by timestamp (oldest first)."""
        results = []
        for filepath in sorted(self.storage_dir.glob("scan_*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    results.append(ScanResult.from_json(f.read()))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return results

    # -------------------------------------------------------------------
    # Diff
    # -------------------------------------------------------------------

    def diff(
        self,
        before: Optional[ScanResult] = None,
        after: Optional[ScanResult] = None,
    ) -> ScanDiff:
        """Compute the diff between two scans.

        Args:
            before: The earlier scan. Defaults to second-most-recent.
            after: The later scan. Defaults to most recent.

        Returns:
            ScanDiff showing new, fixed, and persistent violations.
        """
        if before is None or after is None:
            all_results = self.load_all()
            if len(all_results) < 2:
                return ScanDiff(
                    new_violations=[],
                    fixed_violations=[],
                    persistent_violations=[],
                )
            before = before or all_results[-2]
            after = after or all_results[-1]

        # Create fingerprints for comparison
        def _fingerprint(v: Dict) -> str:
            return f"{v.get('category', '')}:{v.get('file', '')}:{v.get('line', '')}"

        before_set = {_fingerprint(v) for v in before.violations}
        after_set = {_fingerprint(v) for v in after.violations}

        before_map = {_fingerprint(v): v for v in before.violations}
        after_map = {_fingerprint(v): v for v in after.violations}

        new_fps = after_set - before_set
        fixed_fps = before_set - after_set
        persistent_fps = before_set & after_set

        return ScanDiff(
            new_violations=[after_map[fp] for fp in new_fps],
            fixed_violations=[before_map[fp] for fp in fixed_fps],
            persistent_violations=[after_map[fp] for fp in persistent_fps],
            new_count=len(new_fps),
            fixed_count=len(fixed_fps),
            persistent_count=len(persistent_fps),
            delta_total=after.total_violations - before.total_violations,
        )

    # -------------------------------------------------------------------
    # Trend
    # -------------------------------------------------------------------

    def trend(self, limit: int = 0) -> List[TrendPoint]:
        """Compute violation trend over time.

        Args:
            limit: Maximum number of data points. 0 = all.

        Returns:
            List of TrendPoint objects sorted chronologically.
        """
        all_results = self.load_all()
        if limit > 0:
            all_results = all_results[-limit:]

        return [
            TrendPoint(
                timestamp=r.timestamp,
                total=r.total_violations,
                critical=r.critical,
                high=r.high,
                medium=r.medium,
                low=r.low,
                info=r.info,
            )
            for r in all_results
        ]

    # -------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------

    def generate_text_report(self, result: ScanResult) -> str:
        """Generate a human-readable text report.

        Args:
            result: The scan result to report on.

        Returns:
            Formatted text report.
        """
        lines = [
            "=" * 70,
            "SECURITY SCAN REPORT",
            "=" * 70,
            f"Timestamp : {result.timestamp}",
            f"Commit    : {result.commit}",
            f"Branch    : {result.branch}",
            f"Duration  : {result.scan_duration_seconds:.2f}s",
            "-" * 70,
            f"Total Violations : {result.total_violations}",
            f"  Critical : {result.critical}",
            f"  High     : {result.high}",
            f"  Medium   : {result.medium}",
            f"  Low      : {result.low}",
            f"  Info     : {result.info}",
            "-" * 70,
        ]

        if result.by_category:
            lines.append("By Category:")
            for cat, count in sorted(result.by_category.items(), key=lambda x: -x[1]):
                lines.append(f"  {cat:12s} : {count}")
            lines.append("-" * 70)

        if result.by_file:
            lines.append("By File (top 10):")
            sorted_files = sorted(result.by_file.items(), key=lambda x: -x[1])[:10]
            for filepath, count in sorted_files:
                lines.append(f"  {count:3d} : {filepath}")
            lines.append("-" * 70)

        lines.append("=" * 70)
        return "\n".join(lines)

    def generate_markdown_report(
        self,
        result: ScanResult,
        diff: Optional[ScanDiff] = None,
        gate_result: Optional[GateResult] = None,
    ) -> str:
        """Generate a Markdown report suitable for CI artifacts or PR comments.

        Args:
            result: The scan result to report on.
            diff: Optional diff from previous scan.
            gate_result: Optional quality gate evaluation.

        Returns:
            Markdown-formatted report string.
        """
        lines = [
            "# 🔒 Security Scan Report",
            "",
            f"**Timestamp:** {result.timestamp}  ",
            f"**Commit:** `{result.commit}`  ",
            f"**Branch:** `{result.branch}`  ",
            f"**Duration:** {result.scan_duration_seconds:.2f}s  ",
            "",
        ]

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| Critical | {result.critical} |")
        lines.append(f"| High | {result.high} |")
        lines.append(f"| Medium | {result.medium} |")
        lines.append(f"| Low | {result.low} |")
        lines.append(f"| Info | {result.info} |")
        lines.append(f"| **Total** | **{result.total_violations}** |")
        lines.append("")

        # Quality gate
        if gate_result is not None:
            status = "✅ PASSED" if gate_result.passed else "❌ FAILED"
            lines.append(f"## Quality Gate: {status}")
            lines.append("")
            if gate_result.failures:
                lines.append("Failures:")
                for f in gate_result.failures:
                    lines.append(f"- {f}")
                lines.append("")

        # Diff
        if diff is not None:
            direction = "📈" if not diff.improved else "📉"
            lines.append(f"## Trend {direction}")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append(f"| New violations | {diff.new_count} |")
            lines.append(f"| Fixed violations | {diff.fixed_count} |")
            lines.append(f"| Persistent | {diff.persistent_count} |")
            lines.append(f"| Delta | {diff.delta_total:+d} |")
            lines.append("")

        # By category
        if result.by_category:
            lines.append("## By Category")
            lines.append("")
            lines.append("| Category | Count |")
            lines.append("|----------|-------|")
            for cat, count in sorted(result.by_category.items(), key=lambda x: -x[1]):
                lines.append(f"| {cat} | {count} |")
            lines.append("")

        # By file (top 10)
        if result.by_file:
            lines.append("## Hotspot Files (top 10)")
            lines.append("")
            lines.append("| File | Violations |")
            lines.append("|------|-----------|")
            sorted_files = sorted(result.by_file.items(), key=lambda x: -x[1])[:10]
            for filepath, count in sorted_files:
                lines.append(f"| `{filepath}` | {count} |")
            lines.append("")

        # Individual violations (limit to 50 for readability)
        if result.violations:
            lines.append("## Violations")
            lines.append("")
            for i, v in enumerate(result.violations[:50]):
                cat = v.get("category", "unknown")
                sev = v.get("severity", "unknown")
                fpath = v.get("file", "unknown")
                line = v.get("line", "?")
                msg = v.get("message", "")
                suggestion = v.get("suggestion", "")
                lines.append(
                    f"### {i + 1}. [{cat}] {sev.value.upper() if hasattr(sev, 'value') else str(sev).upper()} — `{fpath}:{line}`",
                )
                lines.append("")
                if msg:
                    lines.append(f"**Issue:** {msg}  ")
                if suggestion:
                    lines.append(f"**Fix:** {suggestion}  ")
                lines.append("")

            if len(result.violations) > 50:
                lines.append(f"_...and {len(result.violations) - 50} more violations_")
                lines.append("")

        return "\n".join(lines)

    def generate_json_report(self, result: ScanResult) -> str:
        """Generate a JSON report for machine consumption."""
        return result.to_json()

    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------

    def cleanup(self, keep: int = 30) -> int:
        """Remove old scan results, keeping only the most recent ones.

        Args:
            keep: Number of results to retain.

        Returns:
            Number of files removed.
        """
        scan_files = sorted(self.storage_dir.glob("scan_*.json"))
        to_remove = scan_files[:-keep] if len(scan_files) > keep else []
        for f in to_remove:
            f.unlink()
        return len(to_remove)

    # -------------------------------------------------------------------
    # Convenience
    # -------------------------------------------------------------------

    @staticmethod
    def get_commit_sha() -> str:
        """Get the current git commit SHA."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)  # nosec B110 – graceful fallback when git unavailable
        return "unknown"

    @staticmethod
    def get_branch() -> str:
        """Get the current git branch name."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)  # nosec B110 – graceful fallback when git unavailable
        return "unknown"

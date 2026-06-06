"""
shared_core.security_automation.security_reporter — Context-rich security intelligence reporter.

Reads the adaptive scanner's history.json and patterns.json and produces:
  1. Per-rule summaries with human-readable context from the rule catalog
  2. Trend analysis (improving / degrading / stable) across scans
  3. Entity-aware hotspot identification (which platform entities own the most violations)
  4. Remediation guidance with auto-fix capability status
  5. CLI entry point for manual reporting

Usage:
    # Programmatic
    reporter = SecurityReporter()
    report = reporter.generate_report()
    print(reporter.format_report(report))

    # CLI
    python -m shared_core.security_automation.security_reporter [--json] [--top N]
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from shared_core.security_automation.rule_catalog import (
    entity_for_directory,
    rule_info,
)

_DEFAULT_LEARNING_DIR = ".security_learning"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RuleSummary:
    rule_id: str
    rule_name: str
    severity: str
    total_observations: int
    directory_count: int
    top_directories: List[Tuple[str, str, int]]  # (directory, entity, obs_count)
    trend: str  # "improving" | "degrading" | "stable" | "unknown"
    trend_delta: int  # positive = more violations, negative = fewer
    auto_fixable: bool
    remediation_summary: str
    what_it_means: str


@dataclass
class EntityHotspot:
    entity: str
    total_observations: int
    rule_breakdown: Dict[str, int]  # rule_id → count
    highest_severity: str


@dataclass
class SecurityReport:
    generated_at: str
    total_observations: int
    total_rules_active: int
    total_directories_affected: int
    scan_count: int
    overall_trend: str
    rule_summaries: List[RuleSummary]
    entity_hotspots: List[EntityHotspot]
    auto_fixable_count: int
    auto_fixable_observations: int
    recommendations: List[str]


# ---------------------------------------------------------------------------
# SecurityReporter
# ---------------------------------------------------------------------------


class SecurityReporter:
    """Generates context-rich security intelligence reports from scanner learning data."""

    def __init__(self, learning_dir: str = _DEFAULT_LEARNING_DIR):
        self._learning_dir = learning_dir
        self._patterns: Dict[str, Any] = {}
        self._history: List[Dict] = []
        self._load()

    def _load(self) -> None:
        base = Path(self._learning_dir)
        patterns_file = base / "patterns.json"
        history_file = base / "history.json"

        if patterns_file.exists():
            try:
                with open(patterns_file, encoding="utf-8") as f:
                    self._patterns = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._patterns = {}

        if history_file.exists():
            try:
                with open(history_file, encoding="utf-8") as f:
                    self._history = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._history = []

    def generate_report(self) -> SecurityReport:
        """Build a full security intelligence report."""
        # Aggregate patterns by rule_id
        by_rule: Dict[str, Dict[str, int]] = defaultdict(dict)  # rule_id → {dir: obs}
        for key, obs in self._patterns.items():
            rule_id = obs.get("rule_id", "")
            directory = obs.get("directory", key.split(":")[1] if ":" in key else ".")
            count = obs.get("observation_count", 0)
            if rule_id and count > 0:
                by_rule[rule_id][directory] = count

        total_obs = sum(
            sum(dirs.values()) for dirs in by_rule.values()
        )
        total_dirs = len({d for dirs in by_rule.values() for d in dirs})

        # Compute trends from enriched history
        rule_summaries = []
        for rule_id, dir_counts in sorted(
            by_rule.items(), key=lambda x: -sum(x[1].values())
        ):
            trend, delta = self._compute_trend(rule_id)
            info = rule_info(rule_id)
            top_dirs = sorted(dir_counts.items(), key=lambda x: -x[1])[:5]
            top_with_entity = [
                (d, entity_for_directory(d), c) for d, c in top_dirs
            ]
            rule_summaries.append(
                RuleSummary(
                    rule_id=rule_id,
                    rule_name=info.name if info else rule_id,
                    severity=info.severity if info else "unknown",
                    total_observations=sum(dir_counts.values()),
                    directory_count=len(dir_counts),
                    top_directories=top_with_entity,
                    trend=trend,
                    trend_delta=delta,
                    auto_fixable=info.auto_fixable if info else False,
                    remediation_summary=info.remediation if info else "Manual review required.",
                    what_it_means=info.what_it_means if info else "",
                )
            )

        # Entity hotspots
        entity_obs: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for rule_id, dir_counts in by_rule.items():
            for directory, count in dir_counts.items():
                entity = entity_for_directory(directory)
                entity_obs[entity][rule_id] += count

        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}
        hotspots = []
        for entity, rule_counts in sorted(
            entity_obs.items(), key=lambda x: -sum(x[1].values())
        ):
            total = sum(rule_counts.values())
            highest = max(
                (rule_info(r) for r in rule_counts if rule_info(r)),
                key=lambda i: severity_rank.get(i.severity, 0),
                default=None,
            )
            hotspots.append(
                EntityHotspot(
                    entity=entity,
                    total_observations=total,
                    rule_breakdown=dict(rule_counts),
                    highest_severity=highest.severity if highest else "unknown",
                )
            )

        # Auto-fix counts
        auto_fixable_count = sum(1 for r in rule_summaries if r.auto_fixable)
        auto_fixable_obs = sum(r.total_observations for r in rule_summaries if r.auto_fixable)

        # Overall trend
        degrading = sum(1 for r in rule_summaries if r.trend == "degrading")
        improving = sum(1 for r in rule_summaries if r.trend == "improving")
        if degrading > improving:
            overall_trend = "degrading"
        elif improving > degrading:
            overall_trend = "improving"
        else:
            overall_trend = "stable"

        # Recommendations
        recommendations = self._build_recommendations(rule_summaries, hotspots)

        return SecurityReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_observations=total_obs,
            total_rules_active=len(by_rule),
            total_directories_affected=total_dirs,
            scan_count=len(self._history),
            overall_trend=overall_trend,
            rule_summaries=rule_summaries,
            entity_hotspots=hotspots[:10],
            auto_fixable_count=auto_fixable_count,
            auto_fixable_observations=auto_fixable_obs,
            recommendations=recommendations,
        )

    def format_report(self, report: SecurityReport) -> str:
        """Return a human-readable text report."""
        lines = [
            "=" * 72,
            "  TRANCENDOS PLATFORM — SECURITY INTELLIGENCE REPORT",
            f"  Generated: {report.generated_at}",
            "=" * 72,
            "",
            f"  Total observations : {report.total_observations:,}",
            f"  Active rules       : {report.total_rules_active}",
            f"  Directories hit    : {report.total_directories_affected}",
            f"  History entries    : {report.scan_count}",
            f"  Overall trend      : {report.overall_trend.upper()}",
            f"  Auto-fixable obs   : {report.auto_fixable_observations:,} ({report.auto_fixable_count} rules)",
            "",
        ]

        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "unknown": "⚪"}
        trend_icon = {"improving": "↓", "degrading": "↑", "stable": "→", "unknown": "?"}

        lines.append("── RULE BREAKDOWN ─────────────────────────────────────────────────")
        for r in report.rule_summaries:
            icon = severity_icon.get(r.severity, "⚪")
            trend = trend_icon.get(r.trend, "?")
            fixable = "✓ auto-fix" if r.auto_fixable else "  manual"
            delta_str = f"+{r.trend_delta}" if r.trend_delta > 0 else str(r.trend_delta)
            lines.append(
                f"\n  {icon} {r.rule_id} — {r.rule_name}  [{r.severity}]  {trend} {delta_str}  [{fixable}]"
            )
            lines.append(f"     Observations: {r.total_observations:,}  across {r.directory_count} directories")
            lines.append(f"     What it means: {r.what_it_means[:120]}...")
            lines.append(f"     Fix: {r.remediation_summary[:100]}...")
            lines.append("     Top hotspot directories:")
            for directory, entity, count in r.top_directories[:3]:
                lines.append(f"       {count:>6,}  {directory}  [{entity}]")

        lines.append("")
        lines.append("── ENTITY HOTSPOTS ─────────────────────────────────────────────────")
        for h in report.entity_hotspots[:7]:
            icon = severity_icon.get(h.highest_severity, "⚪")
            rules = ", ".join(f"{k}({v:,})" for k, v in sorted(h.rule_breakdown.items(), key=lambda x: -x[1])[:4])
            lines.append(f"  {icon} {h.entity:<40} {h.total_observations:>8,} obs  [{rules}]")

        lines.append("")
        lines.append("── RECOMMENDATIONS ─────────────────────────────────────────────────")
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"  {i}. {rec}")

        lines.append("")
        lines.append("=" * 72)
        return "\n".join(lines)

    def _compute_trend(self, rule_id: str) -> Tuple[str, int]:
        """Compare recent vs older scan history to determine trend direction.

        Compares the last 5 scans vs the 5 before that. Returns trend and delta.
        """
        # Only works with enriched history (new schema with per_rule_counts)
        enriched = [
            h for h in self._history
            if "per_rule_counts" in h
        ]
        if len(enriched) < 4:
            return "unknown", 0

        recent = enriched[-5:]
        older = enriched[-10:-5]
        if not older:
            return "unknown", 0

        def avg_count(entries: List[Dict]) -> float:
            counts = [e.get("per_rule_counts", {}).get(rule_id, 0) for e in entries]
            return sum(counts) / len(counts) if counts else 0.0

        recent_avg = avg_count(recent)
        older_avg = avg_count(older)
        delta = int(recent_avg - older_avg)

        if recent_avg < older_avg * 0.9:
            return "improving", delta
        elif recent_avg > older_avg * 1.1:
            return "degrading", delta
        return "stable", delta

    def _build_recommendations(
        self,
        rules: List[RuleSummary],
        hotspots: List[EntityHotspot],
    ) -> List[str]:
        recs = []

        # Highest-volume auto-fixable rule
        fixable = [r for r in rules if r.auto_fixable]
        if fixable:
            top = fixable[0]
            recs.append(
                f"Run AutoRemediatorV2 on {top.rule_id} ({top.rule_name}) — "
                f"{top.total_observations:,} observations auto-fixable across {top.directory_count} directories."
            )

        # Degrading rules
        degrading = [r for r in rules if r.trend == "degrading"]
        for r in degrading[:2]:
            recs.append(
                f"{r.rule_id} is DEGRADING (+{r.trend_delta} recent) — add pre-commit hook rule or lint check."
            )

        # High-severity unfixed rules
        high = [r for r in rules if r.severity in ("critical", "high") and not r.auto_fixable]
        for r in high[:2]:
            recs.append(
                f"{r.rule_id} ({r.rule_name}) severity={r.severity} requires manual review — {r.directory_count} directories affected."
            )

        # Entity with most observations
        if hotspots:
            top_entity = hotspots[0]
            recs.append(
                f"Focus sprint on '{top_entity.entity}' — {top_entity.total_observations:,} total observations "
                f"(highest_severity={top_entity.highest_severity})."
            )

        if not recs:
            recs.append("No critical recommendations — run AutoRemediatorV2 for routine cleanup.")

        return recs


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Trancendos Security Intelligence Reporter")
    parser.add_argument("--json", action="store_true", help="Output raw JSON report")
    parser.add_argument("--top", type=int, default=10, help="Max rules to show (default: 10)")
    parser.add_argument(
        "--learning-dir",
        default=_DEFAULT_LEARNING_DIR,
        help="Path to .security_learning directory",
    )
    args = parser.parse_args()

    reporter = SecurityReporter(learning_dir=args.learning_dir)
    report = reporter.generate_report()

    if args.json:
        import dataclasses
        print(json.dumps(dataclasses.asdict(report), indent=2, default=str))
    else:
        report.rule_summaries = report.rule_summaries[: args.top]
        print(reporter.format_report(report))

    # Exit non-zero if platform is degrading
    if report.overall_trend == "degrading":
        sys.exit(1)


if __name__ == "__main__":
    main()

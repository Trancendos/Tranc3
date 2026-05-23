"""
shared_core.security_automation.adaptive_scanner — Adaptive security scanner with learning.

Extends the base SecurityScanner with adaptive features:
    - Confidence scoring for each violation
    - Suppression of known false positives
    - Pattern learning from historical data
    - Persistent learning state (save/load)

The adaptive scanner wraps scan results with confidence levels based on
context (test files get lower confidence, known patterns get higher).

Zero-cost: All analysis is local, no external APIs required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared_core.security_automation.scanner import (
    Category,
    SecurityScanner,
    Violation,
)


class Confidence(Enum):
    """Confidence levels for adaptive violation assessment."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class AdaptiveViolation:
    """A security violation with confidence scoring."""
    violation: Violation
    confidence_level: Confidence = Confidence.MEDIUM
    suppressed: bool = False

    # Delegate common attributes to the wrapped Violation
    @property
    def rule_id(self) -> str:
        return self.violation.rule_id

    @property
    def category(self) -> Category:
        return self.violation.category

    @property
    def severity(self):
        return self.violation.severity

    @property
    def file(self) -> str:
        return self.violation.file

    @property
    def line(self) -> int:
        return self.violation.line

    @property
    def col(self) -> int:
        return self.violation.col

    @property
    def message(self) -> str:
        return self.violation.message

    @property
    def suggestion(self) -> str:
        return self.violation.suggestion

    @property
    def fixable(self) -> bool:
        return self.violation.fixable

    def to_dict(self) -> Dict[str, Any]:
        d = self.violation.to_dict()
        d["confidence_level"] = self.confidence_level.value
        d["suppressed"] = self.suppressed
        return d


class AdaptiveScanner:
    """Adaptive security scanner with confidence scoring and learning.

    Wraps SecurityScanner with adaptive features:
    - Confidence levels based on file context
    - Suppression lists for known false positives
    - Pattern learning persistence

    Args:
        learning_dir: Directory for persistent learning data.
        min_confidence: Minimum confidence level to report.
    """

    def __init__(
        self,
        learning_dir: Optional[str] = None,
        min_confidence: Confidence = Confidence.LOW,
    ) -> None:
        self._scanner = SecurityScanner()
        self._learning_dir = Path(learning_dir) if learning_dir else None
        self._min_confidence = min_confidence
        self._suppressions: List[Dict[str, str]] = []
        self._false_positives: List[Dict[str, str]] = []
        self._patterns: Dict[str, int] = {}
        self._stats: Dict[str, int] = {
            "total_scanned": 0,
            "total_violations": 0,
            "total_suppressed": 0,
            "total_false_positives": 0,
        }

        if self._learning_dir:
            self._load()

    def scan_path(self, path: str) -> List[AdaptiveViolation]:
        """Scan a path and return adaptive violations with confidence scores.

        Args:
            path: File or directory path to scan.

        Returns:
            List of AdaptiveViolation objects (suppressed ones excluded).
        """
        raw_violations = self._scanner.scan_path(path)
        self._stats["total_scanned"] += 1
        self._stats["total_violations"] += len(raw_violations)

        results: List[AdaptiveViolation] = []
        for v in raw_violations:
            confidence = self._compute_confidence(v)
            av = AdaptiveViolation(violation=v, confidence_level=confidence)

            # Check suppression
            if self._is_suppressed(v):
                av.suppressed = True
                self._stats["total_suppressed"] += 1
                continue  # Skip suppressed violations

            # Learn pattern
            key = f"{v.rule_id}:{v.file}"
            self._patterns[key] = self._patterns.get(key, 0) + 1

            results.append(av)

        return results

    def suppress(
        self,
        rule_id: str,
        file_pattern: str,
        *,
        line_pattern: str = "",
        reason: str = "",
    ) -> None:
        """Suppress a violation pattern.

        Args:
            rule_id: Rule ID to suppress.
            file_pattern: File path pattern to match.
            line_pattern: Optional line pattern.
            reason: Reason for suppression.
        """
        self._suppressions.append({
            "rule_id": rule_id,
            "file_pattern": file_pattern,
            "line_pattern": line_pattern,
            "reason": reason,
        })

    def mark_false_positive(
        self,
        violation,
        reason: str = "",
    ) -> None:
        """Mark a violation as a false positive (adds suppression).

        Args:
            violation: The violation to mark (Violation or AdaptiveViolation).
            reason: Reason for marking as false positive.
        """
        rule_id = violation.rule_id
        file_path = violation.file
        self._false_positives.append({
            "rule_id": rule_id,
            "file": file_path,
            "reason": reason,
        })
        self.suppress(rule_id, file_path, reason=reason or "false positive")
        self._stats["total_false_positives"] += 1

    def get_stats(self) -> Dict[str, int]:
        """Get scanning statistics."""
        return dict(self._stats)

    def save(self) -> None:
        """Save learning data to disk."""
        if not self._learning_dir:
            return
        self._learning_dir.mkdir(parents=True, exist_ok=True)

        suppress_path = self._learning_dir / "suppress.json"
        suppress_path.write_text(json.dumps(self._suppressions, indent=2))

        patterns_path = self._learning_dir / "patterns.json"
        patterns_path.write_text(json.dumps(self._patterns, indent=2))

    def _compute_confidence(self, v: Violation) -> Confidence:
        """Compute confidence level for a violation based on context."""
        # Test files get lower confidence
        file_path = v.file.lower()
        if "test" in file_path or "tests" in file_path:
            return Confidence.LOW

        # High-severity violations get higher confidence
        if v.severity.value in ("critical", "high"):
            return Confidence.HIGH

        # Known patterns get higher confidence
        key = f"{v.rule_id}:{v.file}"
        if self._patterns.get(key, 0) > 3:
            return Confidence.HIGH

        return Confidence.MEDIUM

    def _is_suppressed(self, v: Violation) -> bool:
        """Check if a violation matches any suppression rule."""
        for s in self._suppressions:
            if s["rule_id"] == v.rule_id and s["file_pattern"] in v.file:
                return True
        return False

    def _load(self) -> None:
        """Load learning data from disk."""
        if not self._learning_dir:
            return

        suppress_path = self._learning_dir / "suppress.json"
        if suppress_path.exists():
            try:
                self._suppressions = json.loads(suppress_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        patterns_path = self._learning_dir / "patterns.json"
        if patterns_path.exists():
            try:
                self._patterns = json.loads(patterns_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

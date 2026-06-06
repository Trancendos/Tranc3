"""
shared_core.security_automation.adaptive_scanner — Adaptive security scanner that learns
from codebase patterns to reduce false positives over time.

The AdaptiveScanner wraps the base SecurityScanner with a learning layer that:
  1. Tracks violation patterns specific to this codebase
  2. Learns which violations are false positives (via suppress file)
  3. Adjusts severity based on historical data (e.g., a CWE-022 in a test
     helper is less severe than in a route handler)
  4. Provides confidence scoring for each violation

Usage:
    from shared_core.security_automation.adaptive_scanner import AdaptiveScanner

    scanner = AdaptiveScanner()
    violations = scanner.scan_path("src/")
    for v in violations:
        print(f"[{v.adaptive_confidence:.0%}] {v}")

Learning workflow:
    1. Run scan → get violations with confidence scores
    2. Review low-confidence violations → mark as false positives
    3. Scanner learns and adjusts future scans
    4. Over time, signal-to-noise ratio improves dramatically
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Tuple

from shared_core.security_automation.scanner import (
    Category,
    SecurityScanner,
    Severity,
    Violation,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_LEARNING_DIR = ".security_learning"
_SUPPRESS_FILE = "suppress.json"
_PATTERN_FILE = "patterns.json"
_HISTORY_FILE = "history.json"


class Confidence(Enum):
    """Adaptive confidence level for a violation."""

    HIGH = "high"  # Almost certainly a real violation (≥0.8)
    MEDIUM = "medium"  # Likely real (0.5–0.8)
    LOW = "low"  # Possibly false positive (0.2–0.5)
    SUPPRESSED = "suppressed"  # Known false positive (<0.2 or explicitly suppressed)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AdaptiveViolation:
    """A security violation enriched with adaptive confidence scoring."""

    base: Violation
    adaptive_confidence: float = 1.0
    confidence_level: Confidence = Confidence.HIGH
    suppression_reason: str = ""
    similar_history_count: int = 0
    false_positive_rate: float = 0.0

    @property
    def rule_id(self) -> str:
        return self.base.rule_id

    @property
    def category(self) -> Category:
        return self.base.category

    @property
    def severity(self) -> Severity:
        return self.base.severity

    @property
    def file(self) -> str:
        return self.base.file

    @property
    def line(self) -> int:
        return self.base.line

    @property
    def message(self) -> str:
        return self.base.message

    def to_dict(self) -> Dict[str, Any]:
        d = self.base.to_dict()
        d["adaptive_confidence"] = round(self.adaptive_confidence, 3)
        d["confidence_level"] = self.confidence_level.value
        d["suppression_reason"] = self.suppression_reason
        d["similar_history_count"] = self.similar_history_count
        d["false_positive_rate"] = round(self.false_positive_rate, 3)
        return d


@dataclass
class SuppressionEntry:
    """A single suppression entry — marks a violation as a known false positive."""

    rule_id: str
    file_pattern: str  # Glob pattern or exact path
    line_pattern: str = ""  # Regex pattern for the line content (empty = any line)
    reason: str = ""
    created_at: str = ""
    created_by: str = "adaptive_scanner"


@dataclass
class PatternObservation:
    """A learned pattern observation about a codebase."""

    rule_id: str
    directory: str
    file_glob: str
    observation_count: int = 0
    false_positive_count: int = 0
    last_seen: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# AdaptiveScanner
# ---------------------------------------------------------------------------


class AdaptiveScanner:
    """Security scanner that learns from codebase patterns to reduce false positives.

    Wraps the base SecurityScanner with adaptive intelligence:

    Layer 1 — Suppression filtering: Known false positives are suppressed based on
    a suppress.json file that can be curated manually or automatically.

    Layer 2 — Pattern learning: The scanner observes which patterns recur in
    specific directories/files and tracks their false-positive rates. When a
    pattern has a high false-positive rate, its confidence is reduced.

    Layer 3 — Context-aware severity: Violations in test directories have
    slightly reduced confidence. Violations in API route handlers or security
    modules have increased confidence.

    Layer 4 — Historical trending: The scanner tracks violation history and
    can detect if a pattern is improving or regressing.
    """

    def __init__(
        self,
        *,
        learning_dir: str = _DEFAULT_LEARNING_DIR,
        auto_learn: bool = True,
        min_confidence: float = 0.1,
    ):
        """Initialize the adaptive scanner.

        Args:
            learning_dir: Directory for storing learned patterns and suppressions.
            auto_learn: If True, automatically update patterns from scan results.
            min_confidence: Minimum confidence to include in results (0.0–1.0).
        """
        self._scanner = SecurityScanner()
        self._learning_dir = learning_dir
        self._auto_learn = auto_learn
        self._min_confidence = min_confidence

        self._suppressions: List[SuppressionEntry] = []
        self._patterns: Dict[str, PatternObservation] = {}
        self._history: List[Dict[str, Any]] = []

        self._load_learning_data()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_path(self, *paths: str) -> List[AdaptiveViolation]:
        """Scan paths and return violations with adaptive confidence scoring.

        Args:
            *paths: File or directory paths to scan.

        Returns:
            List of AdaptiveViolation instances, sorted by confidence (highest first).
        """
        raw_violations = self._scanner.scan_path(*paths)
        adaptive = [self._enrich_violation(v) for v in raw_violations]

        # Filter by minimum confidence
        result = [v for v in adaptive if v.adaptive_confidence >= self._min_confidence]

        # Auto-learn from this scan
        if self._auto_learn:
            self._record_observations(result)

        # Sort: highest confidence first, then by severity
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        result.sort(key=lambda v: (-v.adaptive_confidence, severity_order.get(v.severity, 5)))

        return result

    def scan_file(self, filepath: str) -> List[AdaptiveViolation]:
        """Scan a single file and return adaptive violations."""
        return self.scan_path(filepath)

    def suppress(
        self,
        rule_id: str,
        file_pattern: str,
        *,
        line_pattern: str = "",
        reason: str = "",
    ) -> None:
        """Add a suppression entry for a known false positive.

        Args:
            rule_id: The rule to suppress (e.g., "CWE-022", "PY-008").
            file_pattern: Glob pattern for file paths (e.g., "tests/*").
            line_pattern: Regex for line content (optional).
            reason: Human-readable reason for the suppression.
        """
        entry = SuppressionEntry(
            rule_id=rule_id,
            file_pattern=file_pattern,
            line_pattern=line_pattern,
            reason=reason or "Suppressed by adaptive scanner",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._suppressions.append(entry)
        self._save_suppressions()

    def unsuppress(self, rule_id: str, file_pattern: str) -> bool:
        """Remove a suppression entry.

        Returns:
            True if a matching suppression was found and removed.
        """
        original_len = len(self._suppressions)
        self._suppressions = [
            s
            for s in self._suppressions
            if not (s.rule_id == rule_id and s.file_pattern == file_pattern)
        ]
        if len(self._suppressions) < original_len:
            self._save_suppressions()
            return True
        return False

    def get_suppressions(self) -> List[SuppressionEntry]:
        """Return current suppression entries."""
        return list(self._suppressions)

    def get_patterns(self) -> Dict[str, PatternObservation]:
        """Return learned pattern observations."""
        return dict(self._patterns)

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the adaptive scanner's learning state."""
        total_suppressions = len(self._suppressions)
        total_patterns = len(self._patterns)
        category_fp_rates: Dict[str, float] = {}

        for _key, obs in self._patterns.items():
            rule_id = obs.rule_id
            if rule_id not in category_fp_rates:
                category_fp_rates[rule_id] = 0.0
            if obs.observation_count > 0:
                rate = obs.false_positive_count / obs.observation_count
                category_fp_rates[rule_id] = max(category_fp_rates[rule_id], rate)

        return {
            "total_suppressions": total_suppressions,
            "total_patterns": total_patterns,
            "category_false_positive_rates": category_fp_rates,
            "history_entries": len(self._history),
            "learning_dir": self._learning_dir,
        }

    def save(self) -> None:
        """Persist all learning data to disk."""
        self._save_suppressions()
        self._save_patterns()
        self._save_history()

    # ------------------------------------------------------------------
    # Internal: enrichment logic
    # ------------------------------------------------------------------

    def _enrich_violation(self, v: Violation) -> AdaptiveViolation:
        """Enrich a raw violation with adaptive confidence scoring."""
        confidence = 1.0
        reason = ""

        # Layer 1: Check suppressions
        suppressed, suppress_reason = self._check_suppressions(v)
        if suppressed:
            return AdaptiveViolation(
                base=v,
                adaptive_confidence=0.0,
                confidence_level=Confidence.SUPPRESSED,
                suppression_reason=suppress_reason,
            )

        # Layer 2: Pattern-based confidence adjustment
        pattern_key = self._pattern_key(v)
        if pattern_key in self._patterns:
            obs = self._patterns[pattern_key]
            if obs.observation_count > 0:
                fp_rate = obs.false_positive_count / obs.observation_count
                confidence *= 1.0 - fp_rate * 0.7  # Reduce but don't eliminate
                similar_count = obs.observation_count
            else:
                similar_count = 0
                fp_rate = 0.0
        else:
            similar_count = 0
            fp_rate = 0.0

        # Layer 3: Context-aware adjustments
        context_modifier = self._context_confidence_modifier(v)
        confidence *= context_modifier

        # Layer 4: History-based trending
        history_modifier = self._history_confidence_modifier(v)
        confidence *= history_modifier

        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))

        # Determine confidence level
        if confidence >= 0.8:
            level = Confidence.HIGH
        elif confidence >= 0.5:
            level = Confidence.MEDIUM
        else:
            level = Confidence.LOW

        return AdaptiveViolation(
            base=v,
            adaptive_confidence=confidence,
            confidence_level=level,
            suppression_reason=reason,
            similar_history_count=similar_count,
            false_positive_rate=fp_rate,
        )

    def _check_suppressions(self, v: Violation) -> Tuple[bool, str]:
        """Check if a violation matches any suppression entry."""
        from fnmatch import fnmatch

        for s in self._suppressions:
            if s.rule_id != v.rule_id and s.rule_id != v.category.value:
                continue
            if not fnmatch(v.file, s.file_pattern):
                continue
            if s.line_pattern:
                if not re.search(s.line_pattern, v.message):
                    continue
            return True, s.reason

        return False, ""

    def _context_confidence_modifier(self, v: Violation) -> float:
        """Adjust confidence based on the file's context in the codebase.

        Test files: slightly reduced confidence (test helpers often have
        intentional patterns that trigger rules).

        Security-critical files: increased confidence (violations in security
        modules, API routes, or authentication code are more serious).

        Auto-generated files: reduced confidence.
        """
        filepath = v.file.replace("\\", "/")

        # Test directories — slightly lower confidence
        if any(part in filepath.split("/") for part in ("tests", "test", "__tests__")):
            if v.category in (Category.MIXED_RETURN, Category.BARE_EXCEPT):
                return 0.7  # Test functions often have mixed returns intentionally

        # Security-critical paths — higher confidence
        critical_parts = ("security", "auth", "api", "gateway", "middleware")
        if any(part in filepath.split("/") for part in critical_parts):
            if v.category in (Category.PATH_TRAVERSAL, Category.INFO_EXPOSURE, Category.WEAK_HASH):
                return 1.2  # These violations in security code are more serious

        # Auto-generated files — lower confidence
        if any(
            indicator in filepath for indicator in ("_pb2.py", "_grpc.py", ".venv", "node_modules")
        ):
            return 0.3

        # Scripts directory — mixed confidence
        if "scripts/" in filepath:
            if v.category == Category.BARE_EXCEPT:
                return 0.6  # Scripts often use bare except for robustness

        return 1.0

    def _history_confidence_modifier(self, v: Violation) -> float:
        """Adjust confidence based on historical trending.

        If a violation pattern has been appearing for a long time without
        being fixed, it might be a known-accepted pattern (slight reduction).

        If a violation pattern is new (first time seen), it gets full confidence.
        """
        pattern_key = self._pattern_key(v)
        seen_count = sum(1 for h in self._history if h.get("pattern_key") == pattern_key)

        if seen_count > 20:
            # Long-standing pattern — possibly accepted, slight reduction
            return 0.9
        elif seen_count > 10:
            return 0.95

        return 1.0

    # ------------------------------------------------------------------
    # Internal: learning
    # ------------------------------------------------------------------

    def _pattern_key(self, v: Violation) -> str:
        """Generate a unique key for a violation pattern."""
        directory = str(Path(v.file).parent)
        return f"{v.rule_id}:{directory}"

    def _record_observations(self, violations: List[AdaptiveViolation]) -> None:
        """Record observations from this scan for future learning."""
        self._prev_pattern_keys = set(self._patterns.keys())
        for av in violations:
            key = self._pattern_key(av.base)
            filepath = av.file.replace("\\", "/")
            directory = str(Path(filepath).parent)
            file_glob = f"{directory}/*.py"

            if key not in self._patterns:
                self._patterns[key] = PatternObservation(
                    rule_id=av.rule_id,
                    directory=directory,
                    file_glob=file_glob,
                )

            obs = self._patterns[key]
            obs.observation_count += 1
            obs.last_seen = datetime.now(timezone.utc).isoformat()

            # If suppressed, count as false positive
            if av.confidence_level == Confidence.SUPPRESSED:
                obs.false_positive_count += 1

        # Record scan in history (keep last 100)
        # Build per-rule counts
        per_rule: Dict[str, int] = {}
        for av in violations:
            rid = av.rule_id
            per_rule[rid] = per_rule.get(rid, 0) + 1

        # Build per-entity counts using the rule catalog entity map
        try:
            from shared_core.security_automation.rule_catalog import (
                entity_for_directory as _entity_for_dir,
            )

            per_entity: Dict[str, int] = {}
            for av in violations:
                directory = str(Path(av.file).parent).replace("\\", "/")
                entity = _entity_for_dir(directory)
                per_entity[entity] = per_entity.get(entity, 0) + 1
        except ImportError:
            per_entity = {}

        self._history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "violation_count": len(violations),
                "per_rule_counts": per_rule,
                "per_entity_counts": per_entity,
                "new_since_last": len(
                    [
                        av
                        for av in violations
                        if self._pattern_key(av.base) not in self._prev_pattern_keys
                    ]
                ),
                "suppressed_count": len(
                    [av for av in violations if av.confidence_level == Confidence.SUPPRESSED]
                ),
            }
        )
        if len(self._history) > 100:
            self._history = self._history[-100:]

        self._save_patterns()
        self._save_history()

    def mark_false_positive(self, violation: AdaptiveViolation, reason: str = "") -> None:
        """Mark a violation as a false positive for future learning.

        This both adds a suppression and updates the pattern's false positive count.
        """
        # Add suppression
        self.suppress(
            rule_id=violation.rule_id,
            file_pattern=violation.file,
            reason=reason or "Marked as false positive via adaptive scanner",
        )

        # Update pattern false positive count
        key = self._pattern_key(violation.base)
        if key in self._patterns:
            self._patterns[key].false_positive_count += 1
            self._save_patterns()

    # ------------------------------------------------------------------
    # Internal: persistence
    # ------------------------------------------------------------------

    def _load_learning_data(self) -> None:
        """Load all learning data from disk."""
        self._load_suppressions()
        self._load_patterns()
        self._load_history()

    def _load_suppressions(self) -> None:
        path = Path(self._learning_dir) / _SUPPRESS_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._suppressions = [SuppressionEntry(**entry) for entry in data]
            except (json.JSONDecodeError, TypeError):
                self._suppressions = []

    def _save_suppressions(self) -> None:
        path = Path(self._learning_dir) / _SUPPRESS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "rule_id": s.rule_id,
                "file_pattern": s.file_pattern,
                "line_pattern": s.line_pattern,
                "reason": s.reason,
                "created_at": s.created_at,
                "created_by": s.created_by,
            }
            for s in self._suppressions
        ]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _load_patterns(self) -> None:
        path = Path(self._learning_dir) / _PATTERN_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._patterns = {}
                for key, entry in data.items():
                    self._patterns[key] = PatternObservation(**entry)
            except (json.JSONDecodeError, TypeError):
                self._patterns = {}

    def _save_patterns(self) -> None:
        path = Path(self._learning_dir) / _PATTERN_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for _key, obs in self._patterns.items():
            data[_key] = {
                "rule_id": obs.rule_id,
                "directory": obs.directory,
                "file_glob": obs.file_glob,
                "observation_count": obs.observation_count,
                "false_positive_count": obs.false_positive_count,
                "last_seen": obs.last_seen,
                "notes": obs.notes,
            }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _load_history(self) -> None:
        path = Path(self._learning_dir) / _HISTORY_FILE
        if path.exists():
            try:
                self._history = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, TypeError):
                self._history = []

    def _save_history(self) -> None:
        path = Path(self._learning_dir) / _HISTORY_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

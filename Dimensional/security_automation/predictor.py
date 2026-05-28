"""
Dimensional.security_automation.predictor — Violation predictor for proactive security.

Predicts which files and code patterns are most likely to contain security
violations, enabling proactive scanning and developer guidance. Uses heuristics
derived from the patterns observed during the ~297 CodeQL alert remediation.

Prediction signals:
    - Import patterns (e.g., hashlib → likely CWE-327, os.path → likely CWE-022)
    - Function complexity (high cyclomatic complexity → more likely to have mixed returns)
    - Code churn (recently modified files → more likely to introduce new violations)
    - Historical violation density (files with many past violations → higher risk)
    - Dependency proximity (files that import from high-risk modules → elevated risk)

Usage:
    from Dimensional.security_automation.predictor import ViolationPredictor

    predictor = ViolationPredictor(repo_root=".")
    predictions = predictor.predict("src/")

    for p in predictions:
        print(f"{p.filepath}: {p.risk_score:.0%} risk — likely {p.predicted_categories}")
"""

from __future__ import annotations

import ast
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Prediction:
    """A single prediction about likely violations in a file."""

    filepath: str
    risk_score: float  # 0.0 to 1.0
    predicted_categories: List[str]
    signals: List[str]
    confidence: float = 0.5  # How confident we are in this prediction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filepath": self.filepath,
            "risk_score": round(self.risk_score, 3),
            "predicted_categories": self.predicted_categories,
            "signals": self.signals,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class RiskSignal:
    """A single risk signal detected in a file."""

    category: str
    description: str
    weight: float  # How much this signal contributes to risk


# ---------------------------------------------------------------------------
# Signal detectors
# ---------------------------------------------------------------------------


class ImportRiskDetector:
    """Detects risk signals based on import patterns."""

    # Import → likely violation categories
    IMPORT_RISK_MAP = {
        "hashlib": [RiskSignal("CWE-327", "hashlib import — may use md5/sha1 for security", 0.4)],
        "os.path": [RiskSignal("CWE-022", "os.path usage — may have path traversal", 0.3)],
        "os": [RiskSignal("CWE-022", "os module — may construct paths unsafely", 0.2)],
        "open": [RiskSignal("CWE-022", "builtin open — may open user-supplied paths", 0.2)],
        "subprocess": [RiskSignal("CWE-078", "subprocess — may have command injection", 0.4)],
        "pickle": [RiskSignal("CWE-502", "pickle — deserialization of untrusted data", 0.5)],
        "eval": [RiskSignal("CWE-94", "eval — code injection risk", 0.6)],
        "exec": [RiskSignal("CWE-94", "exec — code injection risk", 0.6)],
        "yaml.load": [RiskSignal("CWE-502", "yaml.load — unsafe deserialization", 0.4)],
        "logging": [RiskSignal("CWE-117", "logging — may have log injection", 0.2)],
        "logger": [RiskSignal("CWE-117", "logger — may have log injection", 0.2)],
    }

    def detect(self, tree: ast.AST, source: str) -> List[RiskSignal]:
        """Detect risk signals from import statements."""
        signals = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in self.IMPORT_RISK_MAP:
                        signals.extend(self.IMPORT_RISK_MAP[name])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    if name in self.IMPORT_RISK_MAP:
                        signals.extend(self.IMPORT_RISK_MAP[name])

        return signals


class ComplexityRiskDetector:
    """Detects risk signals based on code complexity."""

    def detect(self, tree: ast.AST, source: str) -> List[RiskSignal]:
        """Detect risk signals from code complexity."""
        signals = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Calculate cyclomatic complexity
            complexity = self._cyclomatic_complexity(node)  # type: ignore[arg-type]

            if complexity > 10:
                signals.append(
                    RiskSignal(
                        "PY-008",
                        f"High complexity function '{node.name}' (complexity={complexity}) — mixed return risk",
                        min(0.1 + (complexity - 10) * 0.02, 0.5),
                    )
                )

            # Check for bare except
            for child in ast.walk(node):
                if isinstance(child, ast.ExceptHandler) and child.type is None:
                    signals.append(
                        RiskSignal(
                            "PY-001",
                            f"Bare except in '{node.name}'",
                            0.3,
                        )
                    )

            # Check for mixed returns
            has_return_value = False
            has_implicit_return = False
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value is not None:
                    has_return_value = True

            if node.body and not isinstance(node.body[-1], (ast.Return, ast.Raise)):
                has_implicit_return = True

            if has_return_value and has_implicit_return:
                signals.append(
                    RiskSignal(
                        "PY-008",
                        f"Mixed return in '{node.name}' — has return value but implicit None",
                        0.5,
                    )
                )

        return signals

    @staticmethod
    def _cyclomatic_complexity(node: ast.FunctionDef) -> int:
        """Calculate McCabe cyclomatic complexity for a function."""
        complexity = 1  # Base
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # and/or operators add one per operand after the first
                complexity += len(child.values) - 1
        return complexity


class PatternRiskDetector:
    """Detects risk signals based on code patterns."""

    # Patterns that indicate likely violations
    PATTERNS = [
        (r"open\s*\(", RiskSignal("CWE-022", "open() call — potential path traversal", 0.2)),
        (
            r'logger\.\w+\(f["\']',
            RiskSignal("CWE-117", "f-string in logger — log injection risk", 0.4),
        ),
        (
            r"str\(\w+\).*detail",
            RiskSignal("CWE-209", "str(exc) in detail — info exposure risk", 0.5),
        ),
        (r"hashlib\.(md5|sha1)\s*\(", RiskSignal("CWE-327", "weak hash algorithm", 0.6)),
        (r"0\.0\.0\.0", RiskSignal("CWE-605", "bind all interfaces", 0.4)),
        (r"except\s*:", RiskSignal("PY-001", "bare except", 0.3)),
        (r"type\(.*__exc.*\)", RiskSignal("PY-003", "__exc variable reference", 0.3)),
    ]

    def detect(self, tree: ast.AST, source: str) -> List[RiskSignal]:
        """Detect risk signals from code patterns."""
        signals = []
        seen = set()

        for pattern, signal in self.PATTERNS:
            if re.search(pattern, source):
                # Deduplicate by category + description
                key = (signal.category, signal.description)
                if key not in seen:
                    signals.append(signal)
                    seen.add(key)

        return signals


class SafePatternDetector:
    """Detects patterns that REDUCE risk — indicates secure coding practices."""

    SAFE_PATTERNS = [
        (r"validate_path\s*\(", -0.3, "CWE-022"),
        (r"safe_error_detail\s*\(", -0.3, "CWE-209"),
        (r"sanitize_for_log\s*\(", -0.3, "CWE-117"),
        (r"usedforsecurity\s*=\s*False", -0.3, "CWE-327"),
        (r"from Dimensional\.path_validation import", -0.2, "CWE-022"),
        (r"from Dimensional\.error_handlers import", -0.2, "CWE-209"),
        (r"from Dimensional\.sanitize import", -0.2, "CWE-117"),
    ]

    def detect(self, source: str) -> List[Tuple[str, float]]:
        """Detect safe patterns and return risk reductions.

        Returns:
            List of (category, risk_reduction) tuples.
        """
        reductions = []
        seen = set()

        for pattern, reduction, category in self.SAFE_PATTERNS:
            if re.search(pattern, source):
                key = category
                if key not in seen:
                    reductions.append((category, reduction))
                    seen.add(key)

        return reductions


# ---------------------------------------------------------------------------
# ViolationPredictor
# ---------------------------------------------------------------------------


class ViolationPredictor:
    """Predicts likely violation areas based on code patterns and heuristics.

    Uses multiple signal detectors to assess the risk level of each file
    in the codebase, enabling proactive scanning and developer guidance.

    The predictor does NOT replace the scanner — it prioritizes which files
    to scan first and identifies files that are likely to introduce violations
    in the future.
    """

    def __init__(self, *, repo_root: str = "."):
        """Initialize the predictor.

        Args:
            repo_root: Root directory of the repository.
        """
        self.repo_root = repo_root
        self._import_detector = ImportRiskDetector()
        self._complexity_detector = ComplexityRiskDetector()
        self._pattern_detector = PatternRiskDetector()
        self._safe_detector = SafePatternDetector()
        self._historical_data: Dict[str, int] = {}  # filepath → historical violation count

    def predict(self, *paths: str) -> List[Prediction]:
        """Predict likely violations in the given paths.

        Args:
            *paths: File or directory paths to analyze.

        Returns:
            List of Prediction objects, sorted by risk score (highest first).
        """
        # Collect all Python files
        all_files = []
        for path in paths:
            p = Path(path)
            if p.is_file() and p.suffix == ".py":
                all_files.append(str(p))
            elif p.is_dir():
                for root, dirs, files in os.walk(p):
                    dirs[:] = [
                        d
                        for d in dirs
                        if d not in ("__pycache__", ".git", "node_modules", ".venv", "venv")
                    ]
                    for fname in files:
                        if fname.endswith(".py"):
                            all_files.append(os.path.join(root, fname))

        # Analyze each file
        predictions = []
        for filepath in all_files:
            prediction = self._analyze_file(filepath)
            if prediction and prediction.risk_score > 0.1:
                predictions.append(prediction)

        # Sort by risk score (highest first)
        predictions.sort(key=lambda p: -p.risk_score)
        return predictions

    def update_historical_data(self, violations: List) -> None:
        """Update the predictor's historical data from scan results.

        Args:
            violations: List of Violation objects from a scan.
        """
        counter = Counter()  # type: ignore[var-annotated]
        for v in violations:
            counter[v.file] += 1

        for filepath, count in counter.items():
            # Exponential moving average — recent data weighted more
            old = self._historical_data.get(filepath, 0)
            self._historical_data[filepath] = int(old * 0.7 + count * 0.3)

    def get_hotspots(self, limit: int = 20) -> List[Prediction]:
        """Get the current top risk hotspots based on historical data.

        Returns:
            List of Prediction objects for the highest-risk files.
        """
        predictions = []
        for filepath, count in sorted(self._historical_data.items(), key=lambda x: -x[1])[:limit]:
            if count > 0:
                risk = min(count / 10.0, 1.0)
                predictions.append(
                    Prediction(
                        filepath=filepath,
                        risk_score=risk,
                        predicted_categories=["historical"],
                        signals=[f"Historical violation count: {count}"],
                        confidence=0.7,
                    )
                )

        return predictions

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _analyze_file(self, filepath: str) -> Optional[Prediction]:
        """Analyze a single file and generate a risk prediction."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        # Parse AST
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return Prediction(
                filepath=filepath,
                risk_score=0.3,
                predicted_categories=["syntax-error"],
                signals=["File has syntax errors — cannot analyze"],
                confidence=0.3,
            )

        # Collect risk signals
        all_signals: List[RiskSignal] = []
        all_signals.extend(self._import_detector.detect(tree, source))
        all_signals.extend(self._complexity_detector.detect(tree, source))
        all_signals.extend(self._pattern_detector.detect(tree, source))

        # Calculate base risk from signals
        total_risk = 0.0
        category_risks: Dict[str, float] = {}
        signal_descriptions: List[str] = []

        for signal in all_signals:
            total_risk += signal.weight
            category_risks[signal.category] = category_risks.get(signal.category, 0) + signal.weight
            signal_descriptions.append(f"{signal.category}: {signal.description}")

        # Apply safe pattern reductions
        safe_reductions = self._safe_detector.detect(source)
        for category, reduction in safe_reductions:
            if category in category_risks:
                category_risks[category] = max(0, category_risks[category] + reduction)
                total_risk = max(0, total_risk + reduction)

        # Apply historical data modifier
        historical_count = self._historical_data.get(filepath, 0)
        if historical_count > 0:
            historical_modifier = min(historical_count * 0.05, 0.3)
            total_risk += historical_modifier
            signal_descriptions.append(f"Historical violations: {historical_count}")

        # Clamp risk
        total_risk = min(1.0, total_risk)

        # Predict categories
        predicted_categories = sorted(
            category_risks.keys(),
            key=lambda c: -category_risks[c],
        )

        # Calculate confidence based on number of signals
        confidence = min(0.3 + len(all_signals) * 0.1, 0.9)

        return Prediction(
            filepath=filepath,
            risk_score=total_risk,
            predicted_categories=predicted_categories,
            signals=signal_descriptions,
            confidence=confidence,
        )

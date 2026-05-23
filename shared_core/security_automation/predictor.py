"""
shared_core.security_automation.predictor — Predictive violation risk analysis.

Analyzes source code for risk signals that predict where security violations
are likely to occur. Uses import analysis, complexity metrics, and pattern
recognition to prioritize scanning and remediation efforts.

Zero-cost: All analysis is local, no external APIs required.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class RiskPrediction:
    """A risk prediction for a source file."""

    file: str
    risk_score: float
    signals: List[str] = field(default_factory=list)
    category: str = "unknown"

    def to_dict(self) -> Dict[str, object]:
        return {
            "file": self.file,
            "risk_score": self.risk_score,
            "signals": self.signals,
            "category": self.category,
        }


# Known risky imports and their associated CWE signals
_RISKY_IMPORTS: Dict[str, List[str]] = {
    "hashlib": ["CWE-327:weak-hash"],
    "os": ["CWE-022:path-traversal"],
    "subprocess": ["CWE-078:command-injection"],
    "pickle": ["CWE-502:deserialization"],
    "eval": ["CWE-95:code-injection"],
    "exec": ["CWE-95:code-injection"],
    "xml.etree.ElementTree": ["CWE-611:xxe"],
    "yaml": ["CWE-502:deserialization"],
}

# Patterns that indicate safe handling
_SAFE_PATTERNS: List[str] = [
    "validate_path",
    "sanitize",
    "sanitize_for_log",
    "safe_error_detail",
    "path_validation",
]


class ViolationPredictor:
    """Predictive violation risk analyzer.

    Scans source files for risk signals (risky imports, complexity,
    unsafe patterns) and produces risk scores to prioritize security
    scanning and remediation.

    Usage:
        predictor = ViolationPredictor()
        predictions = predictor.predict("src/")
        for p in predictions:
            if p.risk_score > 0.7:
                print(f"HIGH RISK: {p.file} — signals: {p.signals}")
    """

    def __init__(self) -> None:
        self._predictions: List[RiskPrediction] = []
        self._hotspots: List[RiskPrediction] = []

    def predict(self, path: str) -> List[RiskPrediction]:
        """Analyze a path and return risk predictions for each file.

        Args:
            path: File or directory path to analyze.

        Returns:
            List of RiskPrediction objects sorted by risk_score descending.
        """
        self._predictions = []
        p = Path(path)

        if p.is_file():
            self._analyze_file(p)
        elif p.is_dir():
            for py_file in p.rglob("*.py"):
                self._analyze_file(py_file)

        # Sort by risk score descending
        self._predictions.sort(key=lambda x: x.risk_score, reverse=True)
        self._hotspots = [p for p in self._predictions if p.risk_score >= 0.5]
        return self._predictions

    def _analyze_file(self, filepath: Path) -> None:
        """Analyze a single file for risk signals."""
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            return

        signals: List[str] = []
        risk_score = 0.0

        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _RISKY_IMPORTS:
                        signals.extend(_RISKY_IMPORTS[alias.name])
                        risk_score += 0.2
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module in _RISKY_IMPORTS:
                    signals.extend(_RISKY_IMPORTS[node.module])
                    risk_score += 0.2

        # Check for safe patterns (reduces risk)
        source_lower = source.lower()
        safe_count = sum(1 for pattern in _SAFE_PATTERNS if pattern in source_lower)
        if safe_count > 0:
            risk_score = max(0.0, risk_score - safe_count * 0.15)
            signals.append(f"safe-pattern:{safe_count}")

        # Check complexity (high cyclomatic complexity = higher risk)
        function_count = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        if function_count > 10:
            signals.append(f"high-complexity:{function_count}")
            risk_score += 0.1

        # Check for known dangerous patterns
        dangerous_patterns = [
            (r"hashlib\.md5\(", "CWE-327:md5-usage"),
            (r"hashlib\.sha1\(", "CWE-327:sha1-usage"),
            (r"os\.system\(", "CWE-078:os-system"),
            (r"eval\(", "CWE-95:eval-usage"),
            (r"pickle\.loads\(", "CWE-502:pickle-loads"),
        ]
        for pattern, signal in dangerous_patterns:
            if re.search(pattern, source):
                signals.append(signal)
                risk_score += 0.3

        # Clamp risk score
        risk_score = min(1.0, max(0.0, risk_score))

        if signals:
            self._predictions.append(RiskPrediction(
                file=str(filepath),
                risk_score=risk_score,
                signals=signals,
                category="prediction",
            ))

    def get_hotspots(self, limit: int = 10) -> List[RiskPrediction]:
        """Return the top N high-risk predictions.

        Args:
            limit: Maximum number of hotspots to return.

        Returns:
            List of RiskPrediction objects with risk_score >= 0.5.
        """
        return self._hotspots[:limit]

# src/coding/self_adaptive.py
# TRANC3 Self-Adaptive Coding System
# Monitors its own code quality, detects regressions, applies targeted fixes

import ast
import re
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CodeQualityMetric:
    """Snapshot of code quality at a point in time."""

    timestamp: float
    complexity: int
    lines_of_code: int
    function_count: int
    class_count: int
    docstring_coverage: float  # fraction of fns with docstrings
    type_hint_coverage: float  # fraction of fns with type hints
    error_handling_score: float
    overall_score: float

    @classmethod
    def from_code(cls, code: str) -> "CodeQualityMetric":
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return cls(
                timestamp=time.time(),
                complexity=0,
                lines_of_code=len(code.splitlines()),
                function_count=0,
                class_count=0,
                docstring_coverage=0.0,
                type_hint_coverage=0.0,
                error_handling_score=0.0,
                overall_score=0.0,
            )

        functions = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        try_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]

        fn_count = len(functions)
        cls_count = len(classes)
        loc = len(code.splitlines())

        # Docstring coverage
        doc_count = sum(1 for fn in functions if ast.get_docstring(fn))
        doc_cov = doc_count / fn_count if fn_count > 0 else 1.0

        # Type hint coverage
        hint_count = sum(
            1
            for fn in functions
            if fn.returns is not None
            or any(a.annotation is not None for a in fn.args.args)
        )
        hint_cov = hint_count / fn_count if fn_count > 0 else 1.0

        # Error handling score
        eh_score = min(1.0, len(try_nodes) / max(fn_count, 1) * 2)

        # Cyclomatic complexity estimate
        branches = sum(
            1
            for n in ast.walk(tree)
            if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With))
        )
        complexity = branches + 1

        # Overall score (weighted)
        overall = (
            doc_cov * 0.25
            + hint_cov * 0.25
            + eh_score * 0.15
            + max(0.0, 1.0 - complexity / 50) * 0.20
            + max(0.0, 1.0 - loc / 500) * 0.15
        )

        return cls(
            timestamp=time.time(),
            complexity=complexity,
            lines_of_code=loc,
            function_count=fn_count,
            class_count=cls_count,
            docstring_coverage=doc_cov,
            type_hint_coverage=hint_cov,
            error_handling_score=eh_score,
            overall_score=round(overall, 4),
        )


class RegressionDetector:
    """Detects quality regressions by comparing snapshots over time."""

    def __init__(self, threshold: float = 0.05):
        self.threshold = threshold
        self._history: List[CodeQualityMetric] = []

    def record(self, metric: CodeQualityMetric):
        self._history.append(metric)
        if len(self._history) > 50:
            self._history.pop(0)

    def detect_regression(self) -> Optional[Dict]:
        if len(self._history) < 2:
            return None
        current = self._history[-1]
        baseline = self._history[-2]
        delta = current.overall_score - baseline.overall_score
        if delta < -self.threshold:
            return {
                "regression_detected": True,
                "delta": round(delta, 4),
                "current_score": current.overall_score,
                "baseline_score": baseline.overall_score,
                "likely_causes": self._find_causes(baseline, current),
            }
        return None

    def _find_causes(
        self, baseline: CodeQualityMetric, current: CodeQualityMetric
    ) -> List[str]:
        causes = []
        if current.docstring_coverage < baseline.docstring_coverage - 0.1:
            causes.append("docstring_coverage_dropped")
        if current.type_hint_coverage < baseline.type_hint_coverage - 0.1:
            causes.append("type_hints_removed")
        if current.complexity > baseline.complexity * 1.3:
            causes.append("complexity_increased")
        if current.error_handling_score < baseline.error_handling_score - 0.15:
            causes.append("error_handling_removed")
        return causes or ["unknown_quality_drop"]


class AdaptiveCodingEngine:
    """
    Self-monitoring coding engine that watches code quality and
    applies targeted improvements when regressions are detected.
    """

    def __init__(self):
        self.detector = RegressionDetector()
        self._monitored_modules: Dict[str, str] = {}  # name → code
        self._fix_history: List[Dict] = []

    def monitor_module(self, name: str, code: str):
        """Register a module for quality monitoring."""
        self._monitored_modules[name] = code
        metric = CodeQualityMetric.from_code(code)
        self.detector.record(metric)
        logger.debug("Monitoring module '%s' — score: %.2f", name, metric.overall_score)

    async def sweep(self) -> List[Dict]:
        """Check all monitored modules for regressions."""
        results = []
        for name, code in self._monitored_modules.items():
            metric = CodeQualityMetric.from_code(code)
            self.detector.record(metric)
            regression = self.detector.detect_regression()
            if regression:
                fix = await self._apply_targeted_fix(name, code, regression)
                results.append({"module": name, "regression": regression, "fix": fix})
        return results

    async def _apply_targeted_fix(self, name: str, code: str, regression: Dict) -> Dict:
        """Apply targeted fix based on regression causes."""
        causes = regression.get("likely_causes", [])
        fixes_applied = []
        improved_code = code

        if "docstring_coverage_dropped" in causes:
            improved_code = self._inject_missing_docstrings(improved_code)
            fixes_applied.append("injected_docstrings")

        if "type_hints_removed" in causes:
            improved_code = self._add_basic_type_hints(improved_code)
            fixes_applied.append("added_type_hints")

        if fixes_applied:
            self._monitored_modules[name] = improved_code
            self._fix_history.append(
                {
                    "module": name,
                    "timestamp": time.time(),
                    "fixes": fixes_applied,
                    "delta_before": regression["delta"],
                }
            )

        return {"fixes_applied": fixes_applied, "improved": bool(fixes_applied)}

    def _inject_missing_docstrings(self, code: str) -> str:
        """Add minimal docstrings to functions that lack them."""
        lines = code.splitlines()
        output = []
        i = 0
        while i < len(lines):
            line = lines[i]
            output.append(line)
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                # Check if next non-empty line is a docstring
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if (
                    j < len(lines)
                    and not lines[j].strip().startswith('"""')
                    and not lines[j].strip().startswith("'''")
                ):
                    indent = len(line) - len(line.lstrip()) + 4
                    fn_name = re.search(r"def (\w+)", stripped)
                    name_str = fn_name.group(1) if fn_name else "function"
                    output.append(" " * indent + f'"""Execute {name_str}."""')
            i += 1
        return "\n".join(output)

    def _add_basic_type_hints(self, code: str) -> str:
        """Add -> None to functions that have no return annotation."""
        return re.sub(
            r"(def \w+\([^)]*\))(\s*:)",
            lambda m: m.group(1) + " -> None" + m.group(2)
            if "->" not in m.group(0)
            else m.group(0),
            code,
        )

    def get_stats(self) -> Dict:
        return {
            "monitored_modules": len(self._monitored_modules),
            "fix_history_count": len(self._fix_history),
            "recent_fixes": self._fix_history[-5:],
        }


# Singleton
adaptive_coder = AdaptiveCodingEngine()

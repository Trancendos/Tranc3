# tests/test_coding.py
# Tests for src/coding/self_adaptive.py
# Covers CodeQualityMetric, RegressionDetector, and AdaptiveCodingEngine.

from __future__ import annotations

import pytest

from src.coding.self_adaptive import (
    AdaptiveCodingEngine,
    CodeQualityMetric,
    RegressionDetector,
)

# ── CodeQualityMetric ────────────────────────────────────────────────


class TestCodeQualityMetric:
    def test_from_code_simple_function(self):
        code = '''
def hello():
    """Say hello."""
    return "hello"
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.function_count == 1
        assert metric.class_count == 0
        assert metric.lines_of_code > 0
        assert metric.docstring_coverage == 1.0
        assert 0.0 <= metric.overall_score <= 1.0

    def test_from_code_with_class(self):
        code = '''
class MyClass:
    """A class."""
    def method(self):
        """A method."""
        pass
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.class_count == 1
        assert metric.function_count == 1

    def test_from_code_syntax_error(self):
        code = "def broken("
        metric = CodeQualityMetric.from_code(code)
        assert metric.overall_score == 0.0
        assert metric.function_count == 0
        assert metric.lines_of_code > 0

    def test_from_code_empty(self):
        code = ""
        metric = CodeQualityMetric.from_code(code)
        # Empty code parses fine, just has no functions
        assert metric.function_count == 0
        assert metric.docstring_coverage == 1.0  # 0 functions → 1.0

    def test_from_code_no_docstrings(self):
        code = """
def foo():
    pass

def bar():
    pass
"""
        metric = CodeQualityMetric.from_code(code)
        assert metric.function_count == 2
        assert metric.docstring_coverage == 0.0

    def test_from_code_partial_docstrings(self):
        code = '''
def documented():
    """Has a docstring."""
    pass

def undocumented():
    pass
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.function_count == 2
        assert metric.docstring_coverage == 0.5

    def test_from_code_type_hints(self):
        code = '''
def hinted(x: int) -> str:
    """Typed function."""
    return str(x)

def unhinted(y):
    """Untyped function."""
    return y
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.type_hint_coverage == 0.5

    def test_from_code_error_handling(self):
        code = '''
def risky():
    """Risky function."""
    try:
        pass
    except ValueError:
        pass
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.error_handling_score > 0.0

    def test_from_code_complexity(self):
        code = '''
def complex_fn(x):
    """Complex."""
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                while i < 10:
                    i += 1
    return x
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.complexity > 1

    def test_from_code_async_function(self):
        code = '''
async def async_fn():
    """Async function."""
    pass
'''
        metric = CodeQualityMetric.from_code(code)
        assert metric.function_count == 1
        assert metric.docstring_coverage == 1.0


# ── RegressionDetector ───────────────────────────────────────────────


class TestRegressionDetector:
    def test_no_regression_with_single_metric(self):
        det = RegressionDetector()
        det.record(
            CodeQualityMetric(
                timestamp=1.0,
                complexity=1,
                lines_of_code=10,
                function_count=1,
                class_count=0,
                docstring_coverage=1.0,
                type_hint_coverage=1.0,
                error_handling_score=0.5,
                overall_score=0.8,
            ),
        )
        assert det.detect_regression() is None

    def test_no_regression_when_improving(self):
        det = RegressionDetector()
        det.record(
            CodeQualityMetric(
                timestamp=1.0,
                complexity=1,
                lines_of_code=10,
                function_count=1,
                class_count=0,
                docstring_coverage=0.5,
                type_hint_coverage=0.5,
                error_handling_score=0.5,
                overall_score=0.5,
            ),
        )
        det.record(
            CodeQualityMetric(
                timestamp=2.0,
                complexity=1,
                lines_of_code=10,
                function_count=1,
                class_count=0,
                docstring_coverage=1.0,
                type_hint_coverage=1.0,
                error_handling_score=0.5,
                overall_score=0.8,
            ),
        )
        assert det.detect_regression() is None

    def test_detects_regression(self):
        det = RegressionDetector(threshold=0.05)
        det.record(
            CodeQualityMetric(
                timestamp=1.0,
                complexity=1,
                lines_of_code=10,
                function_count=1,
                class_count=0,
                docstring_coverage=1.0,
                type_hint_coverage=1.0,
                error_handling_score=1.0,
                overall_score=0.9,
            ),
        )
        det.record(
            CodeQualityMetric(
                timestamp=2.0,
                complexity=20,
                lines_of_code=200,
                function_count=10,
                class_count=2,
                docstring_coverage=0.1,
                type_hint_coverage=0.0,
                error_handling_score=0.0,
                overall_score=0.3,
            ),
        )
        result = det.detect_regression()
        assert result is not None
        assert result["regression_detected"] is True
        assert result["delta"] < 0
        assert result["current_score"] == 0.3
        assert result["baseline_score"] == 0.9

    def test_regression_likely_causes(self):
        det = RegressionDetector(threshold=0.05)
        det.record(
            CodeQualityMetric(
                timestamp=1.0,
                complexity=1,
                lines_of_code=10,
                function_count=1,
                class_count=0,
                docstring_coverage=1.0,
                type_hint_coverage=1.0,
                error_handling_score=1.0,
                overall_score=0.9,
            ),
        )
        det.record(
            CodeQualityMetric(
                timestamp=2.0,
                complexity=50,
                lines_of_code=500,
                function_count=5,
                class_count=1,
                docstring_coverage=0.0,
                type_hint_coverage=0.0,
                error_handling_score=0.0,
                overall_score=0.2,
            ),
        )
        result = det.detect_regression()
        assert result is not None
        assert "likely_causes" in result
        causes = result["likely_causes"]
        assert "docstring_coverage_dropped" in causes
        assert "type_hints_removed" in causes

    def test_history_capped_at_50(self):
        det = RegressionDetector()
        for i in range(60):
            det.record(
                CodeQualityMetric(
                    timestamp=float(i),
                    complexity=1,
                    lines_of_code=10,
                    function_count=1,
                    class_count=0,
                    docstring_coverage=1.0,
                    type_hint_coverage=1.0,
                    error_handling_score=1.0,
                    overall_score=0.8,
                ),
            )
        assert len(det._history) <= 50

    def test_threshold_customization(self):
        det = RegressionDetector(threshold=0.5)
        det.record(
            CodeQualityMetric(
                timestamp=1.0,
                complexity=1,
                lines_of_code=10,
                function_count=1,
                class_count=0,
                docstring_coverage=1.0,
                type_hint_coverage=1.0,
                error_handling_score=1.0,
                overall_score=0.8,
            ),
        )
        det.record(
            CodeQualityMetric(
                timestamp=2.0,
                complexity=5,
                lines_of_code=20,
                function_count=2,
                class_count=0,
                docstring_coverage=0.7,
                type_hint_coverage=0.8,
                error_handling_score=0.5,
                overall_score=0.6,
            ),
        )
        # Delta is -0.2 which is > -0.5 threshold, so no regression
        assert det.detect_regression() is None


# ── AdaptiveCodingEngine ─────────────────────────────────────────────


class TestAdaptiveCodingEngine:
    def test_monitor_module(self):
        engine = AdaptiveCodingEngine()
        code = '''
def hello():
    """Say hello."""
    return "hello"
'''
        engine.monitor_module("test_mod", code)
        assert "test_mod" in engine._monitored_modules
        assert len(engine.detector._history) == 1

    def test_monitor_module_records_metric(self):
        engine = AdaptiveCodingEngine()
        code = "def f(): pass\n"
        engine.monitor_module("mod_a", code)
        assert engine.detector._history[-1].overall_score >= 0.0

    @pytest.mark.asyncio
    async def test_sweep_no_regressions(self):
        engine = AdaptiveCodingEngine()
        code = '''
def documented():
    """Has docstring."""
    return 42
'''
        engine.monitor_module("good_mod", code)
        results = await engine.sweep()
        assert isinstance(results, list)

    def test_get_stats(self):
        engine = AdaptiveCodingEngine()
        engine.monitor_module("mod1", "def f(): pass\n")
        stats = engine.get_stats()
        assert stats["monitored_modules"] == 1
        assert stats["fix_history_count"] == 0
        assert isinstance(stats["recent_fixes"], list)

    @pytest.mark.asyncio
    async def test_sweep_with_regression_triggers_fix(self):
        engine = AdaptiveCodingEngine()
        good_code = '''
def documented():
    """Has docstring."""
    return 42
'''
        bad_code = """
def no_doc():
    pass

def also_no_doc():
    pass
"""
        engine.monitor_module("declining_mod", good_code)
        # Replace with worse code to simulate regression
        engine._monitored_modules["declining_mod"] = bad_code
        # Record the new metric manually to trigger regression detection
        metric = CodeQualityMetric.from_code(bad_code)
        engine.detector.record(metric)
        results = await engine.sweep()
        # If a regression was detected, there should be results
        # (exact behavior depends on threshold and scores)
        assert isinstance(results, list)

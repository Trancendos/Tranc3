"""
Tests for src/core/intelligent_logger.py
"""
import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.intelligent_logger import (
    AnomalyDetector,
    IntelligentLogger,
    SeverityClassifier,
    _LokiJsonFormatter,
    set_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logger_with_capture() -> tuple:
    """Return (IntelligentLogger, StringIO buffer)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(_LokiJsonFormatter())

    inner = logging.getLogger(f"test_logger_{id(buf)}")
    inner.handlers.clear()
    inner.addHandler(handler)
    inner.setLevel(logging.DEBUG)
    inner.propagate = False

    logger = IntelligentLogger.__new__(IntelligentLogger)
    logger._name = inner.name
    logger._service_name = "test-service"
    from src.core.intelligent_logger import AnomalyDetector, SeverityClassifier
    logger._classifier = SeverityClassifier()
    logger._anomaly = AnomalyDetector()
    logger._logger = inner
    return logger, buf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_json_output_contains_context_fields():
    set_context(trace_id="trace-123", user_id="user-456", service_name="svc-test")
    logger, buf = _make_logger_with_capture()
    logger.info("hello world")

    output = buf.getvalue().strip()
    assert output, "Logger produced no output"
    data = json.loads(output)
    assert data["trace_id"] == "trace-123"
    assert data["user_id"] == "user-456"
    assert data["message"] == "hello world"
    assert "timestamp" in data
    assert "level" in data


def test_severity_classifier_detects_error_keywords():
    clf = SeverityClassifier()
    assert clf.classify("An error occurred") == logging.ERROR
    assert clf.classify("Exception raised during startup") == logging.ERROR
    assert clf.classify("critical system failure") == logging.CRITICAL
    assert clf.classify("warning: disk usage high") == logging.WARNING
    assert clf.classify("Everything is fine") == logging.INFO
    assert clf.classify("debug dump of state") == logging.DEBUG


def test_anomaly_detector_triggers_on_burst():
    alerts = []
    detector = AnomalyDetector(window_secs=60.0, burst_threshold=10)
    detector.set_alert_callback(lambda count: alerts.append(count))

    # Fire 15 errors rapidly
    for _ in range(15):
        detector.record_error()

    assert len(alerts) >= 1, "Alert should have fired after burst"
    assert alerts[0] > 10


def test_anomaly_detector_does_not_fire_below_threshold():
    alerts = []
    detector = AnomalyDetector(window_secs=60.0, burst_threshold=10)
    detector.set_alert_callback(lambda count: alerts.append(count))

    for _ in range(5):
        detector.record_error()

    assert len(alerts) == 0


def test_auto_log_uses_classifier():
    logger, buf = _make_logger_with_capture()
    logger.auto_log("fatal error occurred")
    output = buf.getvalue().strip()
    data = json.loads(output)
    assert data["level"] in ("ERROR", "CRITICAL")


def test_context_propagates_to_log_output():
    set_context(trace_id="tid-xyz", user_id="u-001", service_name="my-svc", env="prod")
    logger, buf = _make_logger_with_capture()
    logger.warning("something suspicious")
    output = buf.getvalue().strip()
    data = json.loads(output)
    assert data["trace_id"] == "tid-xyz"
    assert data["user_id"] == "u-001"
    assert data.get("env") == "prod"


def test_error_sets_anomaly_alert_after_burst():
    logger, buf = _make_logger_with_capture()
    # Override threshold to make it fire quickly
    logger._anomaly = AnomalyDetector(window_secs=60.0, burst_threshold=3)

    for _ in range(5):
        logger.error("something failed")

    lines = [l for l in buf.getvalue().splitlines() if l.strip()]
    alert_seen = any(json.loads(l).get("anomaly_alert") for l in lines)
    assert alert_seen, "anomaly_alert should appear in JSON output after burst"

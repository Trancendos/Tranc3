# tests/test_circuit_core.py
# Tests for src/resilience/circuit_core.py — the shared TASD-001 Phase 2
# transition primitives used by all 4 circuit breaker implementations.

import logging

from src.resilience.circuit_core import log_circuit_transition, should_recover
from src.resilience.circuit_state import CircuitState


class TestShouldRecover:
    def test_false_before_timeout(self):
        assert should_recover(elapsed_seconds=5.0, recovery_timeout_seconds=30.0) is False

    def test_true_at_exact_timeout(self):
        assert should_recover(elapsed_seconds=30.0, recovery_timeout_seconds=30.0) is True

    def test_true_after_timeout(self):
        assert should_recover(elapsed_seconds=31.0, recovery_timeout_seconds=30.0) is True

    def test_unit_invariant_ms(self):
        # Same comparison holds regardless of unit, as long as both sides match.
        assert should_recover(elapsed_seconds=30000.0, recovery_timeout_seconds=30000.0) is True
        assert should_recover(elapsed_seconds=29999.0, recovery_timeout_seconds=30000.0) is False


class TestLogCircuitTransition:
    def test_logs_structured_event(self, caplog):
        with caplog.at_level(logging.INFO, logger="tranc3.resilience.circuit_core"):
            log_circuit_transition("test-service", CircuitState.CLOSED, CircuitState.OPEN)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.message == "circuit_breaker_state_transition"
        assert record.service == "test-service"
        assert record.from_state == "closed"
        assert record.to_state == "open"

    def test_accepts_plain_strings_too(self, caplog):
        # loop_validator's CircuitState was historically a plain class; guard
        # against a caller passing bare strings rather than enum members.
        with caplog.at_level(logging.INFO, logger="tranc3.resilience.circuit_core"):
            log_circuit_transition("svc", "closed", "open")

        record = caplog.records[0]
        assert record.from_state == "closed"
        assert record.to_state == "open"


class TestLoopValidatorBreakerRecoveryPath:
    """loop_validator.CircuitBreaker's OPEN -> HALF_OPEN -> CLOSED path — not
    exercised by tests/test_full_suite.py's existing coverage, which
    deliberately uses recovery_timeout=999 to stay in OPEN."""

    def test_recovers_through_half_open_to_closed(self):
        from src.validation.loop_validator import CircuitBreaker, CircuitState

        cb = CircuitBreaker(
            "recovery-test", failure_threshold=1, recovery_timeout=0.0, success_threshold=1
        )
        try:
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        # recovery_timeout=0.0 means the circuit opened and immediately became
        # eligible to recover — the next `.state` read observes HALF_OPEN.
        assert cb.state == CircuitState.HALF_OPEN

        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

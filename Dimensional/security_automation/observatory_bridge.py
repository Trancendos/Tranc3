"""SecurityWatchdog → The Observatory, carrying the scanner's learning with it.

WHAT WAS WRONG

`watchdog.py` is 447 lines that catch security violations at the moment a file
is written, rather than waiting for CI. It had **zero importers**. Nothing
started it, nothing consumed its alerts, and its `on_violation` callback — the
entire point of the design — was never supplied. The capability was built and
then left unplugged.

Its sibling `adaptive_scanner.py` is genuinely adaptive: it tracks how often a
rule has fired falsely in this codebase and attaches `adaptive_confidence`,
`false_positive_rate` and a `suppression_reason` to every finding. That learning
also went nowhere, because the only consumer that could have acted on it did not
exist.

WHAT THIS DOES

Supplies the missing callback. Each `ScanAlert` becomes Observatory events, and
the scanner's confidence travels with them rather than being flattened away:

  * `Confidence.SUPPRESSED` findings are recorded at DEBUG and never alert. The
    scanner has learned this rule misfires here; forwarding it as a security
    event would train the humans to ignore the channel.
  * Everything else maps its scanner severity onto an Observatory severity, and
    carries `adaptive_confidence` / `false_positive_rate` in metadata so a
    reviewer can rank by "how sure is it" and not only "how bad would it be".

That is the adaptive behaviour being *used*, not merely present: the same
violation produces a louder or quieter event depending on what the scanner has
learned about that rule in this codebase.

WHY IT LIVES IN Dimensional/ AND NOT src/

The Observatory is `src/observability/observatory.py`, and `src/` is absent from
the 74 services that build from their own directory. A bridge that imported it
unconditionally could not be used by them. The import is therefore deferred and
guarded, exactly like `workers/chaos-party/observatory_bridge.py` — with the
difference that this one lives in the shared core, so it is the *last* copy of
this pattern anyone should need to write.

FAIL-OPEN, ALWAYS

A telemetry sink must never take down the thing it observes. If the Observatory
is unavailable the alert is dropped with a logged warning and the watchdog keeps
scanning. The precedent is set: an earlier version of this platform had seven
workers that failed to start because an optional telemetry import was not
guarded.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from Dimensional.security_automation.adaptive_scanner import AdaptiveViolation, Confidence
from Dimensional.security_automation.scanner import Severity

if TYPE_CHECKING:  # pragma: no cover — typing only, never imported at runtime
    from Dimensional.security_automation.watchdog import ScanAlert

logger = logging.getLogger("dimensional.security-automation.observatory-bridge")

# Scanner severity → Observatory severity. SECURITY rather than CRITICAL for the
# top two: the Observatory routes SECURITY events to the Basement for retention
# and to Prometheus's security counters, which is where a live code violation
# belongs. CRITICAL there means "the platform is broken", a different claim.
_SEVERITY_MAP = {
    Severity.CRITICAL: "SECURITY",
    Severity.HIGH: "SECURITY",
    Severity.MEDIUM: "WARNING",
    Severity.LOW: "INFO",
    Severity.INFO: "INFO",
}


def _observatory() -> Optional[Any]:
    """The Observatory singleton, or None when it cannot be reached.

    Deferred and guarded: `src/` is not in an own-context worker's image, so a
    module-level import would raise ImportError there and take the watchdog with
    it.
    """
    try:
        from src.observability.observatory import get_observatory
    except Exception:  # noqa: BLE001 — absent src/ is expected, not exceptional
        return None
    try:
        return get_observatory()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Observatory unavailable: %s", exc)
        return None


def classify(violation: AdaptiveViolation) -> tuple[str, bool]:
    """Map one violation to (observatory_severity, should_alert).

    `should_alert` is False when the scanner has learned this rule misfires in
    this codebase. The event is still recorded — suppressed findings are
    evidence about the scanner's own accuracy, and discarding them would make
    that accuracy unmeasurable — but it is recorded quietly.
    """
    if violation.confidence_level is Confidence.SUPPRESSED:
        return "DEBUG", False
    severity = _SEVERITY_MAP.get(violation.base.severity, "INFO")
    # A low-confidence finding is real enough to record but not to page anyone,
    # so it is capped below the alerting threshold regardless of how severe the
    # rule claims to be.
    if violation.confidence_level is Confidence.LOW and severity == "SECURITY":
        return "WARNING", False
    return severity, severity in ("SECURITY", "WARNING")


def build_events(alert: "ScanAlert") -> list[dict[str, Any]]:
    """Shape one ScanAlert as a list of Observatory record() kwargs."""
    events: list[dict[str, Any]] = []
    for violation in alert.new_violations:
        severity, alerting = classify(violation)
        base = violation.base
        events.append(
            {
                "event_type": f"security.violation.{base.rule_id}",
                "actor": "The Queen",
                "target": f"{base.file}:{base.line}",
                "category": "SECURITY",
                "severity": severity,
                "service": "dimensional.security-automation",
                "outcome": "detected",
                "metadata": {
                    "rule_id": base.rule_id,
                    "message": base.message,
                    "suggestion": base.suggestion,
                    "fixable": base.fixable,
                    "scanner_severity": getattr(base.severity, "value", str(base.severity)),
                    "confidence": getattr(
                        violation.confidence_level, "value", str(violation.confidence_level)
                    ),
                    "adaptive_confidence": round(violation.adaptive_confidence, 4),
                    "false_positive_rate": round(violation.false_positive_rate, 4),
                    "similar_history_count": violation.similar_history_count,
                    "suppression_reason": violation.suppression_reason or None,
                    "alerting": alerting,
                    "trigger_file": alert.trigger_file,
                    "scan_duration_s": round(alert.scan_duration, 4),
                },
            }
        )
    return events


def forward(alert: "ScanAlert") -> int:
    """Forward one alert to the Observatory. Never raises.

    Returns the number of events recorded, so a caller can assert the wiring
    works without reaching into the Observatory's storage.
    """
    obs = _observatory()
    if obs is None:
        logger.debug(
            "Observatory not reachable — %d violation(s) not forwarded", len(alert.new_violations)
        )
        return 0

    try:
        from src.observability.observatory import EventCategory, EventSeverity
    except Exception:  # noqa: BLE001
        return 0

    recorded = 0
    for payload in build_events(alert):
        try:
            payload = dict(payload)
            payload["category"] = EventCategory[payload["category"]]
            payload["severity"] = EventSeverity[payload["severity"]]
            obs.record(payload.pop("event_type"), **payload)
            recorded += 1
        except Exception as exc:  # noqa: BLE001 — one bad event must not stop the rest
            logger.warning("Observatory rejected a security event: %s", exc)
    return recorded


def make_callback() -> Callable[[Any], None]:
    """A SecurityWatchdog `on_violation` callback that forwards to the Observatory.

    Usage:
        SecurityWatchdog(watch_paths=[...], on_violation=make_callback())
    """

    def _callback(alert: Any) -> None:
        try:
            forward(alert)
        except Exception as exc:  # noqa: BLE001 — the watchdog must keep running
            logger.warning("security event forwarding failed: %s", exc)

    return _callback


__all__ = ["build_events", "classify", "forward", "make_callback"]

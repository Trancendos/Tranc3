"""
Dimensional.security_automation — Proactive Security Automation Framework.

Prevents the recurrence of the ~297 CodeQL alerts that were manually remediated
by enforcing secure coding patterns at three layers:

Layer 1: AST-based pre-commit scanner (blocks bad patterns before they land)
Layer 2: Automated remediation engine (self-heals known patterns)
Layer 3: Security telemetry collector (tracks compliance trends over time)

Layer 4: Adaptive scanning (learns from codebase patterns, reduces false positives)
Layer 5: Real-time file watching (catches violations at point of authorship)
Layer 6: Violation prediction (identifies high-risk files before scanning)

Usage:
    # Run the scanner (pre-commit hook or CI step):
    python -m Dimensional.security_automation scan src/

    # Auto-fix violations:
    python -m Dimensional.security_automation fix src/

    # Generate compliance report:
    python -m Dimensional.security_automation report src/

    # Run as a long-lived watcher (for CI):
    python -m Dimensional.security_automation watch src/

    # Adaptive scan (with confidence scoring):
    from Dimensional.security_automation.adaptive_scanner import AdaptiveScanner
    scanner = AdaptiveScanner()
    violations = scanner.scan_path("src/")

    # Predict likely violation areas:
    from Dimensional.security_automation.predictor import ViolationPredictor
    predictor = ViolationPredictor()
    predictions = predictor.predict("src/")
"""

from Dimensional.security_automation.adaptive_scanner import (  # codeql[py/cyclic-import]
    AdaptiveScanner,
    AdaptiveViolation,
    Confidence,
)
from Dimensional.security_automation.predictor import (  # codeql[py/cyclic-import]
    Prediction,
    ViolationPredictor,
)
from Dimensional.security_automation.remediator import AutoRemediator  # codeql[py/cyclic-import]
from Dimensional.security_automation.remediator_v2 import (  # codeql[py/cyclic-import]
    AutoRemediatorV2,
    FixResult,
    RemediationSession,
)
from Dimensional.security_automation.scanner import (  # codeql[py/cyclic-import]
    SecurityScanner,
    Violation,
)
from Dimensional.security_automation.telemetry import SecurityTelemetry  # codeql[py/cyclic-import]
from Dimensional.security_automation.watchdog import (  # codeql[py/cyclic-import]
    ScanAlert,
    SecurityWatchdog,
)

__all__ = [
    # Core scanner
    "SecurityScanner",
    "Violation",
    # Adaptive scanner
    "AdaptiveScanner",
    "AdaptiveViolation",
    "Confidence",
    # Remediators
    "AutoRemediator",
    "AutoRemediatorV2",
    "FixResult",
    "RemediationSession",
    # Telemetry
    "SecurityTelemetry",
    # Watchdog
    "SecurityWatchdog",
    "ScanAlert",
    # Predictor
    "ViolationPredictor",
    "Prediction",
]

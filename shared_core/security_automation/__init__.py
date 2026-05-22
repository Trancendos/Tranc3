"""
shared_core.security_automation — Proactive Security Automation Framework.

Prevents the recurrence of the ~297 CodeQL alerts that were manually remediated
by enforcing secure coding patterns at three layers:

Layer 1: AST-based pre-commit scanner (blocks bad patterns before they land)
Layer 2: Automated remediation engine (self-heals known patterns)
Layer 3: Security telemetry collector (tracks compliance trends over time)

Usage:
    # Run the scanner (pre-commit hook or CI step):
    python -m shared_core.security_automation scan src/

    # Auto-fix violations:
    python -m shared_core.security_automation fix src/

    # Generate compliance report:
    python -m shared_core.security_automation report src/

    # Run as a long-lived watcher (for CI):
    python -m shared_core.security_automation watch src/
"""

from shared_core.security_automation.remediator import AutoRemediator
from shared_core.security_automation.scanner import SecurityScanner, Violation
from shared_core.security_automation.telemetry import SecurityTelemetry

__all__ = ["SecurityScanner", "Violation", "AutoRemediator", "SecurityTelemetry"]

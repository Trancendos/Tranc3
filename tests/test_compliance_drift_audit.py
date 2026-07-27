"""scripts/compliance_drift_audit.py checks that the code-grounded findings
Magna-Carta's compliance matrices (Security MC-015, Encryption MC-014,
Knowledge MC-018) assert are fixed actually stay fixed. Guards against those
matrices silently drifting out of sync with the code again."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_compliance_drift_audit_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compliance_drift_audit.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

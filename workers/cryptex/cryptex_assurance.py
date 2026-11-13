"""Cryptex scan assurance primitives; no network or destructive side effects.

A security engine that did not substantively run MUST NOT report a clean result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class Assessment(str, Enum):
    THREAT = "threat"
    CLEAN = "clean"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ScanAssurance:
    assessment: Assessment
    reason: str
    coverage_confirmed: bool


def assess_engine_output(engine: str, output: Mapping[str, Any]) -> ScanAssurance:
    """Classify one detector's response, distinguishing a missing scan from clean."""
    if not isinstance(output, Mapping):
        return ScanAssurance(Assessment.INCONCLUSIVE, "Malformed engine output", False)
    if engine == "offline" or output.get("scan_performed") is False:
        return ScanAssurance(
            Assessment.INCONCLUSIVE, "No substantive security scan completed", False
        )
    if not isinstance(output.get("threat_found"), bool):
        return ScanAssurance(
            Assessment.INCONCLUSIVE, "Engine did not report a validated threat result", False
        )
    if output["threat_found"]:
        return ScanAssurance(
            Assessment.THREAT, "Positive detection returned by security engine", True
        )
    return ScanAssurance(
        Assessment.CLEAN, "Security engine executed and returned no detection", True
    )

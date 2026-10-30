"""Conservative capability-aware Cryptex security engine selection.

A threat-intelligence lookup cannot substitute for a file scan or SAST.
Suricata is an offline stub until an actual log collector is wired.
Wazuh alert lookups cannot substitute for active vulnerability assessment.
"""

from __future__ import annotations

from collections.abc import Iterable

ENGINE_COVERAGE: dict[str, frozenset[str]] = {
    "file": frozenset({"clamav", "yara"}),
    "network": frozenset({"openvas"}),
    "vulnerability": frozenset({"openvas"}),
    "threat_intel": frozenset({"misp"}),
    "sast": frozenset({"semgrep"}),
    "ioc": frozenset({"misp"}),
}


def compatible_engines(scan_type: str, candidates: Iterable[str]) -> list[str]:
    """Keep existing priority order, retaining only valid detectors and offline."""
    allowed = ENGINE_COVERAGE.get(scan_type, frozenset())
    original = list(candidates)
    result = [name for name in original if name in allowed]
    if "offline" in original:
        result.append("offline")
    return result

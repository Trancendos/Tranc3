"""OpenTelemetry releases in lockstep, so its pins must move together.

On 2026-10-23 `main` could not be installed: Renovate's security PR #1424
bumped `opentelemetry-api` to 1.45.1 alone, while `opentelemetry-sdk==1.45.0`
and `opentelemetry-semantic-conventions==0.66b0` (pulled by every
instrumentation package) both require `opentelemetry-api==1.45.0` exactly.
`pip install -r requirements.txt` failed with ResolutionImpossible, and nothing
reported it because the PR only changed one line.

The rule checked here is the one upstream publishes: every core package
(`api`, `sdk`, `exporter-*`, `proto`) shares one version, and every
contrib package (`instrumentation-*`, `semantic-conventions`) shares the
matching `0.Nb*` version.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_PIN = re.compile(r"^(opentelemetry-[a-z0-9-]+)==([0-9][^\s#]*)", re.MULTILINE)
_CONTRIB = ("opentelemetry-instrumentation", "opentelemetry-semantic-conventions")


def _requirement_files() -> list[Path]:
    files = [REPO / "requirements.txt"]
    files += sorted((REPO / "workers").glob("*/requirements*.txt"))
    return [f for f in files if _PIN.search(f.read_text(encoding="utf-8"))]


@pytest.mark.parametrize("path", _requirement_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_opentelemetry_pins_move_together(path: Path):
    pins = dict(_PIN.findall(path.read_text(encoding="utf-8")))
    core = {v for k, v in pins.items() if not k.startswith(_CONTRIB)}
    contrib = {v for k, v in pins.items() if k.startswith(_CONTRIB)}
    assert len(core) <= 1, f"{path.name}: core OpenTelemetry pins disagree: {sorted(core)}"
    assert len(contrib) <= 1, f"{path.name}: contrib OpenTelemetry pins disagree: {sorted(contrib)}"

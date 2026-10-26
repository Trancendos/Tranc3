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
_PIN = re.compile(r"^\s*(opentelemetry-[a-z0-9-]+)\s*==\s*([0-9][^\s#]*)", re.MULTILINE)
_CONTRIB = (
    "opentelemetry-instrumentation",
    "opentelemetry-semantic-conventions",
    "opentelemetry-util-http",
)
# Explicitly reviewed core/contrib release pair. Extend only after checking the
# contrib release metadata and pip resolution; update generated SBOMs with it.
_APPROVED_CORE_CONTRIB_PAIRS = {("1.45.1", "0.66b1")}
_EXCLUDED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "build", "dist"}


def _requirement_files() -> list[Path]:
    """Discover manifests recursively, without scanning vendored environments."""
    files = (
        path
        for path in REPO.rglob("requirements*.txt")
        if not _EXCLUDED_DIRECTORIES.intersection(path.relative_to(REPO).parts)
    )
    return sorted(path for path in files if _PIN.search(path.read_text(encoding="utf-8")))


def _validate_pin_text(content: str, label: str) -> None:
    pins = _PIN.findall(content)
    by_name: dict[str, set[str]] = {}
    for name, version in pins:
        by_name.setdefault(name, set()).add(version)

    conflicts = {name: sorted(vs) for name, vs in by_name.items() if len(vs) > 1}
    assert not conflicts, f"{label}: conflicting pins for identical packages: {conflicts}"

    core = {v for name, v in pins if not name.startswith(_CONTRIB)}
    contrib = {v for name, v in pins if name.startswith(_CONTRIB)}
    assert len(core) <= 1, f"{label}: core OpenTelemetry pins disagree: {sorted(core)}"
    assert len(contrib) <= 1, f"{label}: contrib OpenTelemetry pins disagree: {sorted(contrib)}"
    if core and contrib:
        pair = (next(iter(core)), next(iter(contrib)))
        assert pair in _APPROVED_CORE_CONTRIB_PAIRS, (
            f"{label}: incompatible core/contrib release pair: {pair}. "
            "Verify upstream metadata and pip resolution before approving a new pair."
        )


@pytest.mark.parametrize("_path", _requirement_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_opentelemetry_pins_move_together(_path: Path) -> None:
    _validate_pin_text(_path.read_text(encoding="utf-8"), str(_path.relative_to(REPO)))


def test_opentelemetry_pins_agree_across_requirement_files() -> None:
    files = _requirement_files()
    assert files, "No OpenTelemetry requirements were discovered"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    _validate_pin_text(combined, "all requirement files")


@pytest.mark.parametrize(
    "content",
    [
        "opentelemetry-api==1.45.0\nopentelemetry-api==1.45.1\n",
        "opentelemetry-api==1.45.1\nopentelemetry-instrumentation-fastapi==0.66b0\n",
        "opentelemetry-api==1.45.1\nopentelemetry-sdk==1.45.0\n",
    ],
)
def test_invalid_release_sets_are_rejected(content: str) -> None:
    with pytest.raises(AssertionError):
        _validate_pin_text(content, "synthetic fixture")


def test_http_util_is_classified_as_contrib() -> None:
    _validate_pin_text(
        "opentelemetry-api==1.45.1\nopentelemetry-util-http==0.66b1\n",
        "synthetic fixture",
    )


def test_recursive_discovery_finds_nested_manifests(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "nested" / "another" / "requirements-worker.txt"
    path.parent.mkdir(parents=True)
    path.write_text("opentelemetry-api==1.45.1\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "REPO", tmp_path)
    assert _requirement_files() == [path]

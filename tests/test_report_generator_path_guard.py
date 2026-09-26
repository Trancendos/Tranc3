"""`save_reports` must refuse a traversing output directory, and accept a legitimate one.

The guard was added on #1239 after the substring form (`".." in str(path)`) was
found to reject any directory whose *name* merely contains two dots — a
fail-closed control that closed on valid input. These tests pin both halves of
that, because a guard that only ever rejects is as broken as one that only ever
accepts, and only the rejecting half tends to get tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.compliance.report_generator import save_reports


class _Report:
    """Minimal stand-in: the guard runs before any report field is read."""

    score = 100.0
    status = "compliant"
    checks: list[object] = []
    generated_at = "2026-09-26T00:00:00Z"


@pytest.mark.parametrize(
    "hostile",
    [
        "../escape",
        "reports/../../escape",
        "a/../../b",
        "..",
    ],
)
def test_traversing_output_dir_is_refused(hostile: str) -> None:
    with pytest.raises(ValueError, match="Invalid file path"):
        save_reports(_Report(), Path(hostile))  # type: ignore[arg-type]


def test_null_byte_in_output_dir_is_refused() -> None:
    with pytest.raises(ValueError, match="Invalid file path"):
        save_reports(_Report(), Path("reports\x00/evil"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "legitimate",
    [
        "release..candidate",  # two dots inside a NAME, not a traversal segment
        "v1.2..v1.3",
        "reports",
        "nested/reports",
    ],
)
def test_directory_names_containing_two_dots_are_not_refused(
    tmp_path: Path, legitimate: str
) -> None:
    """The regression the guard was rewritten for.

    `".." in str(path)` matched these and rejected them. A path segment equal
    to `..` is traversal; two dots inside a segment is a version string.
    """
    target = tmp_path / legitimate
    # Must not raise ValueError("Invalid file path"). Anything downstream is
    # this test's business only insofar as it proves the guard let it through.
    try:
        save_reports(_Report(), target)  # type: ignore[arg-type]
    except ValueError as exc:  # pragma: no cover - only on regression
        if "Invalid file path" in str(exc):
            pytest.fail(f"guard rejected a legitimate directory name: {legitimate}")
    except Exception:  # noqa: BLE001 - downstream failure is not the guard
        pass

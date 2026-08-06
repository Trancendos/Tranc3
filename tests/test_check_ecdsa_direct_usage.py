"""
Tests for scripts/check_ecdsa_direct_usage.py — the CI drift guard behind the
CVE-2024-23342 accepted-risk claim (no direct ecdsa usage, no ES256/384/512).

Exercises _scan_file() against small inline source snippets rather than real
repo files, so each case is deterministic and isolated from ambient code.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_ecdsa_direct_usage.py"
_spec = importlib.util.spec_from_file_location("check_ecdsa_direct_usage", _SCRIPT_PATH)
check_ecdsa = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = check_ecdsa
_spec.loader.exec_module(check_ecdsa)


def _scan_source(tmp_path, source: str) -> list[str]:
    f = tmp_path / "sample.py"
    f.write_text(source, encoding="utf-8")
    monkeypatched_root = check_ecdsa.REPO_ROOT
    try:
        check_ecdsa.REPO_ROOT = tmp_path
        violations, errors = check_ecdsa._scan_file(f)
        assert errors == []
        return violations
    finally:
        check_ecdsa.REPO_ROOT = monkeypatched_root


# ── Direct ecdsa imports ─────────────────────────────────────────────────────


def test_direct_import_flagged(tmp_path):
    assert _scan_source(tmp_path, "import ecdsa\n")


def test_from_ecdsa_submodule_import_flagged(tmp_path):
    assert _scan_source(tmp_path, "from ecdsa.keys import SigningKey\n")


def test_relative_import_of_local_module_named_ecdsa_not_flagged(tmp_path):
    """cubic P2: `from .ecdsa import X` resolves within the current package, not
    to the third-party 'ecdsa' distribution — node.level > 0 must be exempt."""
    assert _scan_source(tmp_path, "from .ecdsa import something\n") == []


def test_unrelated_import_not_flagged(tmp_path):
    assert _scan_source(tmp_path, "import os\nfrom typing import Optional\n") == []


# ── ES256/384/512 literal usage ─────────────────────────────────────────────


def test_bare_string_literal_flagged(tmp_path):
    assert _scan_source(tmp_path, 'ALG = "ES256"\n')


def test_docstring_mention_not_flagged(tmp_path):
    assert _scan_source(tmp_path, '"""Do not use ES256 here."""\n') == []


def test_binop_concatenation_flagged(tmp_path):
    assert _scan_source(tmp_path, 'ALG = "ES" + "256"\n')


def test_name_identifier_flagged(tmp_path):
    """`from jose.constants import ES256` binds ES256 as a bare name — a later
    `algorithm=ES256` reference must still be caught even without the string
    literal appearing again."""
    assert _scan_source(tmp_path, "ES256 = object()\nx = ES256\n")


def test_attribute_access_flagged(tmp_path):
    assert _scan_source(tmp_path, "x = Algorithms.ES256\n")


def test_aliased_import_flagged(tmp_path):
    assert _scan_source(tmp_path, "from jose.constants import ES256 as ALG\n")


# ── f-string handling ────────────────────────────────────────────────────────


def test_literal_only_fstring_reported_exactly_once(tmp_path):
    violations = _scan_source(tmp_path, 'ALG = f"ES256"\n')
    assert len(violations) == 1


def test_nested_constant_fstring_reported_exactly_once(tmp_path):
    """cubic P3: f"{'ES256'}" was double-reported by both the plain-Constant
    check and the fold-check before _joined_str_child_ids() recursed into
    FormattedValue.value."""
    violations = _scan_source(tmp_path, "ALG = f\"{'ES256'}\"\n")
    assert len(violations) == 1


def test_unfoldable_mixed_fstring_still_reported(tmp_path):
    """cubic P1: f"{'ES256' + suffix}" (suffix non-constant) never folds, so the
    fold-check alone would miss it entirely — the literal segment must still be
    caught by the plain-Constant check, not silently suppressed by the
    nested-constant dedup logic meant for the *foldable* case."""
    violations = _scan_source(
        tmp_path,
        'suffix = ""\nALG = f"{\'ES256\' + suffix}"\n',
    )
    assert len(violations) == 1


def test_dynamic_fstring_without_es_literal_not_flagged(tmp_path):
    violations = _scan_source(tmp_path, 'name = "x"\nALG = f"{name}"\n')
    assert violations == []

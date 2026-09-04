"""Tests for scripts/check_trivyignore_governance.py.

The file this gate protects is the one place on the platform where NOT acting
on a finding is the intended behaviour, so every case here is a way a
suppression could stop being a decision and become a blind spot.

Two of them were found against the real `.trivyignore`, not invented: two
entries carried a full justification and no re-check trigger, and both were
suppressed on a claim about upstream ("no fixed version exists") that stops
being true the day upstream ships one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_trivyignore_governance.py"

GOOD = """\
# CVE-2025-11111 (GHSA-aaaa-bbbb-cccc) — example heap overflow
# Affects: example < 2.0. No fixed release exists; the vulnerable code path is
# never reached because we do not call the affected function anywhere.
# Re-check trigger: a patched release ships, or that call appears.
CVE-2025-11111
"""


def _load():
    spec = importlib.util.spec_from_file_location("_tig", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_tig"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def checker():
    return _load()


def test_a_fully_documented_entry_passes(checker):
    assert checker.check(GOOD, {"CVE-2025-11111"}) == []


def test_a_bare_id_is_rejected(checker):
    """Valid Trivy syntax, and it silences a real finding with no record.

    One line holding `CVE-2025-12345` suppresses the finding in three scanners
    with no trace of who decided or why.
    """
    problems = checker.check("CVE-2025-11111\n", {"CVE-2025-11111"})
    assert any("no justification" in p for p in problems)


def test_a_comment_that_only_repeats_the_id_is_not_a_justification(checker):
    """The cheapest way to satisfy a naive "has a comment above it" check."""
    text = "# CVE-2025-11111\nCVE-2025-11111\n"
    problems = checker.check(text, {"CVE-2025-11111"})
    assert any("no justification" in p for p in problems)


def test_a_justification_without_a_re_check_trigger_is_rejected(checker):
    """Found against the real file, twice.

    "No fixed version exists" is a claim about somebody else's release
    schedule. Without a trigger, nobody ever asks again.
    """
    text = (
        "# CVE-2025-11111 — example overflow in a dependency we pin.\n"
        "# Affects example < 2.0 and no fixed release exists at the moment.\n"
        "CVE-2025-11111\n"
    )
    problems = checker.check(text, {"CVE-2025-11111"})
    assert any("no re-check trigger" in p for p in problems)


def test_a_lapsed_review_by_date_is_rejected(checker):
    """A suppression past its own review date is an undated one."""
    text = GOOD.replace("Re-check trigger:", "Review-By: 2020-01-01 — trigger:")
    problems = checker.check(text, {"CVE-2025-11111"})
    assert any("past its Review-By date" in p for p in problems)


def test_a_future_review_by_date_is_accepted(checker):
    text = GOOD.replace("Re-check trigger:", "Review-By: 2099-01-01 — trigger:")
    assert checker.check(text, {"CVE-2025-11111"}) == []


def test_an_unregistered_vulnerability_is_rejected(checker):
    """The suppression file and the accepted-risk register must agree.

    The census applies exactly this rule to its own findings: an unrecorded
    accepted risk is an ignored one.
    """
    problems = checker.check(GOOD, set())
    assert any("not named in" in p for p in problems)


def test_a_misconfiguration_id_does_not_need_the_register(checker):
    """`KSV118` is a Trivy check, not a vulnerability.

    Requiring it in the accepted-risk register would put a non-vulnerability
    in a vulnerability register, and a rule that demands nonsense gets
    suppressed rather than followed.
    """
    text = GOOD.replace("CVE-2025-11111", "KSV118")
    assert checker.check(text, set()) == []


def test_a_duplicate_id_is_rejected(checker):
    """Two justifications for one id means one of them is not the reason."""
    problems = checker.check(GOOD + "\n" + GOOD, {"CVE-2025-11111"})
    assert any("repeats" in p for p in problems)


def test_a_blank_line_breaks_the_comment_block(checker):
    """Otherwise a justification could be attributed to an unrelated entry.

    The reader attributes a comment to the id directly beneath it, and so must
    this — a block separated by a blank line belongs to nothing.
    """
    text = GOOD.replace("CVE-2025-11111\n", "\nCVE-2025-11111\n")
    problems = checker.check(text, {"CVE-2025-11111"})
    assert any("no justification" in p for p in problems)


def test_a_commit_only_fix_is_not_a_released_fix(checker, monkeypatch):
    """OSV records a GIT-range fix as a commit hash, not a version.

    Reporting that as FIX AVAILABLE sends a reader looking for a release that
    has not shipped. All three of this tree's vulnerability suppressions have a
    commit-only fix recorded upstream and remain correct because of it.
    """

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            import json

            return json.dumps(self._payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    payload = {
        "affected": [
            {
                "package": {"name": "example", "ecosystem": "PyPI"},
                "ranges": [{"type": "GIT", "events": [{"fixed": "deadbeef" * 5}]}],
            }
        ]
    }
    monkeypatch.setattr(checker.urllib.request, "urlopen", lambda *a, **k: _Response(payload))
    fixed, note = checker.upstream_fixed("CVE-2025-11111")
    assert not fixed
    assert "commit-only" in note


def test_a_released_fix_is_reported(checker, monkeypatch):
    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            import json

            return json.dumps(self._payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    payload = {
        "affected": [
            {
                "package": {"name": "example", "ecosystem": "PyPI"},
                "ranges": [{"type": "ECOSYSTEM", "events": [{"fixed": "2.0.1"}]}],
            }
        ]
    }
    monkeypatch.setattr(checker.urllib.request, "urlopen", lambda *a, **k: _Response(payload))
    fixed, note = checker.upstream_fixed("CVE-2025-11111")
    assert fixed
    assert "2.0.1" in note


def test_an_unreachable_osv_is_not_a_finding(checker, monkeypatch):
    """This runs on a schedule against somebody else's service.

    A network blip must not read as "no fix exists", and must not raise.
    """

    def _boom(*_args, **_kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr(checker.urllib.request, "urlopen", _boom)
    fixed, note = checker.upstream_fixed("CVE-2025-11111")
    assert not fixed
    assert "unreachable" in note


def test_the_real_trivyignore_passes():
    """The estate's own suppression file, not a synthetic stand-in."""
    module = _load()
    assert module.main([]) == 0


def test_a_traversal_shaped_id_is_never_queried(checker, monkeypatch):
    """The id is interpolated into a URL, so its shape is checked, not trusted.

    `CVE-../../x` satisfies the prefix match that decides whether an id is a
    vulnerability, and would walk the OSV API path if that were the only gate.
    """

    def _boom(*_args, **_kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("a malformed id reached the network")

    monkeypatch.setattr(checker.urllib.request, "urlopen", _boom)
    fixed, note = checker.upstream_fixed("CVE-../../etc/passwd")
    assert not fixed
    assert "not in a form safe to query" in note


def test_a_published_fix_fails_the_upstream_run(checker, monkeypatch, capsys):
    """The scheduled job's whole point is surfacing an expired suppression.

    Printing FIX AVAILABLE to stdout and exiting 0 is the pattern this checker
    exists to reject — nobody reads a green scheduled job, so a fix shipping
    would go unnoticed until a PR happened to re-run the offline gate.
    """
    monkeypatch.setattr(checker, "upstream_fixed", lambda _entry: (True, "PyPI/x fixed in 2.0"))
    assert checker.main(["--check-upstream"]) == 1
    assert "a fixed release has shipped" in capsys.readouterr().err


def test_an_unreachable_osv_does_not_fail_the_upstream_run(checker, monkeypatch):
    """A verdict that depends on somebody else's uptime is not a verdict.

    `upstream_fixed` returns distinct tuples for "fixed" and "unreachable"
    precisely so this distinction can be made.
    """
    monkeypatch.setattr(
        checker, "upstream_fixed", lambda _entry: (False, "OSV unreachable (URLError)")
    )
    assert checker.main(["--check-upstream"]) == 0


def test_a_malformed_review_by_value_is_reported(checker):
    """`Review-By: soon` satisfies the trigger words and no date check.

    The label alone made a suppression look dated when nothing could compare
    it, so it could never lapse.
    """
    text = GOOD.replace("Re-check trigger:", "Review-By: soon — trigger:")
    problems = checker.check(text, {"CVE-2025-11111"})
    assert any("not an ISO date" in p for p in problems)


def test_a_temp_advisory_can_be_registered(checker):
    """VULN_ID required TEMP ids to be registered; the register scan could not
    find one, so every valid TEMP suppression was rejected."""
    text = GOOD.replace("CVE-2025-11111", "TEMP-2025-0001")


def test_a_temp_advisory_can_be_registered(checker, monkeypatch, tmp_path):
    """VULN_ID required TEMP ids to be registered; the register scan could not
    find one, so every valid TEMP suppression was rejected."""
    register = tmp_path / "SECURITY.md"
    register.write_text("TEMP-2025-0001", encoding="utf-8")
    monkeypatch.setattr(checker, "REGISTERS", (str(register),))
    text = GOOD.replace("CVE-2025-11111", "TEMP-2025-0001")
    assert checker.check(text, checker._registered_ids()) == []

    class _Response:
        def read(self):
            import json

            return json.dumps({"affected": {"not": "a list"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(checker.urllib.request, "urlopen", lambda *a, **k: _Response())
    fixed, _note = checker.upstream_fixed("CVE-2025-11111")
    assert fixed is False

"""Tests for src/dvms/dispatch.py — the census-to-ITSM step.

The ordering is the part of this module with judgement in it, so it is the part
under test. Each case was calibrated by breaking the behaviour it names.
"""

from __future__ import annotations

import pytest

from src.dvms.dispatch import KIND_CHANGE, KIND_INCIDENT, apply, plan, summarise


def _surface(path, findings=None, errored=False, reason=None):
    record = {"surface": path, "errored": errored, "findings": findings or []}
    if reason:
        record["reason"] = reason
    return record


def _finding(package, classification, ident=None):
    return {"package": package, "classification": classification, "id": ident or f"ID-{package}"}


def test_a_fixable_finding_becomes_a_change():
    """A patch exists and is reachable — that is a planned action."""
    census = {
        "surfaces": [
            _surface("workers/the-studio/requirements.txt", [_finding("pillow", "fixable")])
        ]
    }
    (item,) = plan(census)
    assert item.kind == KIND_CHANGE
    assert item.location == "The Studio"


def test_a_blocked_finding_becomes_an_incident():
    """A patch exists but is out of reach — there is no action to plan.

    Filing it as a Change would put a deployment on a queue that cannot be
    deployed, and it would sit there looking like work in progress.
    """
    census = {
        "surfaces": [_surface("workers/the-lab/requirements.txt", [_finding("fflate", "blocked")])]
    }
    (item,) = plan(census)
    assert item.kind == KIND_INCIDENT


def test_an_accepted_finding_raises_nothing():
    """The risk is already dispositioned in the register.

    Raising a record against a decision somebody already took is the noise
    that makes people stop reading the queue.
    """
    census = {
        "surfaces": [_surface("workers/the-lab/requirements.txt", [_finding("nltk", "accepted")])]
    }
    assert plan(census) == []


def test_an_unscannable_surface_outranks_every_known_finding():
    """Unknown exposure is worse than known exposure.

    A surface that could not be read is not a surface that is clean, and a
    queue that sorts it below a finding it can see has the ordering backwards.
    """
    census = {
        "surfaces": [
            _surface("workers/the-studio/requirements.txt", [_finding("a", "fixable")]),
            _surface("workers/cryptex/requirements.txt", errored=True, reason="npm audit 503"),
        ]
    }
    items = plan(census)
    assert items[0].priority == "p1"
    assert items[0].surface == "workers/cryptex/requirements.txt"


def test_an_owned_surface_outranks_a_cross_cutting_one():
    """Same finding, different accountability.

    A Location that owns its surface can act on it now. A cross-cutting surface
    is stewarded, which means the work is real but the owner is not the one who
    will feel it first.
    """
    census = {
        "surfaces": [
            _surface(
                "workers/rate-limit-service/requirements-worker.txt", [_finding("a", "fixable")]
            ),
            _surface("workers/the-studio/requirements.txt", [_finding("b", "fixable")]),
        ]
    }
    items = plan(census)
    assert [i.location for i in items] == ["The Studio", None]


def test_volume_breaks_the_tie_inside_a_band():
    """Eleven findings ahead of two, at the same priority."""
    census = {
        "surfaces": [
            _surface("workers/the-studio/requirements.txt", [_finding("a", "fixable")]),
            _surface(
                "workers/the-lab/requirements.txt",
                [_finding("b", "fixable"), _finding("c", "fixable")],
            ),
        ]
    }
    assert [i.location for i in plan(census)] == ["The Lab", "The Studio"]


def test_the_plan_is_stable_across_runs():
    """A queue that reshuffles itself is one nobody can tell has changed."""
    census = {
        "surfaces": [
            _surface("workers/the-studio/requirements.txt", [_finding("a", "fixable")]),
            _surface("workers/the-lab/requirements.txt", [_finding("b", "fixable")]),
            _surface("workers/tateking/requirements.txt", [_finding("c", "fixable")]),
        ]
    }
    assert [i.surface for i in plan(census)] == [i.surface for i in plan(census)]


def test_an_unroutable_record_is_kept_in_the_plan_not_dropped():
    """The failure this whole join exists to close.

    Exposure that vanishes because nobody owned it is the exact shape of the
    problem. It stays in the plan, flagged, so it is visible in the summary.
    """
    census = {
        "surfaces": [
            _surface("workers/not-a-real-worker/requirements.txt", errored=True, reason="x")
        ]
    }
    (item,) = plan(census)
    assert not item.is_routable
    assert summarise([item])["unroutable"] == 1


def test_apply_skips_an_unroutable_record_rather_than_filing_a_placeholder():
    """An incident with a plausible-looking owner is worse than none.

    It routes the page to somebody who is not on the hook, and then everybody
    believes it is handled. `resolve_ownership` refuses to guess for the same
    reason.
    """

    class _Recorder:
        def __init__(self):
            self.changes = []
            self.incidents = []

        def create_change(self, title, change_type="normal", service=None):
            self.changes.append((title, service))
            return _Fake({"title": title, "service": service})

        def create_incident(self, title, description, *, priority=None, service=None):
            self.incidents.append((title, service))
            return _Fake({"title": title, "service": service})

    class _Fake:
        def __init__(self, data):
            self._data = data

        def to_dict(self):
            return self._data

    census = {
        "surfaces": [
            _surface("workers/not-a-real-worker/requirements.txt", errored=True, reason="x"),
            _surface("workers/the-studio/requirements.txt", [_finding("a", "fixable")]),
        ]
    }
    recorder = _Recorder()
    written = apply(plan(census), service=recorder)
    assert recorder.incidents == []
    assert recorder.changes == [
        (
            "Upgrade 1 vulnerable dependency in workers/the-studio/requirements.txt",
            "The Studio",
        )
    ]
    assert any("skipped" in entry for entry in written)


def test_the_owner_embedded_by_the_census_is_used_when_present():
    """The census attaches owners; this must not resolve them a second time."""
    census = {
        "surfaces": [
            {
                "surface": "workers/anything-at-all/requirements.txt",
                "errored": False,
                "owner": {"kind": "location", "location": "Cryptex", "responsible": "Cryptex"},
                "findings": [_finding("a", "fixable")],
            }
        ]
    }
    (item,) = plan(census)
    assert item.location == "Cryptex"


@pytest.mark.parametrize("classification", ["fixable", "blocked"])
def test_every_raised_record_names_the_findings_behind_it(classification):
    """A ticket that does not say which packages is a ticket nobody can work."""
    census = {
        "surfaces": [
            _surface("workers/the-studio/requirements.txt", [_finding("pillow", classification)])
        ]
    }
    (item,) = plan(census)
    assert "pillow" in item.detail
    assert item.findings

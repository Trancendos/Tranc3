"""The PID key must join the CMDB to the registry, and must not guess.

The value of a key is that it makes free text checkable. These tests pin the
two halves of that: what the resolver may conclude, and what it must refuse to
conclude.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pid():
    spec = importlib.util.spec_from_file_location(
        "pid_coverage_under_test", REPO / "scripts" / "pid_coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


@pytest.fixture(scope="module")
def records(pid):
    return pid.resolve()


def test_the_inventory_is_clean_of_drift(records):
    """Nothing should still name a retired AI or an AI that does not lead its Location."""
    retired = [r["ServiceID"] for r in records if r["RetiredNameShouldBe"]]
    wrong = [r["ServiceID"] for r in records if r.get("Tier3AIShouldBe")]
    assert not retired, f"rows using a retired AI name: {retired}"
    assert not wrong, f"rows naming an AI that does not lead their Location: {wrong}"


def test_the_spark_belongs_to_the_spark(records):
    """The case that proved the basis ordering mattered.

    SRV-SPARK-001's recorded Tier3AI was Norman Hawkins, who leads The
    Observatory. Ranking that free text above the ID stem attached The Spark's
    own service to a different Location and left PID-SPK looking unrepresented.
    """
    spark = next(r for r in records if r["ServiceID"] == "SRV-SPARK-001")
    assert spark["PID"] == "PID-SPK"
    assert spark["Basis"] != "lead-ai-unique", "a drifted name must not decide ownership"


def test_every_assigned_pid_is_a_real_location(records, pid):
    from src.entities.platform import PLATFORM_ENTITIES

    known = {e.pid for e in PLATFORM_ENTITIES.values()}
    bogus = {r["PID"] for r in records if r["PID"]} - known
    assert not bogus, f"PIDs that match no Location: {sorted(bogus)}"


def test_every_assignment_records_its_basis(records):
    """An assignment nobody can audit is a guess wearing a key's clothes."""
    unexplained = [r["ServiceID"] for r in records if r["PID"] and r["Basis"] == "unresolved"]
    assert not unexplained


def test_unresolved_services_stay_visible_rather_than_guessed(records):
    """The discovery list is the deliverable, not an embarrassment to hide.

    If this ever reaches zero it should be because services were assigned an
    owner, not because the resolver got looser.
    """
    unresolved = [r for r in records if not r["PID"]]
    assert all(r["Basis"] == "unresolved" for r in unresolved)
    assert unresolved, (
        "no unresolved services at all -- verify that ownership was really "
        "assigned rather than the resolver being widened to guess"
    )


def test_the_resolver_refuses_an_ambiguous_lead_ai(pid):
    """Voxx leads five Locations, so his name alone cannot decide ownership."""
    _, by_lead = pid._registry_indexes()
    voxx = by_lead.get(pid._norm("Voxx"), [])
    assert len(voxx) > 1, "fixture assumption: Voxx must lead more than one Location"
    # The resolver only accepts lead-ai-unique when exactly one PID matches.
    ambiguous = [
        r
        for r in pid.resolve()
        if r["Basis"] == "lead-ai-unique" and r["RecordedTier3AI"].strip() == "Voxx"
    ]
    assert not ambiguous, "an AI leading several Locations must not resolve by name alone"

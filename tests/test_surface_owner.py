"""Tests for src/dvms/surface_owner.py and the ownership gate.

Each case below was calibrated by breaking the behaviour it names and
confirming the test fails. The property the whole module exists to protect is
in `test_an_unknown_surface_is_unmapped_not_guessed`: a finding routed to the
wrong Location is worse than one routed nowhere, because the wrong Location
closes it as not-mine and the right one never hears about it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from src.dvms.surface_owner import (
    DECLARED_OWNERS,
    DEFAULT_STEWARD,
    resolve_surface,
    unresolved_surfaces,
)
from src.entities.platform import PLATFORM_ENTITIES

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_surface_ownership.py"


def _gate():
    spec = importlib.util.spec_from_file_location("_surface_gate", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_surface_gate"] = module
    spec.loader.exec_module(module)
    return module


def test_a_surface_inside_a_locations_declared_path_is_owned():
    """Ladder 1: `LocationEntity.worker_path` is the Location's own claim."""
    owner = resolve_surface("workers/the-studio/requirements.txt")
    assert owner.kind == "location"
    assert owner.location == "The Studio"
    assert owner.resolved_by == "worker_path"


def test_a_locations_second_directory_resolves_to_the_same_location():
    """The Lab is `workers/the-lab/` AND `workers/lab-service/`.

    Only one directory fits in `worker_path`, so a Location with two of them is
    invisible to ladder 1 — and `lab-service` is The Lab's extended service
    layer, not an unowned tree.
    """
    primary = resolve_surface("workers/the-lab/requirements.txt")
    extended = resolve_surface("workers/lab-service/requirements-worker.txt")
    assert primary.location == extended.location == "The Lab"


def test_an_unknown_surface_is_unmapped_not_guessed():
    """The property the module exists to protect.

    Nothing about `workers/not-a-real-worker/` says who owns it, and the
    nearest-match answer would be a wrong owner rather than no owner.
    """
    owner = resolve_surface("workers/not-a-real-worker/requirements.txt")
    assert owner.kind == "unmapped"
    assert owner.location is None


def test_an_unmapped_surface_does_not_inherit_the_default_steward():
    """Otherwise a routing gap reports as routed.

    `responsible` falls back to the steward so a shared surface still has
    somebody who acts. Applying that fallback to an unmapped surface would make
    it indistinguishable from a stewarded one in every roll-up built on this.
    """
    assert resolve_surface("workers/not-a-real-worker/x").responsible is None
    assert resolve_surface("workers/geo-service/x").responsible == DEFAULT_STEWARD


def test_a_cross_cutting_surface_is_shared_and_still_routed():
    """`shared` is an answer, not a failure.

    The rate limiter sits in front of every worker and belongs to no single
    Location — `src/cmdb/identity.py` takes the same position, returning a null
    PID rather than putting a wrong owner on every incident. It still needs
    somebody to act, so it carries a steward.
    """
    owner = resolve_surface("workers/rate-limit-service/requirements-worker.txt")
    assert owner.kind == "shared"
    assert owner.location is None
    assert owner.responsible == DEFAULT_STEWARD


def test_the_repository_root_is_matched_exactly_not_as_a_prefix():
    """`.` as a prefix would cover the entire tree.

    It is the npm root's own surface. Treated as a prefix it silently claims
    every path no other rule reached, which is exactly the guessing this module
    refuses to do — and it would make `unmapped` unreachable, so the ownership
    gate could never fire again.
    """
    assert resolve_surface(".").kind == "shared"
    assert resolve_surface("workers/not-a-real-worker/x").kind == "unmapped"


def test_a_trailing_slash_or_backslash_resolves_the_same_way():
    """Census surfaces are directories for npm and files for pip."""
    assert resolve_surface("workers/the-studio/").location == "The Studio"
    assert resolve_surface("workers\\the-studio\\requirements.txt").location == "The Studio"


def test_every_declared_owner_names_a_real_location():
    """A typo here routes findings to a Location that cannot receive them."""
    for prefix, (location, _reason) in DECLARED_OWNERS.items():
        if location is not None:
            assert location in PLATFORM_ENTITIES, f"{prefix} -> {location}"


def test_every_declared_owner_carries_a_reason():
    """A mapping without a reason is indistinguishable from a guess later."""
    for prefix, (_location, reason) in DECLARED_OWNERS.items():
        assert reason.strip(), prefix


def test_every_declared_prefix_still_exists_on_disk():
    """A prefix matching nothing is a claim about a path that moved."""
    for prefix in DECLARED_OWNERS:
        if prefix == ".":
            continue
        assert (REPO_ROOT / prefix).exists(), prefix


def test_unresolved_surfaces_reports_only_the_gaps():
    surfaces = [
        "workers/the-studio/requirements.txt",
        "workers/rate-limit-service/requirements-worker.txt",
        "workers/not-a-real-worker/requirements.txt",
    ]
    gaps = unresolved_surfaces(surfaces)
    assert [gap.surface for gap in gaps] == ["workers/not-a-real-worker/requirements.txt"]


def test_the_real_estate_has_no_unowned_surface():
    """The estate's own manifests, not a synthetic stand-in."""
    module = _gate()
    assert module.main([]) == 0


def test_the_gate_reports_an_unowned_surface(monkeypatch, capsys):
    """Calibration: the gate must fail when a surface has no owner.

    A gate that only ever passes proves nothing about the day someone adds a
    worker tree and forgets to say who owns it.
    """
    module = _gate()
    monkeypatch.setattr(
        module, "scanned_surfaces", lambda: ["workers/not-a-real-worker/requirements.txt"]
    )
    assert module.main([]) == 1
    assert "has no owner" in capsys.readouterr().err


def test_the_gate_reports_a_stale_declaration(monkeypatch, capsys):
    """A mapping left behind when the tree moved is a rotting join."""
    module = _gate()
    monkeypatch.setitem(module.DECLARED_OWNERS, "workers/gone-away", (None, "a reason"))
    assert module.main([]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_the_gate_reports_a_location_that_does_not_exist(monkeypatch, capsys):
    module = _gate()
    monkeypatch.setitem(
        module.DECLARED_OWNERS, "workers/the-lab", ("The Labb", "a typo in the name")
    )
    assert module.main([]) == 1
    assert "not one of the 43 Locations" in capsys.readouterr().err


@pytest.mark.parametrize("surface", ["requirements.txt", "tranc3-bots/requirements.txt"])
def test_the_shared_backend_manifests_are_not_claimed_by_a_location(surface):
    """The FastAPI backend is shared by every in-process router.

    Assigning it to one Location would put every dependency in the estate's
    largest manifest on a Location that owns a fraction of it.
    """
    assert resolve_surface(surface).kind == "shared"

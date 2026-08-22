"""The registry conformance guard is a control, so it is tested like one.

On 2026-08-22 the entity registry described an architecture that had been
superseded: fifteen Locations pointed at a `src/` router `api.py` does not
mount, `src/academy/` did not exist at all, six Locations shared the single
path `src/studio/`, and 27 of 43 carried no `worker_port`. Nothing reported
it, because the thing that would have reported it did not exist.

These tests protect the two properties that make the guard worth having: that
it still finds nothing, and that the exemption list stays small and reasoned.
An allowlist is the natural place for this kind of drift to hide -- a guard
with a growing set of exceptions eventually forgives the whole estate.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from entity_registry_conformance import (  # noqa: E402
    NON_WORKER_LOCATIONS,
    collect_violations,
    load_baseline,
)


def test_registry_has_no_violations():
    """The repair is complete, and stays complete."""
    violations = collect_violations()
    assert violations == [], "entity registry drifted again: " + "; ".join(
        f"{v['rule']} {v['location']}" for v in violations
    )


def test_baseline_is_empty():
    """The baseline exists to be emptied, not to be lived in.

    It was never populated -- the repair landed in the same change as the
    guard -- so a non-empty baseline means someone accepted new drift rather
    than fixing it.
    """
    assert load_baseline() == set(), (
        "violations were baselined instead of repaired; "
        "the baseline is a migration aid, not a permanent waiver"
    )


def test_every_exemption_carries_a_reason():
    """A bare PID in the allowlist tells a future reader nothing."""
    for pid, reason in NON_WORKER_LOCATIONS.items():
        assert reason and len(reason) > 20, f"{pid} needs a real justification"


def test_exemptions_stay_bounded():
    """Four Locations are genuinely not workers. A fifth needs a conversation.

    Arcadia (web/), The Workshop (Forgejo), The Chaos Party (tests/) and
    The Citadel (deploy/) are not FastAPI services, so asking "is it mounted
    or backed by workers/" is the wrong question. If this ever needs to grow,
    that should be a deliberate decision rather than a quiet append.
    """
    assert len(NON_WORKER_LOCATIONS) == 4, (
        f"exemption list changed to {sorted(NON_WORKER_LOCATIONS)}; "
        f"widening it weakens the guard -- confirm this is intended"
    )


def test_the_guard_can_actually_fail():
    """The test that keeps the other four honest.

    Every assertion above expects an empty result. If `collect_violations`
    broke -- a path constant that stopped resolving, a rule that silently
    stopped firing -- all four would still pass, and the guard would be inert
    while reporting success. That is precisely the failure this module was
    written to remove, so it is worth proving the guard detects drift and not
    merely that it reports none.
    """
    import entity_registry_conformance as guard

    entity = next(iter(guard.PLATFORM_ENTITIES.values()))
    original = entity.worker_path
    try:
        object.__setattr__(entity, "worker_path", "src/does_not_exist_9f3a/")
        rules = {v["rule"] for v in guard.collect_violations()}
        assert "path-missing" in rules, (
            "the guard did not report a worker_path that does not exist; "
            "it is no longer detecting the drift it was built for"
        )
    finally:
        object.__setattr__(entity, "worker_path", original)

    assert collect_violations() == [], "the probe leaked state into the registry"


def test_a_port_in_an_image_tag_is_not_a_routed_port():
    """Ports must come from where compose routes them, not from anywhere.

    The first version of this check asked `str(port) in compose`, and the
    second anchored on non-digit boundaries. Both still matched a port sitting
    in an image tag, a digest, or an unrelated numeric field -- so
    `port-unrouted` could pass for a port compose never routes. A guard built
    to catch checks that answer confidently and wrongly must not be one.
    """
    import entity_registry_conformance as guard

    compose = """
services:
  decoy:
    image: registry.example/thing:8069
    environment:
      SOME_TIMEOUT: 8055
  real:
    image: registry.example/other:latest
    ports:
      - "8074:8074"
    labels:
      - traefik.http.services.x.loadbalancer.server.port=8060
  enved:
    image: registry.example/third:latest
    environment:
      PORT: 8077
"""
    routed = guard._routed_ports(compose)

    assert 8074 in routed, "a published ports: mapping is a routed port"
    assert 8060 in routed, "a Traefik loadbalancer port label is a routed port"
    assert 8077 in routed, "a PORT environment value is a routed port"
    assert 8069 not in routed, "an image tag is not a port mapping"
    assert 8055 not in routed, "an unrelated numeric env value is not a port"


def test_routed_ports_survives_unparseable_compose():
    """A broken compose file must not crash the gate that reads it."""
    import entity_registry_conformance as guard

    assert guard._routed_ports("{[not: valid: yaml") == set()
    assert guard._routed_ports("") == set()

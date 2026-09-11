"""Calibration for the deployed-route check.

The check exists because the first version of `src/creative/routing.py` was
wrong in a way that no test caught: several creative Locations ship two
FastAPI applications, and it read the richer `worker.py` rather than the
module each Dockerfile `CMD` actually runs. Warp Radio was marked ROUTED at
`POST /playlists` while its deployed image served no POST at all.

So these tests are mostly about the parser being able to tell the difference.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.check_creative_routes import (  # noqa: E402
    _FAN_OUT_DIRS,
    _fan_out_legs,
    _path_matches,
    entrypoint_for,
    main,
    routes_of,
)


class TestTheCheckPasses:
    def test_every_declared_endpoint_is_served_by_its_deployed_entrypoint(self):
        """The gate itself. A path added to the table must exist in the image."""
        assert main() == 0


class TestEntrypointResolution:
    @pytest.mark.parametrize(
        ("worker", "expected"),
        [
            ("imaginarium", "worker.py"),
            ("the-studio", "worker.py"),
            ("tateking", "main.py"),
            ("warp-radio", "main.py"),
            ("sashas-photo-studio", "main.py"),
        ],
    )
    def test_the_cmd_decides_which_module_runs(self, worker, expected):
        """Calibrated: preferring worker.py by name fails this.

        Picking the larger or more interesting file is exactly the mistake
        the route table made. Only the CMD knows.
        """
        module, why = entrypoint_for(REPO / "workers" / worker)
        assert module is not None, why
        assert module.name == expected

    def test_a_uvicorn_cmd_resolves_its_module(self):
        """Calibrated: handling only `python x.py` fails this.

        TranceFlow's CMD is `uvicorn main:app`, and treating that as
        unresolvable would make its route UNVERIFIABLE rather than checked.
        """
        module, why = entrypoint_for(REPO / "workers" / "tranceflow")
        assert module is not None, why
        assert module.name == "main.py"

    def test_a_directory_with_no_dockerfile_is_unresolvable_not_assumed(self, tmp_path):
        """Calibrated: falling back to main.py fails this.

        An unverifiable claim is the thing this check exists to stop, so it
        must not be resolved by guessing.
        """
        module, why = entrypoint_for(tmp_path)
        assert module is None
        assert "no Dockerfile" in why


class TestRouteCollection:
    def test_a_router_factory_in_a_sibling_module_is_followed(self):
        """Calibrated: parsing only the entrypoint fails this.

        TranceFlow's deployed main.py builds its app from
        router._make_tranceflow_router. A checker that stopped at the
        entrypoint would find a health route and call every real endpoint
        missing.
        """
        module, _ = entrypoint_for(REPO / "workers" / "tranceflow")
        found = routes_of(module)
        assert ("POST", "/tranceflow/projects") in found

    def test_the_router_prefix_is_applied(self):
        """Calibrated: ignoring APIRouter(prefix=...) fails this.

        Without the prefix the path reads /projects, which is a different
        route on a different Location.
        """
        module, _ = entrypoint_for(REPO / "workers" / "tranceflow")
        assert ("POST", "/projects") not in routes_of(module)

    def test_warp_radio_really_serves_no_post(self):
        """The measurement behind music.create being ABSENT."""
        module, _ = entrypoint_for(REPO / "workers" / "warp-radio")
        assert [p for m, p in routes_of(module) if m == "POST"] == []

    def test_imaginarium_now_ships_the_fan_out(self):
        """Calibrated: reverting the Dockerfile to main.py fails this.

        Before this change the image copied and ran a 92-line stub whose only
        POST answered "Orchestration not yet ready", so the fan-out — tested,
        reviewed and committed — never executed.
        """
        module, _ = entrypoint_for(REPO / "workers" / "imaginarium")
        assert module.name == "worker.py"
        assert ("POST", "/create") in routes_of(module)

    def test_the_dockerfile_copies_the_module_it_runs(self):
        """Calibrated: changing only CMD and not COPY fails this.

        The old Dockerfile copied main.py alone, so worker.py was not merely
        unrun — it was not in the image at all.
        """
        dockerfile = (REPO / "workers" / "imaginarium" / "Dockerfile").read_text()
        assert "COPY worker.py ." in dockerfile
        assert "COPY main.py ." not in dockerfile


class TestFanOutLegs:
    def test_the_legs_are_readable_without_importing_the_worker(self):
        """The worker raises at import without INTERNAL_SECRET, by design."""
        legs = _fan_out_legs()
        assert len(legs) >= 5
        assert {"key", "service", "path"} <= set(legs[0])

    def test_every_leg_names_a_known_service_directory(self):
        """Calibrated: adding a leg with an unmapped service key fails this."""
        for leg in _fan_out_legs():
            assert leg["service"] in _FAN_OUT_DIRS, leg

    def test_no_leg_targets_warp_radio(self):
        """Its deployed image has no POST, so a leg would fail on every brief."""
        assert all(leg["service"] != "warp_radio" for leg in _fan_out_legs())


class TestPathMatching:
    def test_a_path_parameter_matches_a_concrete_segment(self):
        assert _path_matches("/photo/status/{job_id}", "/photo/status/abc")

    def test_a_different_path_does_not_match(self):
        assert not _path_matches("/photo/generate", "/photo/upscale")

    def test_a_parameter_does_not_match_across_a_separator(self):
        """Calibrated: using `.*` instead of `[^/]+` fails this.

        A greedy wildcard would let /a/{x} satisfy a claim to /a/b/c, which
        is a different endpoint.
        """
        assert not _path_matches("/a/{x}", "/a/b/c")

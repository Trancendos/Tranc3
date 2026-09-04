"""Calibration for the creative route table.

Each test below was calibrated by mutating the thing it claims to protect and
confirming the test fails, then restoring. Where a property is defended by
more than one mechanism and no single mutation breaks it, the docstring says
so rather than implying a stronger guarantee than the test gives.
"""

from __future__ import annotations

import pytest

from src.creative import routing
from src.creative.routing import (
    CAPABILITIES,
    Capability,
    RouteStatus,
    capability,
    endpoint_for,
    gaps,
    resolve,
)


class TestTheNearMiss:
    """An edit must never be answered by a generator."""

    def test_editing_an_image_does_not_reach_the_generator(self):
        """Sharing the noun "image" is not sharing an intent.

        The generator would answer 200 with an unrelated new picture, which
        reads as success everywhere downstream.

        Redundantly defended, and the docstring says so rather than
        overclaiming: "edit this image" is one of image.edit's phrases, so
        the phrase weight alone decides it and adding "edit" to
        image.create's verbs does *not* fail this case. The phrase-free case
        below is the one the verb exclusion actually carries, and it is
        calibrated against that mutation.
        """
        res = resolve("edit this image")
        assert res.capability is not None
        assert res.capability.id == "image.edit"
        assert res.capability.status is RouteStatus.ABSENT

    def test_editing_without_a_registered_phrase_still_avoids_the_generator(self):
        """Calibrated: adding "edit" to image.create's verbs fails this.

        No phrase covers "edit the artwork", so the verbs are the whole
        defence. With "edit" shared, the two capabilities tie inside one
        Location and the request is refused instead of answered.
        """
        res = resolve("edit the artwork")
        assert res.capability is not None
        assert res.capability.id == "image.edit"

    def test_generating_an_image_still_reaches_the_generator(self):
        """The baseline the mutation above must not be allowed to break."""
        res = resolve("generate an image of a lighthouse")
        assert res.capability is not None
        assert res.capability.id == "image.create"

    def test_a_verb_alone_is_not_a_route(self):
        """Calibrated: dropping the `and` in score()'s candidate test fails this.

        "create" appears in seven capabilities. Without the noun requirement
        every one of them becomes a candidate and the winner is whichever
        happens to carry the most verbs.
        """
        res = resolve("create")
        assert res.capability is None
        assert "no capability matches" in res.reason

    def test_a_noun_alone_is_not_a_route(self):
        """Calibrated the same way, and the reason matters as much as the outcome.

        Under the OR mutation "image" still returns no capability — but
        because three image capabilities tie and one is unimplemented, not
        because nothing matched. Asserting only `capability is None` would
        pass under the mutation it exists to catch.
        """
        res = resolve("image")
        assert res.capability is None
        assert "no capability matches" in res.reason


class TestAbsenceIsAnAnswer:
    def test_an_unmatched_request_routes_nowhere(self):
        """Calibrated: falling back to the orchestrator fails this."""
        res = resolve("what is the weather in Glasgow")
        assert res.capability is None
        assert "no capability matches" in res.reason

    @pytest.mark.parametrize(
        ("request_text", "expected"),
        [
            ("edit this image", "image.edit"),
            ("upscale this image", "image.upscale"),
            ("audit the accessibility of this screen", "design.accessibility"),
            ("provide a component library", "design.component"),
        ],
    )
    def test_unimplemented_capabilities_resolve_to_themselves(self, request_text, expected):
        """An absent capability is named, not silently replaced.

        Calibrated on design.component: routing "provide a component library"
        to design.create instead makes this fail. That substitution is the
        realistic one — both live in Fabulousa — and it would answer a
        request for widgets with an empty Penpot file.
        """
        res = resolve(request_text)
        assert res.capability is not None
        assert res.capability.id == expected
        assert res.capability.status is RouteStatus.ABSENT
        assert not res.capability.servable


class TestTies:
    def test_a_multi_discipline_tie_escalates_to_the_orchestrator(self):
        """Calibrated: refusing every tie fails this.

        Two Locations tie and both can serve, which is what Imaginarium
        exists for.
        """
        res = resolve("produce a video and a picture")
        assert res.capability is not None
        assert res.capability.id == "creative.brief"
        assert {c.location for c in res.candidates} == {"Sashas Photo Studio", "TateKing"}

    def test_a_tie_touching_an_unimplemented_capability_is_refused(self):
        """Calibrated: escalating before the ABSENT check fails this.

        Imaginarium cannot fan out to a capability that does not exist, so
        escalating here would put an orchestrator in front of a gap and
        report progress.
        """
        res = resolve("create a widget and a playlist")
        assert res.capability is None
        assert "design.component" in res.reason

    def test_a_tie_inside_one_location_is_refused(self, monkeypatch):
        """Calibrated: dropping the distinct-location check fails this.

        The registry is patched rather than phrased around, and the reason is
        worth recording. No Location in the real table currently holds two
        *servable* capabilities — every Location has exactly one, with its
        siblings ABSENT — so every within-Location tie today is caught by the
        earlier unimplemented-candidate branch instead. An earlier version of
        this test used a real request and claimed calibration it could not
        deliver: the request had a single winner, and the mutation changed
        nothing.

        The branch is still correct and still worth keeping, because
        escalating a within-Location ambiguity to Imaginarium would send the
        request straight back to the Location that could not decide. So it is
        exercised against a registry that can reach it.
        """
        twins = tuple(
            Capability(
                id=f"studio.thing{n}",
                location="Sashas Photo Studio",
                delivers="A thing.",
                status=RouteStatus.ROUTED,
                verbs=("make",),
                nouns=("thing",),
            )
            for n in (1, 2)
        )
        monkeypatch.setattr(routing, "CAPABILITIES", twins)
        res = routing.resolve("make a thing")
        assert res.capability is None
        assert "ambiguous within Sashas Photo Studio" in res.reason


class TestTheRegistryTellsTheTruth:
    def test_every_addressable_capability_carries_its_address(self):
        """Calibrated: blanking any url_env on a capability with a path fails this."""
        for cap in CAPABILITIES:
            if cap.path:
                assert cap.method, cap.id
                assert cap.url_env, cap.id
                assert cap.default_url.startswith("http"), cap.id

    def test_every_capability_that_cannot_deliver_says_why(self):
        """Calibrated: blanking any DEGRADED capability's gap fails this.

        A status without a reason is a label. The gap text is the part a
        reader can act on.
        """
        for cap in gaps():
            assert cap.gap.strip(), f"{cap.id} is {cap.status.value} with no stated gap"

    def test_a_routed_capability_claims_no_gap(self):
        """Calibrated: marking code.generate ROUTED while keeping a gap fails this."""
        for cap in CAPABILITIES:
            if cap.status is RouteStatus.ROUTED:
                assert not cap.gap, f"{cap.id} is ROUTED but states a gap"

    def test_capability_ids_are_unique(self):
        ids = [c.id for c in CAPABILITIES]
        assert len(ids) == len(set(ids))

    def test_lookup_returns_none_for_an_unknown_id(self):
        assert capability("image.teleport") is None


class TestEndpointResolution:
    def test_the_environment_overrides_the_compose_default(self, monkeypatch):
        """Calibrated: reading default_url unconditionally fails this.

        A deployment that moves a worker must not be routed to the address
        this table was written against.
        """
        cap = capability("game.create")
        assert cap is not None
        monkeypatch.setenv(cap.url_env, "http://tranceflow.internal:9999/")
        assert endpoint_for(cap) == "http://tranceflow.internal:9999/tranceflow/projects"

    def test_a_capability_with_no_endpoint_has_no_address(self):
        """Calibrated: returning the bare base URL fails this.

        image.edit has no path. Handing back the Photo Studio's base URL
        would give a caller something POSTable that answers 404 or, worse,
        matches a different route.
        """
        cap = capability("image.edit")
        assert cap is not None
        assert endpoint_for(cap) is None

    def test_the_default_is_used_when_the_environment_is_silent(self, monkeypatch):
        cap = capability("game.create")
        assert cap is not None
        monkeypatch.delenv(cap.url_env, raising=False)
        assert endpoint_for(cap) == "http://tranceflow:8059/tranceflow/projects"


class TestTheMeasuredGaps:
    """These assert the state of the estate, so a fix has to update them."""

    def test_the_orchestrators_remaining_gap_is_its_dependencies_not_its_wiring(self):
        """The fan-out was fixed in this change; the table has to say so.

        It named TranceFlow as unreached. It is reached now, so the gap that
        survives is the one nobody has fixed: the engines and encoders the
        creative Locations wrap are not services in the stack.
        """
        cap = capability("creative.brief")
        assert cap is not None
        assert "Godot" in cap.gap
        assert "never called" not in cap.gap

    def test_fabulousa_is_recorded_as_reachable_but_unauthenticated(self):
        """Also updated by this change: the address was wrong, now the token is missing.

        Both are DEGRADED, and conflating them would lose the fact that one
        was a compose defect and the other needs a secret issuing.
        """
        cap = capability("design.create")
        assert cap is not None
        assert "PENPOT_TOKEN" in cap.gap

    def test_the_orchestrator_constant_points_at_a_real_capability(self):
        """Calibrated: pointing _ORCHESTRATOR at a removed id fails at import."""
        assert routing._ORCHESTRATOR.id == "creative.brief"
        assert routing._ORCHESTRATOR in CAPABILITIES


class TestTheHttpSurface:
    """The route table has to be reachable, not just importable."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.creative.routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_an_unroutable_request_is_a_200_not_a_404(self, client):
        """Calibrated: raising 404 for an unmatched request fails this.

        "Nothing in this estate does that" is a fact about the estate. A 404
        says the caller asked wrongly, which sends them off to fix a request
        that was fine.
        """
        r = client.post("/creative/resolve", json={"request": "book me a flight"})
        assert r.status_code == 200
        assert r.json()["routed"] is False
        assert r.json()["capability"] is None

    def test_a_resolved_request_carries_its_endpoint(self, client):
        r = client.post("/creative/resolve", json={"request": "create a game"})
        body = r.json()
        assert body["routed"] is True
        assert body["capability"]["location"] == "TranceFlow"
        assert body["url"].endswith("/tranceflow/projects")

    def test_an_absent_capability_is_named_with_its_status(self, client):
        """Calibrated: dropping `deliverable` from the payload fails this.

        A caller that sees only `routed: true` would treat an unimplemented
        capability as a working route.
        """
        r = client.post("/creative/resolve", json={"request": "edit this image"})
        body = r.json()
        # Named, but not routed. The capability says which Location owns the
        # gap; `routed` answers whether anything can serve it, and answering
        # yes here would let a caller treat unimplemented work as dispatchable.
        assert body["capability"]["id"] == "image.edit"
        assert body["routed"] is False
        assert body["deliverable"] == "absent"
        assert body["url"] is None

    def test_an_empty_request_is_rejected(self, client):
        assert client.post("/creative/resolve", json={"request": "   "}).status_code == 400

    def test_gaps_separates_absent_from_degraded(self, client):
        """Calibrated: summing both into one count fails this.

        An ABSENT capability needs building; a DEGRADED one needs a
        dependency stood up. One number would not tell an operator which
        pile they are looking at.
        """
        body = client.get("/creative/gaps").json()
        assert body["absent"] > 0
        assert body["degraded"] > 0
        assert body["absent"] + body["degraded"] == body["count"]

    def test_an_unknown_status_filter_is_rejected_with_the_valid_ones(self, client):
        r = client.get("/creative/capabilities", params={"status": "broken"})
        assert r.status_code == 400
        assert "routed" in r.json()["detail"]

    def test_an_unknown_capability_is_a_404(self, client):
        assert client.get("/creative/capabilities/image.teleport").status_code == 404


class TestCommission:
    """A creative request that opens a Town Hall deliverable rather than bypassing it."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from auth import get_current_user
        from src.creative.routes import router
        from src.townhall import plm as plm_module

        service = plm_module.PlmService(db_path=tmp_path / "plm.db")
        monkeypatch.setattr(plm_module, "_service", service)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {"username": "lilli-sc"}
        yield TestClient(app)
        service.close()

    def test_commission_requires_authentication(self, tmp_path, monkeypatch):
        """Calibrated: dropping the Depends(get_current_user) fails this.

        A durable write with no identity lets anyone fill the register, and
        the register's value is being able to say who asked.

        REQUIRE_AUTH is pinned to true rather than inherited: with it false
        the auth facade returns an anonymous user and this test passes for a
        reason that has nothing to do with the route. A test that flips
        meaning with an environment variable proves whatever the environment
        happens to be.
        """
        monkeypatch.setenv("REQUIRE_AUTH", "true")

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.creative.routes import router
        from src.townhall import plm as plm_module

        service = plm_module.PlmService(db_path=tmp_path / "plm.db")
        monkeypatch.setattr(plm_module, "_service", service)
        app = FastAPI()
        app.include_router(router)
        try:
            unauthenticated = TestClient(app)
            r = unauthenticated.post("/creative/commission", json={"request": "create a game"})
            assert r.status_code in (401, 403), r.status_code
            assert plm_module.get_plm().list_deliverables() == []
        finally:
            service.close()

    def test_the_requester_comes_from_the_token_not_the_body(self, client):
        """Calibrated: reading requested_by from the body fails this.

        An attribution the caller supplies is one anyone can forge.
        """
        body = client.post(
            "/creative/commission",
            json={"request": "create a game", "requested_by": "someone-else"},
        ).json()
        assert body["deliverable"]["requested_by"] == "lilli-sc"

    def test_an_unimplemented_capability_is_not_commissioned(self, client):
        """Calibrated: checking only `capability is None` fails this.

        `resolve` returns a Capability for an ABSENT one — that is how the
        gap gets named — so the None check alone lets image.edit open a
        deliverable whose gate no Location can ever evidence.
        """
        from src.townhall.plm import get_plm

        r = client.post("/creative/commission", json={"request": "edit this image"})
        assert r.status_code == 422
        assert r.json()["detail"]["capability"] == "image.edit"
        assert get_plm().list_deliverables() == []

    def test_a_game_request_opens_a_gated_deliverable(self, client):
        """Calibrated: returning the resolution without creating a deliverable fails this.

        This is the brief in one test: work goes *through* the lifecycle. A
        resolve-only answer lets a caller read the address and then call the
        worker directly, which is the state the estate was already in.
        """
        r = client.post("/creative/commission", json={"request": "create a game"})
        assert r.status_code == 201
        body = r.json()
        assert body["deliverable"]["kind"] == "game"
        assert body["deliverable"]["location"] == "TranceFlow"
        assert body["deliverable"]["stage"] == "concept"
        assert body["gate"]["can_advance"] is False
        assert body["gate"]["unmet"] == ["concept.business-case"]

    def test_an_unroutable_request_opens_nothing(self, client):
        """Calibrated: creating a deliverable before the None check fails this.

        A deliverable naming no Location would sit in the register blocked
        forever at a gate nobody can evidence, which reads as governance and
        is a leak.
        """
        from src.townhall.plm import get_plm

        r = client.post("/creative/commission", json={"request": "book me a flight"})
        assert r.status_code == 422
        assert get_plm().list_deliverables() == []

    def test_the_kind_follows_the_capability_not_the_location(self, client):
        """Calibrated: mapping kind by Location fails this.

        Sashas Photo Studio only ever makes images, but Fabulousa produces
        both design systems and templates, and The Lab produces both
        applications and modules. A Location-keyed map would gate them
        identically.
        """
        game = client.post("/creative/commission", json={"request": "create a game"}).json()
        app = client.post("/creative/commission", json={"request": "build an app"}).json()
        assert game["deliverable"]["kind"] == "game"
        assert app["deliverable"]["kind"] == "application"

    def test_commissioning_a_degraded_capability_says_so(self, client):
        """Calibrated: dropping deliverable_status from the payload fails this.

        The lifecycle would stop this at the build gate eventually. Saying it
        at commission time costs nothing and saves the round trip.
        """
        body = client.post("/creative/commission", json={"request": "create a game"}).json()
        assert body["deliverable_status"] == "degraded"
        assert "Godot" in body["gap"]

    def test_every_capability_has_a_deliverable_kind(self, client):
        """Calibrated: removing any entry from _DELIVERABLE_KIND fails this.

        An unmapped capability would resolve, pass every check, and then 500
        at the last step — after the caller had been told their request was
        routable.
        """
        from src.creative.routes import _DELIVERABLE_KIND
        from src.townhall.plm import DeliverableKind

        for cap in CAPABILITIES:
            assert cap.id in _DELIVERABLE_KIND, cap.id
            DeliverableKind(_DELIVERABLE_KIND[cap.id])  # raises on a bad value

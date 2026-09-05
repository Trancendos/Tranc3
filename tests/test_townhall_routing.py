"""The Town Hall's backlog routing register — and what it refuses.

Every test here is calibrated: the comment on a refusal names the change that
makes it stop failing, because a refusal nobody can make fire is a refusal
nobody has checked.
"""

from __future__ import annotations

import pytest

from src.townhall.routing import (
    InvalidExport,
    RoutingRefused,
    RoutingRegistry,
    design_pack,
    load_decisions,
    pack_slug,
)


@pytest.fixture
def registry(tmp_path):
    return RoutingRegistry(tmp_path / "routing.db")


class TestARoutingDecisionIsRecorded:
    def test_a_decision_carries_its_authority_reason_and_design(self, registry):
        decision = registry.route(
            item_key="docs/compliance/ISO27001_SOA.md:24",
            location="Cryptex",
            reason="Information security roles sit with the cyber-defence Location.",
            authority="The Town Hall",
        )
        assert decision.location == "Cryptex"
        assert decision.authority == "The Town Hall"
        assert decision.design_pack == "docs/solution-packs/cryptex.md"

    def test_the_decision_is_readable_back(self, registry):
        registry.route("k", "The Lab", "code creation platform owns it", "The Town Hall")
        assert registry.decision("k").location == "The Lab"

    def test_an_unrouted_item_has_no_decision(self, registry):
        assert registry.decision("never-routed") is None


class TestWhatTheRegisterRefuses:
    def test_a_location_that_is_not_a_location(self, registry):
        """Calibrated: dropping the PLATFORM_ENTITIES membership test passes this.

        Routing to a name nobody runs is the CMDB defect one level up — a
        record pointing somewhere that does not exist.
        """
        with pytest.raises(RoutingRefused, match="not one of the"):
            registry.route("k", "The Ministry of Silly Walks", "seems right", "someone")

    def test_a_location_with_no_design_material(self, registry, monkeypatch):
        """Calibrated: dropping the design-pack test passes this.

        Routing work to a place with no architecture, journey or acceptance
        criteria is what leaving the item unrouted already says.
        """
        import src.townhall.routing as routing

        monkeypatch.setattr(routing, "design_pack", lambda _location: None)
        with pytest.raises(RoutingRefused, match="no solution pack"):
            registry.route("k", "Cryptex", "a reason", "The Town Hall")

    def test_a_decision_with_no_written_reason(self, registry):
        """Calibrated: making `reason` optional passes this."""
        with pytest.raises(ValueError, match="reason"):
            registry.route("k", "Cryptex", "   ", "The Town Hall")

    def test_a_decision_with_no_named_authority(self, registry):
        """Calibrated: defaulting `authority` passes this.

        A decision with no author is indistinguishable from a guess six
        months later, which is when somebody asks how it got there.
        """
        with pytest.raises(ValueError, match="authority"):
            registry.route("k", "Cryptex", "a reason", "  ")


class TestNothingIsOverwritten:
    def test_rerouting_supersedes_and_keeps_both(self, registry):
        first = registry.route("k", "The Lab", "built here", "The Town Hall")
        second = registry.route("k", "Cryptex", "threat intel, not code creation", "The Town Hall")
        assert second.supersedes == first.id
        assert [d.location for d in registry.history("k")] == ["The Lab", "Cryptex"]
        assert registry.decision("k").location == "Cryptex"


class TestTheExportIsWhatCiReads:
    def test_the_export_round_trips(self, registry, tmp_path):
        registry.route("a:1", "Cryptex", "because", "The Town Hall")
        registry.route("b:2", "The Lab", "because", "The Town Hall")
        path = registry.export(tmp_path / "backlog_routing.yaml")
        loaded = load_decisions(path)
        assert loaded["a:1"]["location"] == "Cryptex"
        assert loaded["b:2"]["reason"] == "because"

    def test_a_missing_export_is_no_decisions_not_an_error(self, tmp_path):
        """A fresh checkout has routed nothing; the backlog must still build."""
        assert load_decisions(tmp_path / "absent.yaml") == {}

    def test_the_export_is_stable_across_runs(self, registry, tmp_path):
        registry.route("b:2", "The Lab", "because", "The Town Hall")
        registry.route("a:1", "Cryptex", "because", "The Town Hall")
        first = registry.export(tmp_path / "one.yaml").read_text()
        second = registry.export(tmp_path / "two.yaml").read_text()
        assert first == second


class TestTheRegisterIsReachable:
    def test_the_routing_routes_are_mounted(self):
        """A register with no HTTP surface is a table nobody can decide through."""
        import api
        from tests.support.routes import mounted_paths

        paths = mounted_paths(api.app)
        assert "/townhall/routing/decisions" in paths
        assert "/townhall/routing/export" in paths


class TestTheBacklogReadsTheDecisions:
    def test_a_decision_overrides_a_name_mentioned_in_prose(self, registry, tmp_path, monkeypatch):
        """Calibrated: making the overlay skip rows that already name a
        Location fails this.

        A Location named inside a register row is a hint its author left. A
        Town Hall decision has an authority, a reason and a record, so where
        both exist the decision is the one that stands.
        """
        import scripts.build_action_backlog as backlog
        import src.townhall.routing as routing

        registry.route("reg.md:7", "Cryptex", "threat intel owns this", "The Town Hall")
        export = registry.export(tmp_path / "backlog_routing.yaml")
        monkeypatch.setattr(routing, "EXPORT", export)

        items = backlog._apply_routing(
            [
                {
                    "source": "reg.md",
                    "line": 7,
                    "action": "x",
                    "status": "Open",
                    "location": "The Lab",
                }
            ]
        )
        assert items[0]["location"] == "Cryptex"
        assert items[0]["routed_by"] == "The Town Hall"

    def test_the_real_sweep_applies_the_decisions(self, registry, tmp_path, monkeypatch):
        """Calibrated: dropping `_apply_routing` from `harvest` fails this.

        The unit test above proves the overlay works; this proves the sweep
        actually calls it, which is the half that a control existing and
        never being invoked keeps getting wrong in this estate.
        """
        import scripts.build_action_backlog as backlog
        import src.townhall.routing as routing

        unrouted = next(item for item in backlog.harvest() if not item["location"])
        key = f"{unrouted['source']}:{unrouted['line']}"
        registry.route(key, "Cryptex", "routed for this test", "The Town Hall")
        monkeypatch.setattr(routing, "EXPORT", registry.export(tmp_path / "backlog_routing.yaml"))

        swept = next(
            item for item in backlog.harvest() if f"{item['source']}:{item['line']}" == key
        )
        assert swept["location"] == "Cryptex"
        assert swept["routed_by"] == "The Town Hall"

    def test_an_item_with_no_decision_is_left_alone(self, tmp_path, monkeypatch):
        import scripts.build_action_backlog as backlog
        import src.townhall.routing as routing

        monkeypatch.setattr(routing, "EXPORT", tmp_path / "absent.yaml")
        items = backlog._apply_routing(
            [{"source": "reg.md", "line": 9, "action": "x", "status": "Open", "location": ""}]
        )
        assert items[0]["location"] == ""
        assert "routed_by" not in items[0]


class TestTheSlugAgreesWithTheBacklog:
    def test_every_location_pack_the_register_claims_exists(self):
        """The register decides a Location has design material and the backlog
        links to it, so the two must agree which file that is."""
        from src.entities.platform import PLATFORM_ENTITIES

        resolved = {name: design_pack(name) for name in PLATFORM_ENTITIES}
        missing = sorted(name for name, pack in resolved.items() if pack is None)
        assert missing == [], f"Locations with no solution pack: {missing}"

    def test_the_slug_matches_the_generators_own_function(self):
        """Calibrated: changing either implementation fails this.

        This used to re-implement the generator's regex inline and compare
        `pack_slug` against a copy of itself — always true, and blind to the
        exact drift it claimed to catch. It now calls the generator's own
        `_pack_slug`, so the two implementations are compared rather than
        one of them being compared with a transcription of the other.
        """
        from scripts.build_action_backlog import _pack_slug
        from src.entities.platform import PLATFORM_ENTITIES

        for name in PLATFORM_ENTITIES:
            assert pack_slug(name) == _pack_slug(name), name


class TestTheExportIsValidatedNotTrusted:
    """Everything `route()` refuses must be refused on the way back in.

    The export is a file in the repository. It can be hand-edited, merged
    badly, or left behind — and CI reads it and applies it to the backlog.
    Trusting it made every validation in `route()` optional in practice.
    Each of these is calibrated: with the validation removed, the malformed
    entry loads cleanly and the backlog carries it as if the Town Hall had
    decided it.
    """

    def _write(self, tmp_path, entry):
        import yaml

        path = tmp_path / "backlog_routing.yaml"
        path.write_text(yaml.safe_dump({"decisions": [entry]}), encoding="utf-8")
        return path

    def test_a_location_that_is_not_a_location_is_refused(self, tmp_path):
        path = self._write(
            tmp_path,
            {
                "item_key": "a:1",
                "location": "The Ministry of Silly Walks",
                "reason": "seems right",
                "authority": "someone",
            },
        )
        with pytest.raises(InvalidExport, match="not one of the"):
            load_decisions(path)

    @pytest.mark.parametrize("missing", ["item_key", "location", "reason", "authority"])
    def test_a_missing_or_blank_field_is_refused(self, tmp_path, missing):
        entry = {
            "item_key": "a:1",
            "location": "Cryptex",
            "reason": "because",
            "authority": "The Town Hall",
        }
        entry[missing] = "   "
        path = self._write(tmp_path, entry)
        with pytest.raises(InvalidExport, match=f"has no {missing}"):
            load_decisions(path)

    def test_a_design_pack_that_is_not_the_locations_is_refused(self, tmp_path):
        path = self._write(
            tmp_path,
            {
                "item_key": "a:1",
                "location": "Cryptex",
                "reason": "because",
                "authority": "The Town Hall",
                "design_pack": "docs/solution-packs/the-lab.md",
            },
        )
        with pytest.raises(InvalidExport, match="names design pack"):
            load_decisions(path)

    def test_one_item_routed_twice_is_refused(self, tmp_path):
        import yaml

        entry = {
            "item_key": "a:1",
            "location": "Cryptex",
            "reason": "because",
            "authority": "The Town Hall",
        }
        path = tmp_path / "backlog_routing.yaml"
        path.write_text(yaml.safe_dump({"decisions": [entry, dict(entry)]}), encoding="utf-8")
        with pytest.raises(InvalidExport, match="a second time"):
            load_decisions(path)

    def test_the_real_export_loads(self):
        """Whatever is committed must satisfy the same rules."""
        load_decisions()


class TestWritesAreGatedAndReadsAreNot:
    def test_the_post_endpoints_require_authentication(self):
        """Calibrated: removing the Depends fails this.

        A routing decision is durable, supersedes an earlier one, and
        changes a file CI reads. An anonymous caller must not make one.
        """
        import api
        from tests.support.routes import mounted_routes

        posts = [
            route
            for route in mounted_routes(api.app)
            if getattr(route, "path", "").startswith("/townhall/routing")
            and "POST" in getattr(route, "methods", set())
        ]
        assert {route.path for route in posts} == {
            "/townhall/routing/decisions",
            "/townhall/routing/export",
        }
        for route in posts:
            assert route.dependant.dependencies, f"{route.path} takes no authentication"

    def test_the_read_endpoints_stay_public(self):
        """A register nobody can read is a register nobody consults."""
        import api
        from tests.support.routes import mounted_routes

        gets = [
            route
            for route in mounted_routes(api.app)
            if getattr(route, "path", "").startswith("/townhall/routing")
            and "GET" in getattr(route, "methods", set())
        ]
        assert gets, "the routing register exposes no reads"
        for route in gets:
            assert not route.dependant.dependencies, f"{route.path} became gated"

    def test_a_null_reason_is_refused_by_the_request_model(self):
        """Calibrated: coercing with `str(...)` passes this.

        `str(None)` is `"None"` — non-empty, so the registry's own check
        accepted it and recorded a decision with no written reason.
        """
        import pydantic

        from src.townhall.routing_routes import RouteItemRequest

        with pytest.raises(pydantic.ValidationError):
            RouteItemRequest(
                item_key="a:1", location="Cryptex", reason=None, authority="The Town Hall"
            )
        with pytest.raises(pydantic.ValidationError):
            RouteItemRequest(item_key="a:1", location="Cryptex", reason="", authority="x")


class TestTheRegistrySingleton:
    def test_a_different_path_gets_a_different_registry(self, tmp_path):
        """Calibrated: a single global returns the first registry forever.

        `get_routing_registry(db_path=...)` silently ignored every later
        path, so a caller asking for a different database got the wrong one
        with no error to say so.
        """
        from src.townhall.routing import get_routing_registry

        first = get_routing_registry(tmp_path / "one.db")
        second = get_routing_registry(tmp_path / "two.db")
        assert first is not second
        assert get_routing_registry(tmp_path / "one.db") is first

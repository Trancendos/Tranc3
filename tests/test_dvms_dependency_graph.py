"""The reverse index: which Locations share a dependency, and what does one declare?

`surface_owner.py` answers "who owns this manifest". This is the other
direction, and it is the one the platform owner asked for by name: open a
Location's record, go to its dependencies, pick one, and see every other
service associated with it.

Two properties are load-bearing and everything here exists to hold them down:

  * A manifest whose Location could not be resolved must never be counted as
    zero exposure. `unrouted_manifests` is reported separately from `locations`
    precisely so a blast radius cannot quietly omit the services it failed to
    place.
  * An UNKNOWN package must not read as an UNAFFECTED one. `blast_radius` on a
    package nothing declares returns `known: False`, not an empty
    `locations: []`, because the second is indistinguishable from "safe".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dvms import dependency_graph as graph  # noqa: E402
from src.dvms.surface_owner import SurfaceOwner  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_cache():
    graph.reset_cache()
    yield
    graph.reset_cache()


def _owner(surface: str) -> SurfaceOwner:
    """A stand-in resolver: the first path segment names the Location.

    `workers/alpha/requirements.txt` -> "Alpha"; anything under `orphan/` is
    unmapped, which is how the unrouted path gets exercised without depending
    on the real estate having an unmapped surface in it.
    """
    parts = surface.strip("./").split("/")
    if parts and parts[0] == "orphan":
        return SurfaceOwner(surface=surface, kind="unmapped", steward="")
    name = parts[1].title() if len(parts) > 1 else (parts[0].title() if parts else "Root")
    return SurfaceOwner(surface=surface, kind="location", location=name)


@pytest.fixture()
def estate(tmp_path, monkeypatch):
    """A miniature estate: two workers sharing a package, plus an unrouted one."""

    def write(rel: str, text: str):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    write("workers/alpha/requirements.txt", "fastapi==0.115.0\nshared-lib>=1.0\n")
    write("workers/beta/requirements.txt", "shared-lib>=1.0\nlonely==2.0\n")
    write("orphan/requirements.txt", "shared-lib>=1.0\n")
    write(
        "web/package.json",
        json.dumps({"dependencies": {"react": "^18"}, "devDependencies": {"vite": "^5"}}),
    )

    monkeypatch.setattr(graph, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(graph, "resolve_surface", _owner)
    graph.reset_cache()
    return tmp_path


class TestManifestParsing:
    """What counts as a declared package, and what is a directive."""

    def test_a_requirements_directive_is_not_a_package(self, tmp_path):
        """`-r base.txt` and `-e .` start with a dash and name no package.

        Recorded as dependencies they would appear in the shared-package list
        as packages named `-r`, and every Location using a layered
        requirements file would look like it shared one.

        Three redundant mechanisms hold this — the leading-dash skip, the
        regex's `[A-Za-z0-9]` first character, and its requirement that a
        version specifier or end-of-line follow the name — so no single-
        mechanism mutation breaks this test. Measured: it fails only once the
        skip AND the regex shape are both gone. It pins the behaviour, not any
        one mechanism, which is the right contract for a property defended
        three times over.
        """
        manifest = tmp_path / "requirements.txt"
        manifest.write_text("-r base.txt\n-e .\nrequests==2.32.3\n", encoding="utf-8")
        assert graph._pip_packages(str(manifest)) == {"requests"}

    def test_extras_markers_and_comments_are_stripped(self, tmp_path):
        """`uvicorn[standard]` and `uvicorn` are one package, not two.

        Left unstripped, the same dependency in two Locations written two ways
        splits into two entries and neither looks shared.
        """
        manifest = tmp_path / "requirements.txt"
        manifest.write_text(
            "uvicorn[standard]==0.30.0\n"
            "httpx ; python_version >= '3.10'\n"
            "# a comment\n"
            "PyYAML>=6  # trailing comment\n",
            encoding="utf-8",
        )
        assert graph._pip_packages(str(manifest)) == {"uvicorn", "httpx", "pyyaml"}

    def test_an_unreadable_manifest_yields_nothing_rather_than_raising(self, tmp_path):
        """One bad file must not take down a whole-estate topology query."""
        assert graph._pip_packages(str(tmp_path / "absent.txt")) == set()

    def test_dev_dependencies_are_included(self, tmp_path):
        """Deliberate, and the reason is written into the module.

        A build-time package with a vulnerability still executes on a machine
        holding this estate's source and its tokens. Excluding devDependencies
        is how a supply-chain compromise gets classified out of scope, so the
        test asserts the dev entry is PRESENT — checking only `dependencies`
        would pass whichever way the code went.
        """
        manifest = tmp_path / "package.json"
        manifest.write_text(
            json.dumps({"dependencies": {"react": "^18"}, "devDependencies": {"vitest": "^2"}}),
            encoding="utf-8",
        )
        assert graph._npm_packages(str(manifest)) == {"react", "vitest"}

    def test_malformed_json_yields_nothing_rather_than_raising(self, tmp_path):
        manifest = tmp_path / "package.json"
        manifest.write_text("{not json", encoding="utf-8")
        assert graph._npm_packages(str(manifest)) == set()

    def test_a_submodule_manifest_is_excluded(self):
        """Submodules are separate repositories that audit themselves.

        A finding in `compliance/magna-carta` cannot be fixed by a change here,
        and counting its Locations would inflate every blast radius with
        services this repo does not deploy.
        """
        assert graph._excluded("compliance/magna-carta/requirements.txt")
        assert not graph._excluded("workers/the-lab/requirements.txt")


class TestReverseLookup:
    """dependency -> every Location associated with it."""

    def test_a_shared_package_names_every_location(self, estate):
        entry = graph.usage("shared-lib")
        assert entry is not None
        assert entry.locations == ["Alpha", "Beta"]
        assert entry.is_shared

    def test_a_single_location_package_is_not_shared(self, estate):
        entry = graph.usage("lonely")
        assert entry is not None
        assert entry.locations == ["Beta"]
        assert not entry.is_shared

    def test_an_unrouted_manifest_is_reported_and_never_counted_as_a_location(self, estate):
        """The fail-open this class exists for.

        `orphan/requirements.txt` also declares `shared-lib`. If an unresolved
        manifest were dropped silently the blast radius would read as complete
        while omitting a service; if it were folded into `locations` it would
        invent a Location name. It is reported as its own list instead.
        """
        entry = graph.usage("shared-lib")
        assert entry.unrouted_manifests == ["orphan/requirements.txt"]
        assert "orphan/requirements.txt" not in str(entry.locations)
        assert len(entry.locations) == 2

    def test_package_names_are_matched_case_insensitively(self, estate):
        """`PyYAML` in one manifest and `pyyaml` in another is one package."""
        assert graph.usage("SHARED-LIB") is not None

    def test_ecosystems_do_not_collide(self, estate):
        """A pip package and an npm package can share a name and are not the same.

        Keyed on the bare name, an npm advisory would be attributed to the
        Locations declaring the Python package of that name.
        """
        assert graph.usage("react", "npm") is not None
        assert graph.usage("react", "pip") is None


class TestForwardLookup:
    """Location -> what it declares. The other half of the owner's flow."""

    def test_a_location_lists_its_own_declarations(self, estate):
        assert graph.dependencies_of("Alpha") == {"pip": ["fastapi", "shared-lib"]}

    def test_a_location_that_declares_nothing_returns_empty(self, estate):
        assert graph.dependencies_of("Not A Location") == {}


class TestBlastRadius:
    """The question a Change record asks before an upgrade."""

    def test_an_undeclared_package_is_unknown_not_unaffected(self, estate):
        """An empty `locations` list reads as "safe". It is not the same claim.

        A typo'd package name returning `locations: []` with no other signal
        would let a reader conclude an advisory touches nothing here.
        """
        result = graph.blast_radius("never-heard-of-it")
        assert result["known"] is False
        assert "not declared" in result["reason"]

    def test_a_known_package_carries_the_declared_only_caveat(self, estate):
        """The graph is a lower bound and every result has to say so.

        The transitive closure is not resolved, so a package reaching a
        Location only through another package's dependencies is absent. A lower
        bound presented as a total gets trusted and then under-reports.
        """
        result = graph.blast_radius("shared-lib")
        assert result["known"] is True
        assert "lower bound" in result["note"]

    def test_shared_packages_are_ordered_widest_first(self, estate):
        """This ordering is the upgrade queue, so the order is the product.

        `shared-lib` (2 Locations) must precede `fastapi` (1) even though it
        sorts later alphabetically — comparing two names that agree under both
        orderings would prove nothing.
        """
        names = [e.package for e in graph.shared_packages(minimum=1)]
        assert names.index("shared-lib") < names.index("fastapi")

    def test_the_minimum_threshold_excludes_narrow_packages(self, estate):
        assert [e.package for e in graph.shared_packages(minimum=2)] == ["shared-lib"]

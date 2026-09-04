"""The CLI over the dependency graph — both directions plus the duplication read.

The interesting one is `--duplication`. It exists because a per-manifest
findings report counts one advisory in a package declared by 35 Locations as 35
findings, and a reader who takes that number as workload sees a queue thirty
times longer than it is. Both numbers are true; they answer different
questions. The arithmetic that separates them is therefore tested against a
constructed graph rather than the live estate, so the assertion is a number and
not whatever the repository happens to contain today.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.dvms.dependency_graph import PackageUsage  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location(
        "_dvms_topology", REPO_ROOT / "scripts" / "dvms_topology.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_dvms_topology"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cli():
    return _load()


@pytest.fixture()
def fake_graph(cli, monkeypatch):
    """Three packages with 3, 1 and 1 Locations: 5 pairs over 3 packages."""
    entries = {
        "pip:wide": PackageUsage(
            package="wide",
            ecosystem="pip",
            locations=["Cryptex", "The Lab", "The Studio"],
            manifests=["a/requirements.txt", "b/requirements.txt", "c/requirements.txt"],
        ),
        "pip:narrow": PackageUsage(
            package="narrow",
            ecosystem="pip",
            locations=["The Lab"],
            manifests=["b/requirements.txt"],
        ),
        "npm:front": PackageUsage(
            package="front",
            ecosystem="npm",
            locations=["Arcadia"],
            manifests=["web/package.json"],
        ),
    }
    monkeypatch.setattr(cli.graph, "build_graph", lambda: entries)
    monkeypatch.setattr(cli.graph, "usage", lambda name, eco="pip": entries.get(f"{eco}:{name}"))
    monkeypatch.setattr(
        cli.graph,
        "shared_packages",
        lambda minimum=2: sorted(
            (e for e in entries.values() if len(e.locations) >= minimum),
            key=lambda e: (-len(e.locations), e.ecosystem, e.package),
        ),
    )
    monkeypatch.setattr(
        cli.graph,
        "blast_radius",
        lambda name, eco="pip": (
            {**entries[f"{eco}:{name}"].to_dict(), "known": True}
            if f"{eco}:{name}" in entries
            else {"package": name, "ecosystem": eco, "known": False, "reason": "not declared"}
        ),
    )
    monkeypatch.setattr(
        cli.graph,
        "dependencies_of",
        lambda location: (
            {
                eco: sorted(
                    e.package
                    for e in entries.values()
                    if e.ecosystem == eco and location in e.locations
                )
                for eco in sorted(
                    {e.ecosystem for e in entries.values() if location in e.locations}
                )
            }
        ),
    )
    return entries


class TestDuplicationArithmetic:
    """Distinct packages vs total reach — the two numbers that get conflated."""

    def test_reach_counts_package_location_pairs_not_packages(self, cli, fake_graph, capsys):
        """3 + 1 + 1 = 5 pairs across 3 packages, so amplification is 1.7x.

        Constructed rather than measured against the estate: an assertion that
        recomputed the answer from the same graph the code reads would hold
        whatever the code did with it.
        """
        result = cli.main(["--duplication", "--json"])
        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["distinct_packages"] == 3
        assert payload["package_location_pairs"] == 5
        assert payload["amplification"] == 1.7

    def test_the_widest_package_leads_the_report(self, cli, fake_graph, capsys):
        cli.main(["--duplication", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["widest"][0] == {"package": "wide", "locations": 3}

    def test_an_unrouted_package_still_counts_as_reach(self, cli, monkeypatch, capsys):
        """A package nothing could be routed to is exposure of at least one.

        Counting it as zero would make a manifest the resolver failed on
        *improve* the amplification figure — a routing defect showing up as
        good news.
        """
        monkeypatch.setattr(
            cli.graph,
            "build_graph",
            lambda: {
                "pip:orphaned": PackageUsage(
                    package="orphaned",
                    ecosystem="pip",
                    locations=[],
                    manifests=["x/requirements.txt"],
                    unrouted_manifests=["x/requirements.txt"],
                )
            },
        )
        cli.main(["--duplication", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["package_location_pairs"] == 1


class TestNavigation:
    """The owner's flow: a Location, its dependencies, then who else has one."""

    def test_a_package_lists_every_associated_location(self, cli, fake_graph, capsys):
        assert cli.main(["--package", "wide"]) == 0
        out = capsys.readouterr().out
        for location in ("Cryptex", "The Lab", "The Studio"):
            assert location in out

    def test_an_unknown_package_says_so_rather_than_printing_an_empty_list(
        self, cli, fake_graph, capsys
    ):
        """Silence after a lookup reads as "affects nothing"."""
        assert cli.main(["--package", "absent"]) == 0
        assert "not declared" in capsys.readouterr().out

    def test_a_location_shows_which_of_its_dependencies_reach_further(
        self, cli, fake_graph, capsys
    ):
        """This annotation IS the flow the owner described.

        Listing The Lab's packages without it gives no way to tell the one
        shared with two other Locations from the one that is The Lab's alone.
        """
        assert cli.main(["--location", "The Lab"]) == 0
        lines = {
            line.strip().split()[0]: line
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("  ")
        }
        assert "also in 2 other" in lines["wide"]
        assert "also in" not in lines["narrow"]

    def test_shared_defaults_to_two_or_more_locations(self, cli, fake_graph, capsys):
        assert cli.main(["--shared", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert [e["package"] for e in payload["shared"]] == ["wide"]

    def test_the_minimum_threshold_is_honoured(self, cli, fake_graph, capsys):
        cli.main(["--shared", "--minimum", "1", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["shared"]) == 3


class TestArgumentHandling:
    def test_a_mode_is_required(self, cli):
        """Without one, argparse would have to invent a default query."""
        with pytest.raises(SystemExit):
            cli.main([])

    def test_json_output_is_parseable(self, cli, fake_graph, capsys):
        cli.main(["--package", "wide", "--json"])
        json.loads(capsys.readouterr().out)

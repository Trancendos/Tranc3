"""The taxonomy must be derived, complete, and unable to invent nodes.

The owner set the structure (Locations / AIs / Dimensionals) on 2026-09-11. The
risk with any structure handed down like that is that it gets *typed in*: a tidy
tree, hand-maintained, describing an intended platform while the repository holds
a different one. This estate has several registers that decayed exactly that way.

So `src/taxonomy/` derives every node from an existing source, and these tests
check the two properties that keeps honest:

  * completeness -- the tree covers all 43 Locations and every named AI, so a new
    entity cannot be added to the platform and missed by the taxonomy;
  * provenance -- every leaf names where it was read from, so a node that nothing
    supplies is visibly a gap instead of looking like content.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.entities.platform import PLATFORM_ENTITIES  # noqa: E402
from src.taxonomy import build_tree, gaps  # noqa: E402
from src.taxonomy.model import Node, Tree  # noqa: E402

JSON_OUT = REPO / "docs" / "architecture" / "taxonomy.json"
MD_OUT = REPO / "docs" / "architecture" / "TAXONOMY.md"

#: Leaf kinds. A branch is a label from the owner's structure and carries no
#: source of its own; a leaf is content and must name where it came from.
LEAF_KINDS = {
    "ability",
    "component",
    "module",
    "nanoservice",
    "job_description",
    "power_up",
    "ai",
    "trait",
    "agent",
    "bot",
    "dimensional",
}


@pytest.fixture(scope="module")
def tree() -> Tree:
    return build_tree()


# ── Structure ────────────────────────────────────────────────────────────────


def test_the_three_branches_the_owner_specified_exist(tree):
    names = {c.name for c in tree.root.children}
    assert names == {"Locations", "AIs", "Dimensionals (Shared-Core)"}, (
        f"top-level branches are {sorted(names)}; the structure is Locations, AIs, "
        "Dimensionals (Shared-Core)"
    )


def test_every_location_has_the_four_sub_branches(tree):
    locations = tree.root.find("Locations")
    required = {"Abilities", "Components", "Job Descriptions", "Power Ups"}
    for location in locations.children:
        if location.name.startswith("_"):
            # `_unrouted_` is a holding node for work with no Location decision,
            # not a 44th Location. Giving it Abilities and a Job Description would
            # be asserting facts about something whose whole content is that it has
            # no owner yet.
            continue
        present = {c.name for c in location.children}
        assert required <= present, f"{location.name} is missing {sorted(required - present)}"


def test_the_unrouted_holder_claims_nothing_it_does_not_have(tree):
    unrouted = tree.root.find("Locations").find("_unrouted_")
    if unrouted is None:
        pytest.skip("nothing unrouted — every nano-service has an owning Location")
    present = {c.name for c in unrouted.children}
    assert present == {"Components"}, (
        f"_unrouted_ carries {sorted(present)}. It exists to hold code with no owner; "
        "an Abilities or Job Descriptions branch on it would be invented content."
    )
    assert not unrouted.meta.get("lead_ai"), "_unrouted_ must not name a Lead AI"


def test_every_ai_has_the_four_sub_branches(tree):
    ais = tree.root.find("AIs")
    required = {"Profile", "Abilities", "Agents", "Bots"}
    for tier in ais.children:
        for ai in tier.children:
            present = {c.name for c in ai.children}
            assert required <= present, f"{ai.name} is missing {sorted(required - present)}"


def test_the_three_tiers_exist(tree):
    tiers = {c.name for c in tree.root.find("AIs").children}
    assert tiers == {"Tier 1 (Orchestrator)", "Tier 2 (Primes)", "Tier 3 (Lead AI)"}


# ── Completeness ─────────────────────────────────────────────────────────────


def test_all_43_locations_are_present(tree):
    """A 44th entity added to PLATFORM_ENTITIES must appear here without edits."""
    in_tree = {c.name for c in tree.root.find("Locations").children if not c.name.startswith("_")}
    assert in_tree == set(PLATFORM_ENTITIES), (
        f"missing from tree: {sorted(set(PLATFORM_ENTITIES) - in_tree)}; "
        f"extra in tree: {sorted(in_tree - set(PLATFORM_ENTITIES))}"
    )


def test_every_named_lead_ai_appears_exactly_once(tree):
    """Including the five multi-AI Locations' extra names."""
    expected = set()
    for entity in PLATFORM_ENTITIES.values():
        expected.update(entity.lead_ais or [entity.lead_ai])

    found: list[str] = []
    for tier in tree.root.find("AIs").children:
        found.extend(ai.name for ai in tier.children)

    assert set(found) == expected, (
        f"missing: {sorted(expected - set(found))}; extra: {sorted(set(found) - expected)}"
    )
    duplicates = {n for n in found if found.count(n) > 1}
    assert not duplicates, (
        f"{sorted(duplicates)} appear under more than one tier. An AI holding roles "
        "at several Locations is recorded once with `also_serves`, not duplicated."
    )


def test_the_unowned_nanoservices_are_surfaced_not_dropped(tree):
    """61 nano-services belong to no Location; silence there would be the bug."""
    assert tree.count("nanoservice") > 0, (
        "no nano-services in the tree. src/nanoservices/ exists and is deployed on "
        "port 8001; reporting zero means the collector stopped seeing the layer."
    )
    unrouted = tree.root.find("Locations").find("_unrouted_")
    assert unrouted is not None, (
        "nano-services owned by no Location must appear under `_unrouted_` — the "
        "platform's own word for work awaiting a Town Hall routing decision."
    )


# ── Provenance ───────────────────────────────────────────────────────────────


def test_every_leaf_names_its_source(tree):
    sourceless = [
        f"{n.kind}:{n.name}" for n in tree.root.walk() if n.kind in LEAF_KINDS and not n.source
    ]
    assert not sourceless, (
        "leaf nodes with no source:\n"
        + "\n".join(f"  {s}" for s in sourceless[:20])
        + "\n\nA node nothing supplies must be a gap, not content."
    )


def test_no_branch_is_silently_empty(tree):
    """Every declared branch is populated, or named in the gap report."""
    empty = {g["name"] for g in gaps(tree)}
    for node in tree.root.walk():
        if node.kind == "branch" and not node.populated:
            assert node.name in empty, (
                f"branch {node.name!r} is empty but absent from gaps() — an empty "
                "branch that no report mentions is how a register starts lying."
            )


def test_sources_point_at_files_that_exist(tree):
    """A source naming a path that is not there is worse than no source."""
    missing = []
    for node in tree.root.walk():
        if not node.source:
            continue
        path_part = node.source.split("::", 1)[0]
        if not (REPO / path_part).exists():
            missing.append(f"{node.kind}:{node.name} -> {node.source}")
    assert not missing, "sources pointing at nothing:\n" + "\n".join(missing[:20])


# ── The published output ─────────────────────────────────────────────────────


def test_published_tree_is_current():
    """The same check CI runs. Stale output means the docs describe an old repo."""
    result = subprocess.run(
        [sys.executable, "scripts/build_taxonomy_tree.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "docs/architecture/taxonomy.json or TAXONOMY.md is stale.\n"
        f"{result.stdout}\n{result.stderr}\n"
        "Run: python3 scripts/build_taxonomy_tree.py"
    )


def test_published_json_parses_and_matches_the_built_tree(tree):
    published = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    assert published == tree.to_dict()


# ── Probes ───────────────────────────────────────────────────────────────────


class TestTheGuardsWouldCatchIt:
    def test_a_sourceless_leaf_is_detected(self):
        root = Node("r", "root")
        root.add(Node("orphan", "ability"))  # no source
        bad = [n for n in root.walk() if n.kind in LEAF_KINDS and not n.source]
        assert bad, "the provenance check would not have fired"

    def test_an_empty_branch_is_reported_as_a_gap(self):
        root = Node("r", "root")
        root.add(Node("Power Ups", "branch"))
        found = gaps(Tree(root))
        assert [g["name"] for g in found] == ["Power Ups"]

    def test_a_branch_with_populated_children_is_not_a_gap(self):
        root = Node("r", "root")
        branch = root.add(Node("Abilities", "branch"))
        branch.add(Node("a", "ability", source="src/entities/platform.py"))
        assert gaps(Tree(root)) == []

    def test_a_dropped_location_would_fail_completeness(self, tree):
        in_tree = {
            c.name for c in tree.root.find("Locations").children if not c.name.startswith("_")
        }
        assert in_tree, "no locations at all — completeness check has nothing to compare"
        pruned = in_tree - {next(iter(sorted(in_tree)))}
        assert pruned != set(PLATFORM_ENTITIES), (
            "removing a Location still compared equal; the completeness check is inert"
        )

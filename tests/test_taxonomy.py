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


# ── The legacy fallback, and its survival ────────────────────────────────────
#
# These two travel together. The first says the fallback points somewhere
# useful; the second says it still will after the migration script is re-run,
# which its own docstring says it is built to be.


def _singular() -> str:
    """The pre-rename directory name, built rather than written.

    A bare literal here would be rewritten by
    `scripts/migrate_to_dimensionals.py` on its next run, turning the
    assertions below into comparisons of the new name with itself -- green,
    and measuring nothing. That is the defect these tests exist to catch, so
    they must not contain it.
    """
    from src.taxonomy.build import DIMENSIONALS_DIR

    return DIMENSIONALS_DIR.name[:-1]


def test_the_legacy_fallback_is_not_the_canonical_path() -> None:
    """src/taxonomy/build.py promises to fall back to the pre-rename directory.

    The rename rewrote that constant too, so both pointed at the plural and
    the fallback could not fall back: mid-migration the taxonomy would report
    the entire shared core as missing, which is exactly what the fallback was
    written to prevent.
    """
    from src.taxonomy.build import DIMENSIONALS_DIR, LEGACY_DIMENSIONAL_DIR

    assert LEGACY_DIMENSIONAL_DIR != DIMENSIONALS_DIR, (
        "the legacy fallback must name the pre-rename directory, not the current one"
    )
    assert LEGACY_DIMENSIONAL_DIR.name == _singular(), (
        "the pre-rename directory was the singular form -- one shared-core tree"
    )
    assert DIMENSIONALS_DIR.name.endswith("s")


def test_the_legacy_fallback_survives_a_migration_rerun() -> None:
    """Re-running the rename must not rewrite the constant back into a tautology.

    Writing the old name back by hand did not fix this the first time: the
    literal was still in the source for the next run to find. The measurement
    is the real rewriter against the real file, not a copy of its patterns --
    a copy would drift from the script and pass while the script still broke
    the file.

    Probed: with the bare literal restored, `rewrite_text` reports 1 and this
    test fails. (The original defect measured 2 -- the constant and a mention
    of the old name in its own comment; the comment no longer spells it.)
    """
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    from migrate_to_dimensionals import rewrite_text

    source = (REPO / "src" / "taxonomy" / "build.py").read_text(encoding="utf-8")
    _, count = rewrite_text(source)

    assert count == 0, (
        f"a migration re-run would rewrite {count} reference(s) in "
        "src/taxonomy/build.py -- the legacy fallback would stop falling back"
    )


# ── Two findings CodeAnt raised on #1248 ─────────────────────────────────────


def test_no_node_name_is_a_dataclass_repr() -> None:
    """Agents and bots expose `code_name`/`description`, not `name`/`role`.

    The first version read them with `getattr(agent, "name", str(agent))`, a
    defaulting accessor that cannot fail: the attribute was absent, so every
    agent and bot node was named with the dataclass repr and carried an empty
    detail. Measured on the published tree before the fix: **282** such nodes.

    A defaulting accessor over an attribute that does not exist is the same
    shape as a check that cannot fail -- it reports a populated tree either
    way. Reading the real attribute means a rename breaks loudly instead.
    """
    tree = build_tree()
    offenders = [
        n.name
        for n in tree.root.walk()
        if isinstance(n.name, str) and ("Agent(" in n.name or "Bot(" in n.name)
    ]
    assert not offenders, (
        f"{len(offenders)} node(s) are named with a dataclass repr rather than "
        f"a code_name: {offenders[:3]}"
    )


def test_every_agent_and_bot_carries_its_description() -> None:
    """The other half: the name resolving is not enough if detail stays empty."""
    tree = build_tree()
    bare = [n.name for n in tree.root.walk() if n.kind in {"agent", "bot"} and not n.detail]
    assert not bare, f"{len(bare)} agent/bot node(s) carry no detail: {bare[:3]}"


def test_the_unrouted_holder_is_not_counted_as_a_location() -> None:
    """`_unrouted_` is a holder for work with no Location decision, not a Location.

    Counting it made the estate read 44 against the canonical 43 platform
    entities -- a register misstating the size of the thing it describes. It
    must stay in the tree, because the Town Hall owes those nano-services an
    answer and the taxonomy's job is to stop them being hidden; it must simply
    not be tallied as an entity.
    """
    tree = build_tree()
    locations = [n for n in tree.root.walk() if n.kind == "location"]
    assert len(locations) == 43, (
        f"expected the 43 canonical platform entities, counted {len(locations)}"
    )
    assert not any(n.name == "_unrouted_" for n in locations), (
        "the synthetic unrouted holder must not carry the 'location' kind"
    )
    assert any(n.name == "_unrouted_" for n in tree.root.walk()), (
        "it must still appear in the tree -- hiding unrouted work is the "
        "failure this node exists to prevent"
    )


def test_the_branch_covers_every_shared_core_tree_its_contract_names() -> None:
    """`src/taxonomy/__init__.py` names three trees; the builder scanned one.

    Its own contract says the Dimensionals branch covers "`Dimensionals/`
    subpackages, `src/mesh/`, router modules", and `shared_core/` still holds
    forks that CLAUDE.md tracks as an open decision. Measured before the fix:
    no `src/mesh` module and no `shared_core` evidence anywhere in the tree.

    The part that made it invisible rather than merely missing: scanning only
    the canonical directory means neither tree can reach `Unclassified`
    either, so a branch claiming to cover the layer omitted two of its three
    sources and reported nothing wrong.
    """
    tree = build_tree()
    sources = [n.source for n in tree.root.walk() if n.source]

    assert any(s.startswith("src/mesh") for s in sources), (
        "the contract names src/mesh/ and no node comes from it"
    )
    assert any(s.startswith("shared_core") for s in sources), (
        "shared_core/ still holds unreconciled forks and no node comes from it"
    )


def test_the_taxonomy_and_the_migration_script_agree_on_the_forks() -> None:
    """One list of real forks, not two that can disagree.

    `migrate_to_dimensionals.py --forks` is the authority on which
    `shared_core/` modules are genuinely divergent rather than shims. The
    taxonomy reads that list rather than keeping a copy, so this asserts the
    reading works -- a silent import failure would mark every module a shim
    and quietly claim the estate has no unreconciled forks.

    It also pins the dunder case: `shared_core/__init__.py` and
    `shared_core/middleware/__init__.py` are real forks, and filtering dunder
    files as packaging noise showed 9 where the script says 11.
    """
    from src.taxonomy import build as taxonomy_build

    script_forks = {name for name, _ in taxonomy_build._shared_core_forks()}
    assert script_forks, "the migration script's fork list could not be read"

    tree_forks = {n.source for n in build_tree().root.walk() if n.kind == "fork"}
    assert tree_forks == script_forks, (
        f"taxonomy reports {len(tree_forks)} forks, the script reports "
        f"{len(script_forks)}: {sorted(tree_forks ^ script_forks)}"
    )

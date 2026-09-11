"""Assemble the taxonomy tree by reading the platform's existing sources.

Every function here reads. None of them declares. If a level of the owner's
structure has no source in this repo, `build_tree()` emits the node with an
empty `source` and `gaps()` reports it -- because a taxonomy whose empty
branches look like filled ones is a picture, not a register.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, List

from src.taxonomy.model import Node, Tree

REPO = Path(__file__).resolve().parents[2]

PROFILES_DIR = REPO / "src" / "personality" / "profiles"
NANOSERVICES_DIR = REPO / "src" / "nanoservices"
DIMENSIONALS_DIR = REPO / "Dimensionals"
LEGACY_DIMENSIONAL_DIR = REPO / "Dimensionals"
LEGACY_SHARED_CORE_DIR = REPO / "shared_core"
SHARDS_WORKER = REPO / "workers" / "infinity-shards-service" / "worker.py"

#: Which Dimensionals subpackage answers to which branch of the owner's tree.
#: Read as a classification of what is there, not a plan for what should be.
DIMENSIONAL_BRANCHES: Dict[str, tuple[str, ...]] = {
    "Services": ("architecture", "orchestration", "infinity", "nexus", "hive", "swarm"),
    "Middleware": ("middleware", "security", "security_automation", "cors", "error_handlers"),
    "Databases": ("dimensionals", "models", "registry"),
    "Mesh": ("bus", "cellular", "genetics", "gas", "liquid", "quantum", "reservoir", "pillars"),
    "Routers": ("cross_bridge_orchestrator", "three_bridge_coordinator", "circuit_state"),
}


def _dimensionals_root() -> Path:
    """Prefer the canonical Dimensionals/ tree; fall back to the legacy name.

    The owner renamed this layer to DIMENSIONALS on 2026-09-11. The fallback
    exists so the taxonomy still builds mid-migration rather than reporting the
    entire shared core as missing.
    """
    if DIMENSIONALS_DIR.is_dir():
        return DIMENSIONALS_DIR
    return LEGACY_DIMENSIONAL_DIR


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:  # pragma: no cover - defensive
        return path.as_posix()


# ── Locations ────────────────────────────────────────────────────────────────


def _shard_catalogue() -> List[str]:
    """Power Up types, read from the Infinity Shards catalogue.

    Parsed rather than imported: the worker binds a port and opens a database at
    import time, which a documentation build has no business doing.
    """
    if not SHARDS_WORKER.is_file():
        return []
    tree = ast.parse(SHARDS_WORKER.read_text(encoding="utf-8"))
    for node in tree.body:
        # The catalogue is annotated (`SHARD_CATALOGUE: Dict[...] = {...}`), which
        # is an AnnAssign and not an Assign -- handling only the latter is why an
        # earlier pass reported zero Power Ups for all 43 Locations.
        if isinstance(node, ast.AnnAssign):
            named = isinstance(node.target, ast.Name) and node.target.id == "SHARD_CATALOGUE"
        elif isinstance(node, ast.Assign):
            named = any(isinstance(t, ast.Name) and t.id == "SHARD_CATALOGUE" for t in node.targets)
        else:
            continue
        if named and isinstance(node.value, ast.Dict):
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    return []


#: Directories that are build output or vendored code, not Components.
_SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build", ".venv", "venv", ".git"}

#: Component/Module collection is language-agnostic on purpose. Restricting it to
#: `*.py` reported Arcadia (`web/`, TypeScript) and The Workshop
#: (`deploy/forgejo/`, compose and shell) as having no Components at all -- two
#: fabricated gaps caused by the collector's blind spot rather than the estate's.
_SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".svelte",
    ".rs",
    ".go",
    ".sh",
    ".sql",
    ".yml",
    ".yaml",
    ".toml",
    ".conf",
}


def _components_for(worker_path: str | None) -> List[Node]:
    """Components = the Python modules and packages under a Location's code path.

    A package becomes a Component with its modules beneath it; a loose module is
    a Component in its own right. This is the level the owner's tree calls
    Components > Modules, derived from what the Location actually ships.
    """
    if not worker_path:
        return []
    root = REPO / worker_path
    if root.is_file():
        return [Node(root.stem, "component", source=_rel(root))]
    if not root.is_dir():
        return []

    components: List[Node] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith((".", "__")) or child.name in _SKIP_DIRS:
            continue
        if child.is_dir():
            modules = [
                Node(m.stem, "module", source=_rel(m))
                for m in sorted(child.rglob("*"))
                if m.is_file()
                and m.suffix in _SOURCE_SUFFIXES
                and not any(part in _SKIP_DIRS or part.startswith(".") for part in m.parts)
            ]
            if modules:
                components.append(
                    Node(child.name, "component", source=_rel(child), children=modules)
                )
        elif child.suffix in _SOURCE_SUFFIXES:
            components.append(Node(child.stem, "component", source=_rel(child)))
    return components


def _nanoservices() -> List[Node]:
    if not NANOSERVICES_DIR.is_dir():
        return []
    return [
        Node(d.name, "nanoservice", source=_rel(d))
        for d in sorted(NANOSERVICES_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(("__", "."))
    ]


def _locations_branch() -> Node:
    from src.entities.platform import (  # imported late: heavy module
        JOB_DESCRIPTIONS,
        PLATFORM_ENTITIES,
        get_seats,
    )

    shards = _shard_catalogue()
    nanos = _nanoservices()
    branch = Node("Locations", "branch", source="src/entities/platform.py")

    for name, entity in sorted(PLATFORM_ENTITIES.items()):
        loc = branch.add(
            Node(
                name,
                "location",
                source="src/entities/platform.py",
                detail=entity.primary_function,
                meta={
                    "pid": entity.pid,
                    "pillar": entity.pillar.value,
                    "lead_ai": entity.lead_ai,
                    "worker_path": entity.worker_path or "",
                    "worker_port": entity.worker_port,
                },
            )
        )

        abilities = loc.add(Node("Abilities", "branch"))
        for ability in entity.abilities:
            abilities.add(Node(ability, "ability", source="src/entities/platform.py"))

        components = loc.add(Node("Components", "branch"))
        for component in _components_for(entity.worker_path):
            components.add(component)
        if entity.worker_path and entity.worker_path.startswith("src/nanoservices"):
            for nano in nanos:
                components.add(nano)

        jobs = loc.add(Node("Job Descriptions", "branch"))
        title = JOB_DESCRIPTIONS.get(name)
        for seat in get_seats(name):
            jobs.add(
                Node(
                    seat.job_description or title or "",
                    "job_description",
                    source="src/entities/platform.py::JOB_DESCRIPTIONS",
                    detail=f"designed for {seat.designed_for}",
                    meta={
                        "seat_id": seat.seat_id,
                        "designed_for": seat.designed_for,
                        "is_primary": seat.is_primary,
                        "mandate": seat.mandate,
                        "functions": list(seat.functions),
                    },
                )
            )

        power_ups = loc.add(Node("Power Ups", "branch"))
        for shard in shards:
            power_ups.add(Node(shard, "power_up", source=_rel(SHARDS_WORKER) + "::SHARD_CATALOGUE"))

    # Nano-services owned by no Location.
    #
    # `src/nanoservices/` holds 61 of them and not one is claimed: no Location's
    # `worker_path` points into it, and `config/estate/registry.yaml` records the
    # layer itself with `lead_ai: null`. Reporting that as "0 nano-services" would
    # have been the comfortable answer and a false one -- the layer exists, it is
    # deployed on port 8001, and nobody owns it.
    #
    # `_unrouted_` is this platform's own word for work with no Location decision
    # (CLAUDE.md, Backlog Routing Register), so it is used here rather than a new
    # one. The Town Hall routes these; the taxonomy only has to stop hiding them.
    owned = {
        nano.name
        for location in branch.children
        for comp in (location.find("Components").children if location.find("Components") else [])
        for nano in [comp]
        if comp.kind == "nanoservice"
    }
    orphans = [n for n in nanos if n.name not in owned]
    if orphans:
        unrouted = branch.add(
            Node(
                "_unrouted_",
                "location",
                source="config/estate/registry.yaml::TRC-P0-006",
                detail=(
                    f"{len(orphans)} nano-services with no owning Location "
                    f"(registry records lead_ai: null)"
                ),
                meta={"worker_path": "src/nanoservices/", "worker_port": 8001, "lead_ai": ""},
            )
        )
        components = unrouted.add(Node("Components", "branch"))
        for nano in orphans:
            components.add(nano)

    return branch


# ── AIs ──────────────────────────────────────────────────────────────────────


def _profile_for(ai_name: str) -> Path | None:
    """Resolve an AI to its personality profile file.

    Uses `AI_NAME_TO_PROFILE_ID` first, because several AIs deliberately share a
    profile -- the five Porters resolve to `the-porter-family.json`, The Dutchy to
    `predictive-lore.json`, Nexus-Prime to `the-nexus-ai.json`. Slugifying the
    name instead reported all of those as having no profile at all, which would
    have turned a documented design decision into twelve fabricated gaps.
    """
    try:
        from src.personality.role_resolution import AI_NAME_TO_PROFILE_ID
    except Exception:  # pragma: no cover - defensive
        AI_NAME_TO_PROFILE_ID = {}  # type: ignore[assignment]

    profile_id = AI_NAME_TO_PROFILE_ID.get(ai_name)
    if profile_id:
        candidate = PROFILES_DIR / f"{profile_id}.json"
        if candidate.is_file():
            return candidate

    slug = (
        ai_name.lower()
        .replace(" (", "-")
        .replace(")", "")
        .replace("'", "")
        .replace(".", "")
        .replace(" ", "-")
    )
    candidate = PROFILES_DIR / f"{slug}.json"
    return candidate if candidate.is_file() else None


def _ais_branch() -> Node:
    from src.entities.platform import PLATFORM_ENTITIES, get_orchestration_tier

    branch = Node("AIs", "branch", source="src/entities/platform.py")
    tiers: Dict[str, Node] = {}
    for label in ("Tier 1 (Orchestrator)", "Tier 2 (Primes)", "Tier 3 (Lead AI)"):
        tiers[label] = branch.add(
            Node(label, "branch", source="src/entities/platform.py::get_orchestration_tier")
        )

    # Every named AI, with the Location it answers for. An AI appearing under two
    # Locations (Rocking Ricki, Voxx) is recorded once per seat, which is the
    # truth -- one AI, several roles.
    seen: Dict[str, Node] = {}
    for loc_name, entity in sorted(PLATFORM_ENTITIES.items()):
        names = entity.lead_ais or [entity.lead_ai]
        for ai_name in names:
            tier = get_orchestration_tier(ai_name)
            label = {
                "Trance-One": "Tier 1 (Orchestrator)",
                "T2ance": "Tier 2 (Primes)",
            }.get(getattr(tier, "value", str(tier)), "Tier 3 (Lead AI)")

            key = f"{label}::{ai_name}"
            if key in seen:
                seen[key].meta.setdefault("also_serves", []).append(loc_name)
                continue

            node = tiers[label].add(
                Node(
                    ai_name,
                    "ai",
                    source="src/entities/platform.py",
                    detail=f"{loc_name} — {entity.primary_function}",
                    meta={"location": loc_name, "base_model": getattr(tier, "value", str(tier))},
                )
            )
            seen[key] = node

            profile_path = _profile_for(ai_name)
            profile = node.add(
                Node(
                    "Profile",
                    "branch",
                    source=_rel(profile_path) if profile_path else "",
                )
            )
            if profile_path:
                try:
                    data = json.loads(profile_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {}
                personality = profile.add(Node("Personality", "branch", source=_rel(profile_path)))
                for trait in sorted(data.get("traits", {}) or {}):
                    personality.add(Node(trait, "trait", source=_rel(profile_path)))

            abilities = node.add(Node("Abilities", "branch"))
            for ability in entity.abilities:
                abilities.add(Node(ability, "ability", source="src/entities/platform.py"))

            agents = node.add(Node("Agents", "branch", source="src/entities/platform.py"))
            pair = entity.agent_teams.get(ai_name)
            alpha = pair.alpha if pair else entity.agent_alpha
            beta = pair.beta if pair else entity.agent_beta
            for agent in (alpha, beta):
                agents.add(
                    Node(
                        getattr(agent, "name", str(agent)),
                        "agent",
                        source="src/entities/platform.py",
                        detail=getattr(agent, "role", ""),
                    )
                )

            bots = node.add(Node("Bots", "branch", source="src/entities/platform.py"))
            for bot in (entity.bot_01, entity.bot_02, entity.bot_03, entity.bot_04):
                bots.add(
                    Node(
                        getattr(bot, "name", str(bot)),
                        "bot",
                        source="src/entities/platform.py",
                        detail=getattr(bot, "function", ""),
                    )
                )

    return branch


# ── Dimensionals ─────────────────────────────────────────────────────────────


def _dimensionals_branch() -> Node:
    root = _dimensionals_root()
    branch = Node(
        "Dimensionals (Shared-Core)",
        "branch",
        source=_rel(root) if root.is_dir() else "",
    )
    if not root.is_dir():
        return branch

    classified: set[str] = set()
    for label, members in DIMENSIONAL_BRANCHES.items():
        node = branch.add(Node(label, "branch"))
        for member in members:
            as_dir = root / member
            as_mod = root / f"{member}.py"
            if as_dir.is_dir():
                node.add(Node(member, "dimensional", source=_rel(as_dir)))
                classified.add(member)
            elif as_mod.is_file():
                node.add(Node(member, "dimensional", source=_rel(as_mod)))
                classified.add(member)

    # Anything present but unclassified is shown, not dropped. A silent drop is
    # how an inventory starts describing less than the estate holds.
    unclassified = branch.add(Node("Unclassified", "branch"))
    for child in sorted(root.iterdir()):
        stem = child.stem if child.suffix == ".py" else child.name
        if stem.startswith(("__", ".")) or stem in classified:
            continue
        if child.is_dir() or child.suffix == ".py":
            unclassified.add(Node(stem, "dimensional", source=_rel(child)))

    return branch


# ── Assembly ─────────────────────────────────────────────────────────────────


def build_tree() -> Tree:
    root = Node("Trancendos", "root", source="src/entities/platform.py")
    root.add(_locations_branch())
    root.add(_ais_branch())
    root.add(_dimensionals_branch())
    return Tree(root)


def gaps(tree: Tree) -> List[Dict[str, str]]:
    """Branch nodes that nothing populates.

    This is the output the owner actually needs: not a tidy tree, but the list
    of places where the structure exists and the content does not.
    """
    out: List[Dict[str, str]] = []
    for node in tree.root.walk():
        if node.kind == "branch" and not node.populated:
            out.append({"name": node.name, "kind": node.kind})
    return out

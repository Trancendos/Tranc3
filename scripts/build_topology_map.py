#!/usr/bin/env python3
"""Generate the Trancendos platform topology map from live repo state.

Builds a single cross-referenced graph of the platform's three layers and
writes it as both machine-readable JSON and a self-contained interactive
HTML viewer:

  1. **AI/Location layer** — the 43 canonical entities in
     `src.entities.platform.PLATFORM_ENTITIES` (Location, Lead AI(s), Pillar,
     Primes, claimed `worker_port`/`worker_path`).
  2. **App/Service layer** — every service actually deployed in
     `docker-compose.production.yml` (has a `build:` target) and every
     router actually mounted in `api.py` right now, cross-referenced against
     the curated duplicate-risk classification already maintained in
     `scripts/check_duplicate_routers.py` (imported directly, not copied —
     see `_load_guard_module()` — plus the supplementary categories below
     for routers that guard doesn't track: CORE_LOAD_BEARING, NO_WORKER_EXISTS,
     NOT_A_REAL_ROUTER, and the history of already-removed duplicates).
  3. **Matrix Suites weave** — the 8 governance suites in
     `compliance/magna-carta/compliance/matrix_suites.yaml`, each stewarded
     by one Location/Lead AI, cutting across both other layers.

Why this exists: `docs/governance/MONOLITH-EXTRACTION-FINDINGS.md` found the
same "looks connected, isn't" mistake twice by hand this session (Resonate,
then I-Mind) before it was caught. A live-generated map that cross-checks
*claimed* topology (`PLATFORM_ENTITIES`'s `worker_path`) against *actual*
topology (compose + api.py's real mount state right now) turns that into
something the map itself flags, instead of something that has to be
re-discovered by reading code every time. This script does NOT hand-encode
"this location is healthy" — every edge is derived from a live source or
from the same curated, reasoned classification the router-duplication guard
already enforces in CI, so the map only ever tells the same story the code
actually does right now.

Regenerate after any change to `api.py` mounts, `docker-compose.production.yml`
services, `src/entities/platform.py`, `scripts/check_duplicate_routers.py`'s
tables, or the Matrix Suites registry. `scripts/check_topology_map_freshness.py`
fails CI if the committed output has drifted from what this script would
produce right now.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
API_PY = ROOT / "api.py"
COMPOSE = ROOT / "docker-compose.production.yml"
MATRIX_SUITES_YAML = ROOT / "compliance" / "magna-carta" / "compliance" / "matrix_suites.yaml"
OUTPUT_DIR = ROOT / "docs" / "architecture"
OUTPUT_JSON = OUTPUT_DIR / "topology-graph.json"
OUTPUT_HTML = OUTPUT_DIR / "topology-map.html"

sys.path.insert(0, str(ROOT))

INCLUDE_ROUTER_RE = re.compile(r"app\.include_router\((_\w+_router)\)")
IMPORT_ROUTER_RE = re.compile(
    r"from\s+([\w.]+)\s+import\s*\(?\s*(?:\n\s*)?router\s+as\s+(_\w+_router)", re.MULTILINE
)

# Supplementary classification for mounted routers `check_duplicate_routers.py`
# doesn't track (it only tracks routers with a *claimed* worker relationship).
# See docs/governance/MONOLITH-EXTRACTION-FINDINGS.md's second-pass sweep for
# the reasoning behind each entry. router_var -> (classification, reason).
CORE_LOAD_BEARING: dict[str, str] = {
    "_observatory_router": (
        "Widest fan-in in the whole platform (~20 modules call observe() "
        "synchronously). Same-named workers/observatory/ is a different "
        "feature (trace/metrics dashboard); workers/audit-service/ is the "
        "route-shape-closer match but still a separate process."
    ),
    "_citadel_router": "DevOps hub wrapper around this host's own Docker/Traefik/Forgejo.",
    "_luminous_router": "The AI inference/consciousness pipeline itself.",
    "_thinktank_router": "The quantum neural core inference pipeline itself.",
    "_enhanced_router": "Intentional aggregator facade over several in-process engines.",
    "_ecosystem_router": "Intentional aggregator facade over several in-process engines.",
    "_aeonmind_router": "Sole live implementation of the AeonMind bridge spec.",
    "_t2ance_router": "Part of the Trancendos Models Matrix tiering engine itself.",
    "_trance_one_router": "Part of the Trancendos Models Matrix tiering engine itself.",
    "_tranc3ts_router": "IS the HTTP bridge surface for external TypeScript callers.",
}
NO_WORKER_EXISTS: dict[str, str] = {
    "_apimarket_router": "No workers/apimarket* in compose. Genuine future-extraction candidate.",
    "_roles_router": (
        "No worker. Real in-process callers on the registry class "
        "(relations/registry.py, personality/role_resolution.py) — any future "
        "extraction needs a bridge, not just an unmount."
    ),
    "_deployment_modes_router": "No worker. Genuine future-extraction candidate.",
    "_notebooks_router": "No worker. Genuine future-extraction candidate.",
    "_relations_router": "No worker. Real caller: roles/registry.py.",
    "_access_router": "No worker. Genuine future-extraction candidate.",
    "_models_router": "No worker. No tight in-process coupling from other subsystems.",
}
# check_duplicate_routers.py tracks these in KNOWN_COUPLED for CI
# regression-safety (so a future PR can't unmount one silently), but their
# recorded reasons resolve to something more specific than a still-open
# "needs_modularization" decision — reclassify here rather than lumping them
# in with genuine pending candidates like Resonate/I-Mind (the only two
# still open — see BRIDGES_IMPLEMENTED in MONOLITH-EXTRACTION-FINDINGS.md).
GUARD_COUPLED_RECLASSIFY: dict[str, str] = {
    "_turingshub_router": "core_load_bearing",
    # Genuinely coupled (in-process singleton has real callers, router can't
    # be unmounted) *and* already has a working HTTP bridge to its worker —
    # neither "still needs a decision" nor "confirmed permanently separate".
    "_nexus_router": "bridged",
    # Newly bridged in the 2026-08-08 remediation pass, fail-open by
    # explicit owner decision — see BRIDGES_IMPLEMENTED in
    # MONOLITH-EXTRACTION-FINDINGS.md for what each bridge actually does.
    "_basement_router": "bridged",
    "_cryptex_router": "bridged",
    "_billing_router": "bridged",
    "_library_router": "bridged",
    # Each of these three has zero live in-process caller and a gap to its
    # same-named worker too large to call "unfinished" — search_api's is an
    # entire vector-DB stack, admin_os's and section7's are different
    # subsystems entirely (entity-config-admin vs. a cells/fabric concept;
    # RSS market-intel vs. platform self-health reports). Nothing breaks
    # either way, so there's no risk to weigh — the decision is just to stop
    # treating a same-name coincidence as an open question. Revisit only if
    # a real requirement emerges to unify them.
    "_admin_os_router": "confirmed_separate_features",
    "_search_router": "confirmed_separate_features",
    "_section7_router": "confirmed_separate_features",
    # townhall's in-process caller (research/section7.py) already wraps the
    # call in try/except with graceful degradation — no live request path
    # depends on it, and cranbania is a different tech stack entirely
    # (Next.js/TypeScript Kanban board, not a Python FastAPI worker), so
    # there's no HTTP bridge to build here, just a product boundary to accept.
    "_townhall_router": "confirmed_separate_features",
}

# Already-shipped safe removals (2026-08-08 sweep) — shown as historical
# "duplicate eliminated" edges even though the router var no longer appears
# in api.py. module -> worker compose service name.
SAFE_REMOVED_HISTORY: dict[str, str] = {
    "src.taimra.routes": "taimra",
    "src.studio.routes": "the-studio",
    "src.lab.routes": "the-lab",
    "src.chronos.routes": "cron-service",
    "src.devocity.routes": "devocity",
    "src.artifactory.routes": "artifactory-service",
    "src.vrar3d.routes": "vrar3d",
}


def _load_guard_module():
    """Import scripts/check_duplicate_routers.py by path (scripts/ has no
    __init__.py) so its ROUTER_TO_WORKER/KNOWN_COUPLED tables are reused
    verbatim rather than re-typed here — one source of truth for the
    duplicate-risk classification, same as CI's own guard uses."""
    spec = importlib.util.spec_from_file_location(
        "check_duplicate_routers", ROOT / "scripts" / "check_duplicate_routers.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _mounted_routers_with_modules() -> dict[str, str]:
    """router_var -> dotted src module, for every router currently mounted."""
    text = API_PY.read_text(encoding="utf-8")
    mounted = set(INCLUDE_ROUTER_RE.findall(text))
    modules: dict[str, str] = {}
    for module, var in IMPORT_ROUTER_RE.findall(text):
        if var in mounted:
            modules[var] = module
    return modules


def _compose_services() -> dict[str, dict[str, Any]]:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")).get("services") or {}
    return {name: (svc or {}) for name, svc in services.items()}


def _service_port(svc: dict[str, Any]) -> Optional[str]:
    env = svc.get("environment")
    if isinstance(env, dict) and env.get("PORT") is not None:
        return str(env["PORT"])
    if isinstance(env, list):
        for e in env:
            if str(e).startswith("PORT="):
                return str(e).split("=", 1)[1]
    labels = svc.get("labels") or []
    if isinstance(labels, dict):
        for key, value in labels.items():
            if key.endswith("loadbalancer.server.port"):
                return str(value)
    else:
        label_text = " ".join(str(item) for item in labels)
        m = re.search(r"loadbalancer\.server\.port=(\d+)", label_text)
        if m:
            return m.group(1)
    for p in svc.get("ports") or []:
        m = re.match(r'^"?(\d+):', str(p))
        if m:
            return m.group(1)
    return None


def _build_service_nodes(compose: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = []
    for name, svc in compose.items():
        if "build" not in svc:
            continue  # infra/data volume/db, not a Trancendos service
        nodes.append(
            {
                "id": f"worker:{name}",
                "type": "service",
                "label": name,
                "port": _service_port(svc),
                "deployed": True,
            }
        )
    return nodes


def _classify_mounted_routers(
    mounted: dict[str, str], guard
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (router nodes, classification edges to worker nodes)."""
    router_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for router_var, module in mounted.items():
        node: dict[str, Any] = {
            "id": f"router:{router_var}",
            "type": "router",
            "label": module,
            "mounted": True,
        }
        if router_var in guard.ROUTER_TO_WORKER:
            _, worker_name = guard.ROUTER_TO_WORKER[router_var]
            reason = guard.KNOWN_COUPLED.get(router_var)
            if router_var in GUARD_COUPLED_RECLASSIFY:
                node["classification"] = GUARD_COUPLED_RECLASSIFY[router_var]
                node["reason"] = reason
            elif reason:
                node["classification"] = "needs_modularization"
                node["reason"] = reason
            else:
                # Tracked with a worker, mounted, but no KNOWN_COUPLED reason
                # recorded — matches check_duplicate_routers.py's own
                # "looks like an unremoved duplicate" failure condition.
                node["classification"] = "unreasoned_duplicate_risk"
                node["reason"] = (
                    "Mounted, a same-service worker is deployed, and no "
                    "KNOWN_COUPLED reason is recorded — check_duplicate_routers.py "
                    "would fail CI on this."
                )
            edges.append(
                {
                    "source": node["id"],
                    "target": f"worker:{worker_name}",
                    "kind": node["classification"],
                }
            )
        elif router_var in CORE_LOAD_BEARING:
            node["classification"] = "core_load_bearing"
            node["reason"] = CORE_LOAD_BEARING[router_var]
        elif router_var in NO_WORKER_EXISTS:
            node["classification"] = "no_worker_exists"
            node["reason"] = NO_WORKER_EXISTS[router_var]
        else:
            node["classification"] = "unclassified"
            node["reason"] = "Mounted, no worker-duplication question raised in the sweep."
        router_nodes.append(node)

    return router_nodes, edges


def _removed_history_nodes_edges() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = []
    edges = []
    for module, worker_name in SAFE_REMOVED_HISTORY.items():
        node_id = f"removed:{module}"
        nodes.append(
            {
                "id": node_id,
                "type": "router",
                "label": module,
                "mounted": False,
                "classification": "safe_duplicate_removed",
                "reason": (
                    f"Confirmed genuine duplicate of workers/{worker_name}/, "
                    "unmounted from api.py in the 2026-08-08 sweep."
                ),
            }
        )
        edges.append({"source": node_id, "target": f"worker:{worker_name}", "kind": "removed"})
    return nodes, edges


def _entity_nodes_and_links(
    compose_names: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Location + Lead AI nodes, plus (a) location->AI edges and (b)
    location->service link edges derived from `worker_path`/`worker_port`,
    flagged `claim_verified` when the claim matches something the App/Service
    layer actually found live, `stale_claim` when it points at a `src/`
    in-process path for which a same-name compose worker with a build target
    now exists (the exact drift class Resonate/I-Mind were caught by)."""
    from src.entities.platform import PLATFORM_ENTITIES  # noqa: E402

    location_nodes = []
    ai_nodes = []
    edges = []
    seen_ai: set[str] = set()

    for location, entity in PLATFORM_ENTITIES.items():
        loc_id = f"location:{location}"
        location_nodes.append(
            {
                "id": loc_id,
                "type": "location",
                "label": location,
                "pillar": entity.pillar.value,
                "pid": entity.pid,
                "primary_function": entity.primary_function,
                "claimed_worker_port": entity.worker_port,
                "claimed_worker_path": entity.worker_path,
            }
        )

        names = entity.lead_ais or [entity.lead_ai]
        for ai_name in names:
            ai_id = f"ai:{ai_name}"
            if ai_id not in seen_ai:
                ai_nodes.append(
                    {"id": ai_id, "type": "lead_ai", "label": ai_name, "aid": entity.aid}
                )
                seen_ai.add(ai_id)
            edges.append({"source": loc_id, "target": ai_id, "kind": "runs"})

        claimed_path = entity.worker_path or ""
        claim_status = None
        target_node = None
        if entity.worker_port is not None:
            target_node = f"worker:{location}"  # best-effort; may not match compose name
            claim_status = "claimed_port"
        if claimed_path.startswith("workers/"):
            worker_name = claimed_path.strip("/").split("/")[-1]
            if worker_name in compose_names:
                target_node = f"worker:{worker_name}"
                claim_status = "claim_verified"
            else:
                claim_status = "stale_claim"
        elif claimed_path.startswith("src/"):
            probable = claimed_path.strip("/").split("/")[-1].replace("_", "-")
            # e.g. "src/studio/" -> does a same-ish-named deployed worker
            # exist that this Location's own record doesn't mention? Exact
            # or "the-<name>"/"<name>-service" only — a bare substring check
            # (e.g. "studio" inside "sashas-photo-studio") produced false
            # positives when this was tried loosely.
            candidates = {
                n
                for n in compose_names
                if n == probable or n == f"the-{probable}" or n == f"{probable}-service"
            }
            if candidates:
                claim_status = "stale_claim"
                target_node = f"worker:{sorted(candidates)[0]}"

        if claim_status and target_node:
            edges.append(
                {
                    "source": loc_id,
                    "target": target_node,
                    "kind": claim_status,
                }
            )

    return location_nodes, ai_nodes, edges


def _matrix_suite_nodes_and_edges() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not MATRIX_SUITES_YAML.exists():
        return [], []
    data = yaml.safe_load(MATRIX_SUITES_YAML.read_text(encoding="utf-8"))
    suites = (data or {}).get("suites") or []
    nodes = []
    edges = []
    for suite in suites:
        suite_id = f"suite:{suite.get('suite_id', suite.get('name', 'unknown'))}"
        nodes.append(
            {
                "id": suite_id,
                "type": "matrix_suite",
                "label": suite.get("name", suite.get("suite_id", "?")),
                "pillar": suite.get("pillar"),
                "steward_ai": suite.get("steward_ai"),
                "steward_location": suite.get("steward_location"),
                "matrix_count": len(suite.get("matrices") or []),
                "review_cadence": suite.get("review_cadence"),
                "next_review": suite.get("next_review"),
            }
        )
        steward_location = suite.get("steward_location")
        if steward_location:
            edges.append(
                {
                    "source": suite_id,
                    "target": f"location:{steward_location}",
                    "kind": "stewarded_by",
                }
            )
    return nodes, edges


def build_graph() -> dict[str, Any]:
    guard = _load_guard_module()
    compose = _compose_services()
    service_nodes = _build_service_nodes(compose)
    compose_names = {n["label"] for n in service_nodes}

    mounted = _mounted_routers_with_modules()
    router_nodes, dup_edges = _classify_mounted_routers(mounted, guard)
    removed_nodes, removed_edges = _removed_history_nodes_edges()
    location_nodes, ai_nodes, entity_edges = _entity_nodes_and_links(compose_names)
    suite_nodes, suite_edges = _matrix_suite_nodes_and_edges()

    nodes = service_nodes + router_nodes + removed_nodes + location_nodes + ai_nodes + suite_nodes
    edges = dup_edges + removed_edges + entity_edges + suite_edges

    classifications = [
        n.get("classification") for n in router_nodes + removed_nodes if n.get("classification")
    ]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "locations": len(location_nodes),
        "lead_ais": len(ai_nodes),
        "deployed_services": len(service_nodes),
        "mounted_routers": len(router_nodes),
        "matrix_suites": len(suite_nodes),
        "needs_modularization": classifications.count("needs_modularization"),
        "confirmed_separate_features": classifications.count("confirmed_separate_features"),
        "bridged": classifications.count("bridged"),
        "unreasoned_duplicate_risk": classifications.count("unreasoned_duplicate_risk"),
        "core_load_bearing": classifications.count("core_load_bearing"),
        "no_worker_exists": classifications.count("no_worker_exists"),
        "safe_duplicate_removed": classifications.count("safe_duplicate_removed"),
        "stale_claims": sum(1 for e in entity_edges if e["kind"] == "stale_claim"),
    }

    return {"summary": summary, "nodes": nodes, "edges": edges}


def render_html(graph: dict[str, Any]) -> str:
    template = (Path(__file__).resolve().parent / "_topology_map_template.html").read_text(
        encoding="utf-8"
    )
    payload = json.dumps(graph, indent=None, separators=(",", ":"))
    # The HTML parser ends a <script> element on a literal "</script"
    # substring regardless of the element's `type` attribute, so this is
    # required even though the template already reads the payload via a
    # non-executable script[type=application/json] block rather than
    # interpolating it into a JS statement directly. Graph data ultimately
    # comes from repo content (compose service names, entity/router labels,
    # YAML-sourced suite names) that isn't expected to contain this, but
    # nothing enforces that, so escape defensively rather than assume it.
    payload = payload.replace("</script", "<\\/script")
    return template.replace("__TOPOLOGY_GRAPH_JSON__", payload)


def main() -> int:
    graph = build_graph()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    OUTPUT_HTML.write_text(render_html(graph), encoding="utf-8")

    s = graph["summary"]
    print(
        f"build_topology_map OK — {s['total_nodes']} nodes, {s['total_edges']} edges "
        f"({s['locations']} locations, {s['lead_ais']} lead AIs, "
        f"{s['deployed_services']} deployed services, {s['mounted_routers']} mounted "
        f"routers, {s['matrix_suites']} matrix suites). "
        f"Flags: {s['needs_modularization']} needs-modularization, "
        f"{s['unreasoned_duplicate_risk']} unreasoned-duplicate-risk, "
        f"{s['stale_claims']} stale entity claims."
    )
    print(f"Wrote {OUTPUT_JSON.relative_to(ROOT)} and {OUTPUT_HTML.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

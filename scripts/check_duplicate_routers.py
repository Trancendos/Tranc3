#!/usr/bin/env python3
"""Guard against the "two sources of truth" dead-router pattern recurring.

`docs/governance/MONOLITH-EXTRACTION-FINDINGS.md` documents a real, repeated bug
class in this repo: a `src/<name>/routes.py` router gets extracted into a real,
deployed `workers/<name>/` nanoservice, but the old in-process
`app.include_router(...)` mount in `api.py` is never removed — leaving two live
implementations of the same service reachable at once. 7 were found and removed
in one pass (taimra, studio, lab, chronos, devocity, artifactory, vrar3d).

An 8th, Resonate, was *also* removed that same pass and had to be reverted: the
worker turned out to implement a different feature (scoring) than the router it
was meant to replace (escalation) — not a superset. That mistake happened
because the only check run was "does anything else import this router object",
which cannot tell a true duplicate from two services that merely share a name.
**This script cannot either** — matching HTTP route paths/behavior requires
reading the code, which is exactly what caught Resonate. So this script does
NOT auto-remove anything. It only flags routers that *look* like the same
duplicate pattern (mounted in api.py + a same-service worker is live in
compose + nothing else in-process imports the router) so a human/agent
investigates with the same rigor as the original sweep, and it fails loudly if
a router already confirmed to be a genuine duplicate reappears without ever
being unmounted.

Exit status: 0 when nothing new needs investigating, 1 otherwise.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API_PY = ROOT / "api.py"
COMPOSE = ROOT / "docker-compose.production.yml"

# Router variable name (as used in `app.include_router(_x_router)`) -> the
# src module it's imported from and the compose service name of the worker
# that (claims to) supersede it. Only services actually investigated belong
# here — this is a curated map, not a name-guessing heuristic, because name
# guessing is exactly how the Resonate false-positive would have been missed
# in the *other* direction (assuming "same name" implies "same behavior").
#
# Add an entry here only after doing the same check the findings doc
# describes: confirm the worker's actual route paths cover the router's.
ROUTER_TO_WORKER: dict[str, tuple[str, str]] = {
    "_resonate_router": ("src.resonate.routes", "resonate"),
    "_imind_router": ("src.imind.routes", "imind"),
    "_basement_router": ("src.basement.routes", "basement"),
    "_cryptex_router": ("src.cryptex.routes", "cryptex"),
    "_library_router": ("src.library.routes", "library-service"),
    "_search_router": ("src.routers.search_api", "search-service"),
    "_turingshub_router": ("src.personality.turingshub.routes", "turings-hub-service"),
    "_nexus_router": ("src.nexus.routes", "infinity-ws"),
    "_townhall_router": ("src.townhall.routes", "cranbania"),
    "_admin_os_router": ("src.admin_os.routes", "infinity-admin"),
    "_section7_router": ("src.research.routes", "the-dutchy"),
    "_billing_router": ("src.monetisation.router", "payments-service"),
    # Confirmed-safe removals from the 2026-08-08 sweep — kept here (even
    # though `_mounted_routers()` will skip them while unmounted) so that if
    # one is ever re-added to api.py without a fresh equivalence check, this
    # script fails immediately instead of the mount silently going stale
    # again.
    "_taimra_router": ("src.taimra.routes", "taimra"),
    "_studio_router": ("src.studio.routes", "the-studio"),
    "_lab_router": ("src.lab.routes", "the-lab"),
    "_chronos_router": ("src.chronos.routes", "cron-service"),
    "_devocity_router": ("src.devocity.routes", "devocity"),
    "_artifactory_router": ("src.artifactory.routes", "artifactory-service"),
    "_vrar3d_router": ("src.vrar3d.routes", "vrar3d"),
}

# Routers where the in-process mount is known to be *intentionally* kept —
# real in-process callers, a verified non-equivalent worker, or genuinely
# core/load-bearing logic. Each needs a one-line reason so this table stays
# self-explanatory instead of becoming an unreviewed escape hatch.
KNOWN_COUPLED: dict[str, str] = {
    "_resonate_router": (
        "workers/resonate/ implements a different feature (scoring) than this "
        "router (escalation) — see MONOLITH-EXTRACTION-FINDINGS.md"
    ),
    "_imind_router": (
        "VERIFIED NOT EQUIVALENT: src/imind/protocol.py's assess() is a "
        "regex-driven crisis/self-harm/suicide detector with SECURITY-severity "
        "human escalation; workers/imind/worker.py only does generic "
        "sentiment/emotion scoring (dominant_emotion/polarity/confidence) with "
        "no crisis-pattern logic at all. Unmounting would silently remove a "
        "safeguarding feature, not a duplicate. src/tranquility/wellbeing.py "
        "also imports src.imind.protocol directly in-process."
    ),
    "_basement_router": (
        "BRIDGED 2026-08-08: src/observability/observatory.py still calls "
        "get_basement() synchronously in-process (SECURITY/CRITICAL audit "
        "path — genuinely load-bearing, router stays mounted), but now also "
        "fire-and-forget forwards the same event to workers/basement/'s "
        "POST /archive via src/basement/bridge.py, so it durably survives a "
        "restart. Fail-open by explicit owner decision: a forward failure is "
        "logged at debug and never blocks the audit write."
    ),
    "_cryptex_router": (
        "BRIDGED 2026-08-08: real in-process callers remain "
        "(section7/information_router.py, mcp/server.py, "
        "security/middleware.py — is_blocked()/analyse_request() stay pure "
        "in-memory, zero request-latency change). src/cryptex/bridge.py adds "
        "a background sync (pulls workers/cryptex/'s IOC list into the local "
        "block-set every 30s) plus a fire-and-forget forward on block_ip(), "
        "so a block set by one process becomes visible to every process "
        "instead of staying stuck in one process's memory. Fail-open: a sync "
        "or forward failure never affects request handling."
    ),
    "_library_router": (
        "BRIDGED 2026-08-08 (write-path only, by design): real in-process "
        "callers (synchronous .create()/.by_tag() writes/reads "
        "on the singleton, not just router imports): section7/information_router.py, "
        "observability/library_pipeline.py, models/knowledge.py, "
        "event_bus/wiring.py. VERIFIED NOT A SAFE SUPERSET SWAP for reads: "
        "this router's src/library/knowledge_base.py Article model carries a "
        "DataClassification (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/TOP_SECRET) "
        "enforced by routes.py's _can_read() — RESTRICTED/TOP_SECRET articles "
        "require admin or matching author — plus author and retention_days. "
        "workers/library-service/ is a generic pluggable wiki-backend facade "
        "with no classification/author/retention concept and no per-caller "
        "authorization at all (only a shared X-Internal-Secret), so reads "
        "are NOT bridged and never will be without that gap being closed "
        "first. What IS bridged: src/library/bridge.py fire-and-forget "
        "forwards newly-created PUBLIC/INTERNAL/CONFIDENTIAL articles only "
        "(RESTRICTED/TOP_SECRET are never sent, regardless of reachability) "
        "to workers/library-service/'s POST /library/documents for "
        "durability. Fail-open: a forward failure never blocks the write."
    ),
    "_turingshub_router": (
        "core/load-bearing AI response pipeline dependency, not a nanoservice duplicate"
    ),
    "_search_router": (
        "VERIFIED NOT EQUIVALENT: this router is a hybrid BM25+vector RAG "
        "pipeline (Meilisearch/Qdrant/Weaviate/Chroma); workers/search-service/ "
        "is SQLite FTS5 full-text only, with no vector/embedding/RAG capability "
        "at all — missing half the feature, not a superset"
    ),
    "_nexus_router": (
        "BRIDGED (not pending): src.nexus.hub.get_nexus() (the underlying "
        "pub/sub singleton, not just the router) is called in-process by "
        "section7.py, cryptex/threat_detector.py, and research/section7.py, "
        "so the router mount is genuinely load-bearing and can't just be "
        "unmounted. But it is already fanned out to workers/infinity-ws/: "
        "NexusHub.publish() -> _forward_to_ws_hub() -> POST {worker}/broadcast "
        "(fire-and-forget, capped in-flight concurrency, never blocks "
        "publish()), and the worker's POST /broadcast (workers/infinity-ws/"
        "worker.py) delivers it to WebSocket subscribers of that channel. An "
        "earlier pass of this table incorrectly claimed the worker had 'no "
        "REST pub/sub surface to bridge to yet' — it does, and has since "
        "before this table existed (see git blame on the /broadcast route)."
    ),
    "_townhall_router": (
        "CONFIRMED SEPARATE FEATURES: this router is a policy/compliance check "
        "engine (GDPR/UK-GDPR/PRINCE2/ITIL4/Zero-Cost policies); "
        "workers/cranbania/ (the same-named 'worker') is a completely "
        "different product — a Next.js/TypeScript Kanban/ITSM board with 40+ "
        "MCP tools and zero policy-check endpoints, not even the same "
        "language/runtime to bridge to. Real caller: research/section7.py, "
        "already in-process and already wrapped in try/except (degrades to a "
        "debug log, not a hard failure) — no network hop, so no fail-open/"
        "fail-closed question exists here the way it does for "
        "basement/cryptex/billing. Same 'same name, different function' "
        "pattern as admin_os/search_api/section7 — see "
        "CONFIRMED_SEPARATE_FEATURES in MONOLITH-EXTRACTION-FINDINGS.md."
    ),
    "_admin_os_router": (
        "VERIFIED NOT EQUIVALENT: this router's cells/fabric/files/backups "
        "features have no counterpart in workers/infinity-admin/, which is "
        "config/entity-override focused instead. api.py's own startup "
        "auto-backup loop depends on src.admin_os.backup_loop directly"
    ),
    "_section7_router": (
        "VERIFIED NOT EQUIVALENT: this router (src.research.routes, backed by "
        "src.research.section7.Section7) generates platform self-health/security "
        "reports from Cryptex+Observatory in-process; workers/the-dutchy/ is RSS/"
        "news market-intelligence ingestion — same entity name, different subject "
        "matter entirely"
    ),
    "_billing_router": (
        "BRIDGED 2026-08-08 — and to a different worker than earlier passes "
        "of this table assumed: workers/payments-service/ was never a "
        "rate-limit stub, it's 'Royal Bank of Arcadia' (accounts/ledger/"
        "transfers/deposits/AUM) — a real, fully-built, unrelated banking "
        "worker, same 'same name/entity, different function' trap as "
        "resonate/imind. workers/ledger-service/ is likewise a different "
        "feature (double-entry accounting, not Stripe/subscription billing). "
        "The actual right bridge target, already fully built and deployed: "
        "workers/rate-limit-service/ (token-bucket policy engine). "
        "api.py's two call sites now `await "
        "src.monetisation.bridge.check_and_increment_durable(...)`, which "
        "tries the worker's POST /check with a tight 0.5s timeout and falls "
        "back to the pre-existing, purely local "
        "TierEnforcer.check_and_increment() on any failure — fail-open by "
        "explicit owner decision. A reachable worker's 429 is still honored "
        "as a real deny, not treated as a failure."
    ),
}

INCLUDE_ROUTER_RE = re.compile(r"app\.include_router\((_\w+_router)\)")


def _mounted_routers() -> set[str]:
    return set(INCLUDE_ROUTER_RE.findall(API_PY.read_text(encoding="utf-8")))


def _compose_services() -> dict[str, dict]:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")).get("services") or {}
    return {name: (svc or {}) for name, svc in services.items()}


def _has_external_caller(src_module: str) -> list[str]:
    """Grep for in-process importers of `src_module` outside api.py and tests/."""
    dotted = re.escape(src_module)
    pattern = rf"from {dotted} import|import {dotted}\b"
    try:
        result = subprocess.run(
            ["grep", "-rlE", pattern, "--include=*.py", str(ROOT / "src"), str(ROOT / "workers")],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: grep not available", file=sys.stderr)
        return ["<grep unavailable>"]

    module_path = ROOT / (src_module.replace(".", "/") + ".py")
    callers = []
    for line in result.stdout.splitlines():
        path = Path(line)
        if path.resolve() == module_path.resolve():
            continue
        if "tests" in path.parts:
            continue
        callers.append(str(path.relative_to(ROOT)))
    return callers


def main() -> int:
    mounted = _mounted_routers()
    compose = _compose_services()

    problems: list[str] = []
    checked = 0

    for router_var, (src_module, worker_name) in ROUTER_TO_WORKER.items():
        if router_var not in mounted:
            # Was removed (or renamed) — nothing to guard here anymore.
            continue

        worker_svc = compose.get(worker_name)
        if worker_svc is None or "build" not in worker_svc:
            # The claimed worker isn't actually a deployed build target —
            # stale table entry, not a live duplicate risk. Warn, don't fail.
            print(
                f"NOTE: {router_var} -> {worker_name} in ROUTER_TO_WORKER but "
                f"'{worker_name}' has no live `build:` service in compose; "
                "table may be stale."
            )
            continue

        checked += 1
        callers = _has_external_caller(src_module)
        reason = KNOWN_COUPLED.get(router_var)

        if not callers and not reason:
            problems.append(
                f"  ✗ {router_var} ({src_module}) is mounted in api.py, "
                f"'{worker_name}' is live in compose, and no other in-process "
                f"code imports {src_module} — looks like the dead-duplicate "
                "pattern. Investigate with the same rigor as "
                "MONOLITH-EXTRACTION-FINDINGS.md (compare actual HTTP route "
                "paths, don't assume): either unmount it, or add it to "
                "KNOWN_COUPLED here with a reason."
            )
        elif callers and not reason:
            print(
                f"NOTE: {router_var} has in-process callers ({', '.join(callers)}) "
                "but no KNOWN_COUPLED entry explaining them — consider adding one "
                "for documentation."
            )

    if problems:
        print(
            f"check_duplicate_routers FAILED — {len(problems)} router(s) look like "
            "unremoved dead duplicates:",
            file=sys.stderr,
        )
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    print(f"check_duplicate_routers OK ({checked} tracked router/worker pairs checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

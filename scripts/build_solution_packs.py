#!/usr/bin/env python3
"""Generate a solution strategy pack per platform Location.

One markdown pack per entry in PLATFORM_ENTITIES (43 Locations), written to
docs/solution-packs/. Every pack carries the same section structure so packs
are comparable side by side, plus an index with the prioritisation grid.

PROVENANCE — this matters more than the volume of output.

Each pack separates two kinds of content and labels them, because a pack that
blends verified repo facts with generated scaffolding is worse than useless:
it launders invention into the appearance of record.

  DERIVED   Read from a register or the filesystem. Verifiable — the pack
            names the source so any claim can be checked. Covers identity,
            pillar, tier, agents, bots, abilities, port, code path, compose
            service, Traefik route, OSS foundation, status, and the debt items
            that come from real findings.

  SCAFFOLD  Generated starting points shaped by the derived facts — epics,
            stories, wireframes, schemas, design direction. These are drafts
            for a human to accept or replace, never a description of what
            exists. Marked inline so nobody mistakes a proposal for a record.

Prioritisation deliberately does NOT collapse to a single score. A common
pattern (attractiveness x execution-probability) double-counts risk: the same
regulatory and feasibility factors appear inside both terms, so risky work is
penalised twice and the ranking drifts toward low-value, low-risk items. Two
independent axes are kept instead — Criticality (what depends on this) and
Readiness (how much already exists) — which yields a quadrant that answers a
real question ("what is important and nearly done?") without inventing a
number nothing can validate.

Usage:
    python3 scripts/build_solution_packs.py [--check]

    --check  Regenerate into a temp dir and diff; non-zero exit if the
             committed packs are stale. Intended for CI.
"""

from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import statistics
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "docs" / "solution-packs"
CLAUDE_MD = ROOT / "CLAUDE.md"
COMPOSE = ROOT / "docker-compose.production.yml"


# ─────────────────────────────────────────────────────────────────────────────
# Joins against the real registers
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Joined:
    """Everything derivable about one Location, with its source named."""

    status: str = ""
    foundation: str = ""
    role: str = ""
    oss_repo: str = ""
    oss_stars: str = ""
    oss_licence: str = ""
    compose_service: str = ""
    traefik_rule: str = ""
    #: The router's name in compose, and its stripprefix middleware if any.
    #: The scaffold below uses these rather than the Location's slug: the two
    #: differ for eight Locations (`the-ice-box` vs `ice-box-service`,
    #: `fabulousa` vs `fabulousa-service`, …), and a template built on the
    #: slug wires a middleware to a router that does not exist.
    traefik_router: str = ""
    traefik_strip: str = ""
    #: The build context and Dockerfile compose actually uses. Inferring the
    #: context from the worker directory was wrong for every service built
    #: with `context: .` — ice-box's Dockerfile COPYs `src/`, so the inferred
    #: `./workers/ice-box-service` context would fail the build outright.
    build_context: str = ""
    build_dockerfile: str = ""
    compose_port: str = ""
    volumes: list[str] = None
    priority: str = ""
    path_exists: bool = False
    py_files: int = 0
    test_files: int = 0

    def __post_init__(self) -> None:
        if self.volumes is None:
            self.volumes = []


def parse_claude_md() -> tuple[dict, dict, dict]:
    md = CLAUDE_MD.read_text(encoding="utf-8")

    entity = {}
    for name, lead, role, status, foundation in re.findall(
        r"^\| \*\*(.+?)\*\* \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$", md, re.M
    ):
        entity[name.strip()] = {
            "lead": lead.strip(),
            "role": role.strip(),
            "status": status.strip(),
            "foundation": foundation.strip(),
        }

    priority = {}
    for svc, port, prio, path, desc in re.findall(
        r"^\| ([a-z0-9-]+) \| (\d+) \| (P\d|—) \| (.*?) \| (.*?) \|$", md, re.M
    ):
        priority[svc] = {
            "port": port,
            "priority": prio,
            "path": path.strip(),
            "desc": desc.strip(),
        }

    oss: dict[str, list[dict]] = {}
    current = None
    for line in md.splitlines():
        m = re.match(r"^\| \*\*(.+?)\*\* \| ([\w\-./]+) \| ([\dK.]+) \| (.+?) \|$", line)
        if m:
            current = m.group(1).strip()
            oss.setdefault(current, []).append(
                {"repo": m.group(2), "stars": m.group(3), "licence": m.group(4).strip()}
            )
            continue
        m2 = re.match(r"^\| (?!\*\*)(.+?) \| ([\w\-./]+) \| ([\dK.]+) \| (.+?) \|$", line)
        if m2 and current and m2.group(1).strip() == current:
            oss[current].append(
                {"repo": m2.group(2), "stars": m2.group(3), "licence": m2.group(4).strip()}
            )
    return entity, priority, oss


def parse_compose() -> dict:
    """Extract per-service compose facts without a YAML round-trip.

    The file uses anchors/merge keys that a naive safe_load flattens, losing
    which values were explicit. Line scanning keeps the authored intent.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    services: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^  ([a-z0-9][a-z0-9_-]*):\s*$", line)
        if m:
            current = m.group(1)
            services[current] = {
                "traefik": "",
                "router": "",
                "strip": "",
                "port": "",
                "context": "",
                "dockerfile": "",
                "volumes": [],
            }
            continue
        if not current:
            continue
        if "rule=" in line and "routers." in line:
            services[current]["traefik"] = line.split("rule=", 1)[1].strip().rstrip('"')
            router = re.search(r"routers\.([A-Za-z0-9_.-]+)\.rule", line)
            if router:
                services[current]["router"] = router.group(1)
        ctx = re.match(r"^\s+context:\s*(\S+)\s*$", line)
        if ctx and not services[current]["context"]:
            services[current]["context"] = ctx.group(1)
        dkf = re.match(r"^\s+dockerfile:\s*(\S+)\s*$", line)
        if dkf and not services[current]["dockerfile"]:
            services[current]["dockerfile"] = dkf.group(1)
        strip = re.search(r"middlewares\.([A-Za-z0-9_.-]+)\.stripprefix\.prefixes=(\S+)", line)
        if strip:
            services[current]["strip"] = f"{strip.group(1)}|{strip.group(2).rstrip(chr(34))}"
        pm = re.search(r'^\s+- "(\d+):(\d+)"', line)
        if pm:
            services[current]["port"] = pm.group(1)
        pe = re.search(r"^\s+- PORT=(\d+)", line)
        if pe and not services[current]["port"]:
            services[current]["port"] = pe.group(1)
        vm = re.search(r"^\s+- ([a-z0-9-]+-data):(\S+)", line)
        if vm:
            services[current]["volumes"].append(f"{vm.group(1)} → {vm.group(2)}")
    return services


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s


def join_entity(name: str, ent, entity_md, priority_md, oss_md, compose) -> Joined:
    j = Joined()
    meta = entity_md.get(name, {})
    j.status = meta.get("status", "")
    j.foundation = meta.get("foundation", "")
    j.role = meta.get("role", "")

    for o in oss_md.get(name, [])[:1]:
        j.oss_repo, j.oss_stars, j.oss_licence = o["repo"], o["stars"], o["licence"]

    # compose service: prefer the directory name from worker_path
    cand = []
    if ent.worker_path:
        cand.append(Path(ent.worker_path.rstrip("/")).name)
    cand.append(slug(name))
    for c in cand:
        if c in compose:
            j.compose_service = c
            j.traefik_rule = compose[c]["traefik"]
            j.traefik_router = compose[c]["router"]
            j.traefik_strip = compose[c]["strip"]
            j.build_context = compose[c]["context"]
            j.build_dockerfile = compose[c]["dockerfile"]
            j.compose_port = compose[c]["port"]
            j.volumes = compose[c]["volumes"]
            break

    if j.compose_service in priority_md:
        j.priority = priority_md[j.compose_service]["priority"]

    if ent.worker_path:
        p = ROOT / ent.worker_path
        j.path_exists = p.exists()
        if p.is_dir():
            j.py_files = len(list(p.rglob("*.py")))
            j.test_files = len(list(p.rglob("test_*.py")))
        elif p.is_file():
            j.py_files = 1
    return j


# ─────────────────────────────────────────────────────────────────────────────
# Prioritisation — two independent axes, deliberately not multiplied
# ─────────────────────────────────────────────────────────────────────────────


def build_dependency_index(entities) -> dict[str, int]:
    """In-degree over the `primes` graph: who depends on whom.

    Each Location names the Prime AIs it answers to. Resolving those names back
    to the Locations that own them turns the registry into a real dependency
    graph — and it resolves completely (no orphan Prime names), so the in-degree
    is a fact about the estate rather than an inference. Luminous carries 11
    dependents, which is why an outage there is not a local event.
    """
    owner = {e.lead_ai: n for n, e in entities.items()}
    for n, e in entities.items():
        for alt in e.lead_ais:
            owner.setdefault(alt, n)
    deps: dict[str, int] = dict.fromkeys(entities, 0)
    for n, e in entities.items():
        for prime in e.primes:
            target = owner.get(prime)
            if target and target != n:
                deps[target] += 1
    return deps


def criticality(ent, j: Joined, dependents: int = 0) -> tuple[int, list[str]]:
    """What depends on this Location. 0-10, with the reasons that set it."""
    score, why = 0, []
    prio_weight = {"P0": 5, "P1": 4, "P2": 2, "P3": 1, "—": 3}
    if j.priority:
        w = prio_weight.get(j.priority, 1)
        score += w
        why.append(f"worker-map priority {j.priority} (+{w})")
    if dependents:
        w = min(dependents, 4)
        score += w
        why.append(f"{dependents} Location(s) name this one's AI as their Prime (+{w})")
    if ent.primes:
        score += 1
        why.append(f"answers to {len(ent.primes)} Prime(s) (+1)")
    if len(ent.lead_ais) > 1:
        score += 1
        why.append(f"{len(ent.lead_ais)} Lead AIs — multi-team Location (+1)")
    if ent.pillar.value in ("Security", "Architectural", "DevOps"):
        score += 2
        why.append(f"{ent.pillar.value} pillar — platform-wide blast radius (+2)")
    if j.traefik_rule:
        score += 1
        why.append("externally routed via Traefik (+1)")
    return min(score, 10), why


def readiness(ent, j: Joined) -> tuple[int, list[str]]:
    """How much already exists. 0-10, with the reasons that set it."""
    score, why = 0, []
    if "✅" in j.status:
        score += 3
        why.append("status ✅ in CLAUDE.md (+3)")
    elif "🔧" in j.status:
        score += 1
        why.append("status 🔧 partial/migrating (+1)")
    if j.path_exists:
        score += 2
        why.append(f"code path `{ent.worker_path}` exists on disk (+2)")
    # The reasons name the threshold each point was earned at, not the exact
    # file count. The score buckets at 1 and 3 files, so an exact count adds
    # nothing a reader can act on — and it made every pack stale on any commit
    # that added a file anywhere beneath a Location's path. A generated
    # document that churns on facts which do not change its meaning trains
    # people to regenerate without reading, which is how real drift gets
    # committed unseen.
    if j.py_files >= 3:
        score += 2
        why.append("three or more Python files present (+2)")
    elif j.py_files:
        score += 1
        why.append("at least one Python file present (+1)")
    if j.compose_service:
        score += 2
        why.append(f"compose service `{j.compose_service}` defined (+2)")
    if j.test_files:
        score += 1
        why.append("at least one test file present (+1)")
    return min(score, 10), why


def quadrant(c: int, r: int, c_split: float, r_split: float) -> str:
    """Classify against each axis's own median, not a fixed absolute.

    The two axes do not share a scale — across the 43 Locations criticality runs
    1-10 with a median near 3, readiness 3-10 with a median near 8. A single
    fixed threshold would put almost everything in one bucket and tell you
    nothing. Splitting at each axis's median makes the grid comparative: a
    "Defer" is below *this estate's own middle*, not unimportant in absolute
    terms. The split therefore moves as the estate does, which is the point.
    """
    # Strictly above: scores are coarse integers and tie heavily (17 of 43
    # Locations score exactly the criticality median), so `>=` would sweep every
    # tie into the upper bucket and rebuild the same useless single-bucket grid
    # that a fixed threshold produced. Sitting *at* the median is not above it.
    hi_c, hi_r = c > c_split, r > r_split
    if hi_c and hi_r:
        return "Finish first — above-median dependency, above-median readiness"
    if hi_c and not hi_r:
        return "Invest — above-median dependency, below-median readiness"
    if not hi_c and hi_r:
        return "Harvest — built out, below-median dependency; polish and ship"
    return "Defer — below median on both axes"


# ─────────────────────────────────────────────────────────────────────────────
# Pack rendering
# ─────────────────────────────────────────────────────────────────────────────


def worker_serves_prefix(build_context: str, prefix: str) -> bool | None:
    """Does the worker itself serve paths under `prefix`?

    `None` when it cannot be determined — a third-party image (Forgejo, n8n,
    Paperless) with no Python in the build context. Unknown is reported as
    unknown; the whole point of this function is that absence of evidence was
    previously reported as evidence of design.

    Why this exists
    ---------------
    An earlier version of this generator saw "no stripprefix middleware" and
    wrote, in 20-odd packs, that the omission was **deliberate** — that the
    worker served the prefixed paths itself and adding the middleware would
    break it. For most of them the opposite is true: `workers/cryptex/router.py`
    registers `/scan`, `/intel`, `/engines` with no prefix, compose routes
    ``PathPrefix(`/cryptex`)`` with no strip, so `/cryptex/scan` reaches the
    worker unchanged and 404s. The absence was a defect, and the pack called
    it a design decision — inverting a real routing fault into a reassurance,
    in the document an implementer is told to trust.

    So intent is no longer inferred from absence. This checks the one thing
    that is checkable: whether any route or router prefix in the worker's own
    source begins with the external prefix.
    """
    directory = Path(build_context.lstrip("./")) if build_context else None
    if directory is None or not directory.is_dir():
        return None
    sources = list(directory.glob("*.py")) + list(directory.glob("*/*.py"))
    if not sources:
        return None  # a third-party image; its routing is not ours to read
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sources)
    return f'"{prefix}' in text or f"'{prefix}" in text


def render_pack(
    name: str, ent, j: Joined, crit, ready, quad, dependents, c_split, r_split, priority_md
) -> str:
    c_score, c_why = crit
    r_score, r_why = ready
    tier = _tier(ent.lead_ai)
    job = _job(name)
    port = ent.worker_port or (int(j.compose_port) if j.compose_port else None)
    agents = [ent.agent_alpha, ent.agent_beta]
    bots = [ent.bot_01, ent.bot_02, ent.bot_03, ent.bot_04]
    sl = slug(name)
    # Routing names come from compose when compose has them. The Location's
    # slug and its deployed router name differ for several Locations —
    # `the-ice-box` vs `ice-box-service`, `fabulousa` vs `fabulousa-service`,
    # `/the-warp-tunnel` vs `/warp-tunnel` — and a scaffold built on the slug
    # attaches a middleware to a router that does not exist, or strips a
    # prefix the router never matches. Both produce a 404 that looks like a
    # code fault, which is the exact failure this pack warns about elsewhere.
    router_name, strip_name, route_prefix = route_names(j, sl)
    dockerfile = j.build_dockerfile or "Dockerfile"

    L: list[str] = []
    add = L.append

    add(f"# Solution Pack — {name}")
    add("")
    add(f"> **{ent.pid} · {ent.aid} · {ent.pillar.value} pillar**")
    add(">")
    add("> Generated by `scripts/build_solution_packs.py`. **DERIVED** sections are read")
    add("> from the registers named inline and are verifiable. **SCAFFOLD** sections are")
    add("> generated starting points shaped by those facts — drafts to accept or replace,")
    add("> not descriptions of what exists.")
    add("")

    # 1 ─ What it is
    add("## 1. What this is — DERIVED")
    add("")
    add("| Field | Value | Source |")
    add("|---|---|---|")
    add(f"| Location | {name} | `src/entities/platform.py` |")
    add(f"| Product ID | `{ent.pid}` | `_assign_ids()` |")
    add(f"| Lead AI | {ent.lead_ai} (`{ent.aid}`) | `src/entities/platform.py` |")
    if len(ent.lead_ais) > 1:
        add(f"| All Lead AIs | {', '.join(ent.lead_ais)} | `lead_ais` |")
    add(f"| Base model tier | {tier} | `get_orchestration_tier()` |")
    add(
        f"| Job Description | {job or '_not assigned_'} | `docs/governance/LOCATION-FUNCTIONS.md` |"
    )
    add(f"| Pillar | {ent.pillar.value} | `Pillar` enum |")
    add(f"| Reports to Prime(s) | {', '.join(ent.primes) or '_none_'} | `primes` |")
    add(f"| Status | {j.status or '_unlisted_'} | `CLAUDE.md` service table |")
    add(
        f"| Code path | `{ent.worker_path or '_none_'}`{' ✅ on disk' if j.path_exists else ' ⚠️ not found'} | filesystem |"
    )
    add(f"| Port | {port or '_unassigned_'} | compose / `worker_port` |")
    if j.compose_service:
        add(f"| Compose service | `{j.compose_service}` | `docker-compose.production.yml` |")
    if j.traefik_rule:
        add(f"| Traefik route | `{j.traefik_rule}` | compose labels |")
    if j.priority:
        add(f"| Rollout priority | {j.priority} | CLAUDE.md worker map |")
    if j.oss_repo:
        add(f"| OSS foundation | `{j.oss_repo}` ({j.oss_stars}★, {j.oss_licence}) | CLAUDE.md |")
    add("")
    add(f"**Role.** {j.role or ent.primary_function}")
    add("")

    # 2 ─ What it does
    add("## 2. What it does — DERIVED")
    add("")
    add(f"**Primary function.** {ent.primary_function}")
    add("")
    add("**Abilities**")
    for a in ent.abilities:
        add(f"- {a}")
    add("")
    add("**Operating modes**")
    add("")
    add(f"- *Online:* {ent.online_mode}")
    add(f"- *Offline:* {ent.offline_mode}")
    add("")
    add("The offline mode is a design constraint, not a footnote: it states what this")
    add("Location must still deliver when its upstreams are unreachable, and any")
    add("implementation that cannot honour it is incomplete regardless of test coverage.")
    add("")

    # 3 ─ Architectural requirements
    add("## 3. Architectural requirements — DERIVED constraints, SCAFFOLD targets")
    add("")
    add("**Hard constraints — these come from the estate, not from preference.**")
    add("")
    # DERIVED from compose where compose says; inferred only where it is
    # silent. Inferring it unconditionally produced a template that fails the
    # build for every service compose builds with `context: .` — ice-box's
    # Dockerfile COPYs `src/`, which a worker-directory context does not hold.
    ctx = j.build_context or (
        f"./{ent.worker_path.rstrip('/')}"
        if ent.worker_path and ent.worker_path.startswith("workers/")
        else "."
    )
    if ctx not in (".", "./") and ent.worker_path and ent.worker_path.startswith("workers/"):
        add(f"- **Build context is `{ctx}`**, so `src/` is *not* in the image. This Location")
        add("  cannot `from src.* import ...` — ported logic must be self-contained. This is the")
        add("  single most common cause of a worker that passes tests and dies in the container.")
    elif ent.worker_path and ent.worker_path.startswith("workers/"):
        add(f"- **Build context is `{ctx}`** (the repo root), so `src/` *is* in the image and")
        add("  this worker's Dockerfile may COPY from it. Narrowing the context to the worker")
        add("  directory would break the build — check the Dockerfile before changing it.")
    else:
        add(f"- Runs in-process under `api.py` (path `{ent.worker_path or 'n/a'}`), so it *may*")
        add("  import from `src/` — but that also means it shares the backend's failure domain.")
    add("- **SQLite over shared state** — each worker owns its own database file (principle 1).")
    add("- **In-memory token-bucket rate limiting** — no external KV (principle 2).")
    add("- **Zero-cost posture** — no paid dependency may be introduced without funding sign-off.")
    if j.traefik_rule and not j.traefik_strip:
        serves = worker_serves_prefix(j.build_context, route_prefix)
        if serves is True:
            add(f"- **No `stripprefix` on `{route_prefix}`, and none is needed** — verified:")
            add(f"  this worker's own source registers paths under `{route_prefix}`, so the")
            add("  prefix must reach it intact. Adding the middleware would break it.")
        elif serves is False:
            add(f"- **ROUTING DEFECT — `{route_prefix}` has no `stripprefix` and this worker")
            add("  does not serve the prefixed path.** Verified against its own source: every")
            add(f"  route it registers sits below `/`, not below `{route_prefix}`, so Traefik")
            add(f"  forwards `{route_prefix}/x` unchanged and the worker 404s on all of them.")
            add("  Either add a stripprefix middleware to the compose labels, or give the")
            add("  worker's router the prefix. **Fix this before building anything on it.**")
        else:
            add(f"- **No `stripprefix` on `{route_prefix}`, and this could not be verified** —")
            add("  the build context holds no Python to read (a third-party image). Confirm")
            add("  against that image's own routing before relying on either behaviour.")
    elif j.traefik_rule:
        add(
            f"- **Traefik `stripprefix` is mandatory** for `{route_prefix}` routing; "
            "without the middleware"
        )
        add("  the router matches and the worker 404s on every path. This has bitten the estate")
        add("  before (resonate, imind).")
    add("")
    add("**Non-functional targets — SCAFFOLD, set these against real measurements.**")
    add("")
    add("| Attribute | Starting target | Why this number needs replacing |")
    add("|---|---|---|")
    add("| Health endpoint | `GET /health` < 200 ms | compose healthcheck already polls it |")
    add("| p95 latency | < 500 ms | placeholder — no load profile exists yet |")
    add("| Availability | 99% single-node | one chassis; see `deploy/CITADEL_OPERATIONS.md` §9 |")
    add("| Data durability | volume-backed + off-box backup | snapshots are not backups |")
    add("")

    # 4 ─ Design schematic
    add("## 4. Design schematic — DERIVED topology")
    add("")
    add("```mermaid")
    add("flowchart LR")
    add("    C[Client] --> T[Traefik]" if j.traefik_rule else "    C[Client] --> A[api.py]")
    node = f"S[{name}<br/>{port or 'no port'}]"
    if j.traefik_rule:
        add(f"    T -->|/{sl}| {node}")
    else:
        add(f"    A --> {node}")
    add("    S --> DB[(SQLite<br/>own file)]")
    for p in ent.primes:
        add(f"    S -.reports.-> P[{p}]")
    add(f"    S --> AA[{agents[0].code_name}]")
    add(f"    S --> AB[{agents[1].code_name}]")
    for b in bots:
        add(f"    AA -.-> {b.code_name.replace('-', '')}[{b.code_name}]")
    add("    S --> OBS[The Observatory<br/>audit]")
    add("```")
    add("")

    # 5 ─ Blueprint
    add("## 5. Blueprint — SCAFFOLD")
    add("")
    add("| Layer | Component | Note |")
    add("|---|---|---|")
    add(
        f"| Ingress | {'Traefik → ' + sl if j.traefik_rule else 'in-process router'} | {j.traefik_rule or 'mounted in api.py'} |"
    )
    add("| API | FastAPI app | `/health`, `/status`, domain routes |")
    add(f"| Domain | {agents[0].code_name} + {agents[1].code_name} | the two Agents below |")
    add(f"| Automation | {', '.join(b.code_name for b in bots)} | the four Bots below |")
    add(
        f"| Persistence | SQLite | {', '.join(j.volumes) if j.volumes else 'volume not yet declared'} |"
    )
    add("| Observability | structured JSON + W3C trace | `src/observability/tracing.py` |")
    add("")

    # 6 ─ Storyboard + schema
    add("## 6. Storyboard and schema — SCAFFOLD")
    add("")
    add("A first-run journey, derived from the abilities above. Replace with the real")
    add("journey once a user has actually walked it.")
    add("")
    add("```")
    if not j.traefik_rule:
        arrival = "api.py routes"
    elif j.traefik_strip:
        arrival = f"Traefik strips {route_prefix}"
    else:
        # No middleware: the prefix reaches the worker unchanged. Whether that
        # works is section 3's verified finding, and this line must not
        # contradict it — the earlier version said "strips" regardless, so a
        # pack could declare a routing defect on one page and describe the
        # stripping that does not happen on the next.
        arrival = f"Traefik forwards {route_prefix} unchanged (no stripprefix)"
    add(f"1. Request arrives  →  {arrival}")
    add(f"2. {agents[0].code_name} — {agents[0].description}")
    add(f"3. {agents[1].code_name} — {agents[1].description}")
    add(f"4. Bots fire: {', '.join(b.code_name for b in bots)}")
    add("5. Result persisted to SQLite; event emitted to The Observatory")
    add("6. Response returned with trace_id for correlation")
    add("```")
    add("")
    add("**Proposed schema** — shaped by the abilities; not yet implemented.")
    add("")
    add("```sql")
    tbl = sl.replace("-", "_")
    add(f"CREATE TABLE IF NOT EXISTS {tbl}_records (")
    add("    id           INTEGER PRIMARY KEY AUTOINCREMENT,")
    add("    record_id    TEXT NOT NULL UNIQUE,")
    add("    actor        TEXT,")
    add("    payload      TEXT NOT NULL,        -- JSON")
    add("    state        TEXT NOT NULL DEFAULT 'new',")
    add("    created_at   REAL NOT NULL,")
    add("    updated_at   REAL")
    add(");")
    add(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_state ON {tbl}_records(state);")
    add("")
    add(f"CREATE TABLE IF NOT EXISTS {tbl}_audit (")
    add("    id           INTEGER PRIMARY KEY AUTOINCREMENT,")
    add("    record_id    TEXT NOT NULL,")
    add("    action       TEXT NOT NULL,")
    add("    actor        TEXT,")
    add("    at           REAL NOT NULL")
    add(");")
    add("```")
    add("")

    # 7 ─ Components
    add("## 7. Components — DERIVED")
    add("")
    add("**Agents (Tier 4)**")
    add("")
    add("| SID | Agent | Responsibility |")
    add("|---|---|---|")
    for a in agents:
        add(f"| `{a.sid}` | {a.code_name} | {a.description} |")
    add("")
    add("**Bots (Tier 5)**")
    add("")
    add("| NID | Bot | Responsibility |")
    add("|---|---|---|")
    for b in bots:
        add(f"| `{b.nid}` | {b.code_name} | {b.description} |")
    add("")
    if ent.agent_teams:
        add("**Per-Lead-AI agent teams** — this Location runs a dedicated pair per named AI.")
        add("")
        add("| Lead AI | Alpha | Beta |")
        add("|---|---|---|")
        for ai, pair in ent.agent_teams.items():
            add(f"| {ai} | {pair.alpha.code_name} | {pair.beta.code_name} |")
        add("")

    # 8 ─ Design direction
    add("## 8. Design direction — SCAFFOLD")
    add("")
    if j.oss_repo:
        add(f"**Foundation.** `{j.oss_repo}` ({j.oss_stars}★, {j.oss_licence}) is the vetted")
        add("starting point recorded in CLAUDE.md. Check the licence against the zero-cost")
        add("posture before adopting — self-host-free is not the same as permissive.")
    else:
        add("**Foundation.** No OSS foundation is recorded for this Location. Either one")
        add("should be chosen and added to CLAUDE.md, or the build-from-scratch decision")
        add("should be written down with its reasoning.")
    add("")
    add(f"**Interface tone.** {ent.pillar.value} pillar. Surface the two Agents as the")
    add("primary verbs and keep the four Bots as background automation the user never")
    add("has to name.")
    add("")

    # 9 ─ Templates
    add("## 9. Templates — SCAFFOLD")
    add("")
    add("**Health response** (matches `to_health_meta()`):")
    add("")
    add("```json")
    add("{")
    add(f'  "location": "{name}",')
    add(f'  "pillar": "{ent.pillar.value}",')
    add(f'  "lead_ai": "{ent.lead_ai}",')
    add(f'  "primes": {ent.primes},')
    add('  "status": "ok"')
    add("}")
    add("```")
    add("")
    add("**Compose service:**")
    add("")
    add("```yaml")
    add(f"  {j.compose_service or sl}:")
    add(f"    build: {{ context: {ctx}, dockerfile: {dockerfile} }}")
    add(f"    environment: [ PORT={port or 'TBD'} ]")
    add(f'    ports: [ "{port or "TBD"}:{port or "TBD"}" ]')
    if j.traefik_rule:
        add("    labels:")
        add(f'      - "traefik.http.routers.{router_name}.rule={j.traefik_rule}"')
        if j.traefik_strip:
            add(f'      - "traefik.http.routers.{router_name}.middlewares={strip_name}@docker"')
            add(
                f'      - "traefik.http.middlewares.{strip_name}.stripprefix.'
                f'prefixes={route_prefix}"'
            )
    add("```")
    add("")

    # 10 ─ Epics and stories
    add("## 10. Epics and stories — SCAFFOLD")
    add("")
    add("Sequenced against the readiness gaps below, so the first epic is whatever is")
    add("actually missing rather than a generic phase 1.")
    add("")
    epics = _epics(ent, j, name)
    for i, (title, stories) in enumerate(epics, 1):
        add(f"### Epic {i} — {title}")
        add("")
        for s in stories:
            add(f"- {s}")
        add("")

    # 11 ─ Technical debt
    add("## 11. Technical debt — DERIVED where evidenced")
    add("")
    debts = _debt(ent, j, name, port, priority_md)
    if debts:
        add("| Item | Evidence | Impact |")
        add("|---|---|---|")
        for d in debts:
            add(f"| {d[0]} | {d[1]} | {d[2]} |")
    else:
        add("No debt evidenced from the registers for this Location. That means nothing")
        add("was *found*, not that nothing exists — the scanners only see what is recorded.")
    add("")

    # 12 ─ Wireframe
    add("## 12. Wireframe — SCAFFOLD")
    add("")
    add("```")
    add("┌──────────────────────────────────────────────────────┐")
    add(f"│ {name[:36]:<36} {(ent.pid or ''):>15} │")
    add("├──────────────────────────────────────────────────────┤")
    add(f"│ {ent.primary_function[:52]:<52} │")
    add("├──────────────────────────────────────────────────────┤")
    for a in agents:
        add(f"│  ▸ {a.code_name[:24]:<24} {a.description[:24][:24]:<24}│")
    add("├──────────────────────────────────────────────────────┤")
    add(f"│  bots: {', '.join(b.code_name for b in bots)[:44]:<44} │")
    add("├──────────────────────────────────────────────────────┤")
    add(f"│  [ health ]  [ status ]  {('route /' + sl)[:26]:<26} │")
    add("└──────────────────────────────────────────────────────┘")
    add("```")
    add("")

    # 13 ─ Prioritisation
    add("## 13. Prioritisation — DERIVED")
    add("")
    add(f"**Criticality {c_score}/10 · Readiness {r_score}/10 → {quad}**")
    add("")
    add(f"Classified against the estate's own medians (criticality {c_split:g}, readiness")
    add(f"{r_split:g} across all 43 Locations), not a fixed threshold — the two axes do not")
    add("share a scale, so one absolute cut-off would bucket almost everything together.")
    add("")
    add("They are also kept separate rather than multiplied. Collapsing them would")
    add("double-count: status and dependency facts feed both terms, so the product")
    add("systematically ranks safe-and-unimportant above important-and-unfinished.")
    if dependents:
        add("")
        add(f"**{dependents} other Location(s) name this one's AI as their Prime.** An outage")
        add("here is not local.")
    add("")
    add("| Axis | Score | Reasons |")
    add("|---|---|---|")
    add(f"| Criticality | {c_score}/10 | {'; '.join(c_why) or 'no signals'} |")
    add(f"| Readiness | {r_score}/10 | {'; '.join(r_why) or 'no signals'} |")
    add("")

    # 14 ─ Documentation
    add("## 14. Documentation — DERIVED")
    add("")
    add(f"- `PLATFORM_ENTITIES.md` — canonical entry for {ent.pid}")
    add(f'- `src/entities/platform.py` — `PLATFORM_ENTITIES["{name}"]`')
    add("- `docs/governance/LOCATION-FUNCTIONS.md` — Job Description")
    add("- `docs/governance/TRANCENDOS-MODELS-MATRIX.md` — base tier and variants")
    if j.compose_service:
        add(f"- `docker-compose.production.yml` — service `{j.compose_service}`")
    if ent.worker_path:
        add(f"- `{ent.worker_path}` — implementation")
    add("- `compliance/magna-carta/compliance/sector_profiles.yaml` — sector activation")
    add("")
    return _document(L)


def route_names(j: "Joined", sl: str) -> tuple[str, str, str]:
    """(router, stripprefix middleware, path prefix) — from compose where it says.

    The Location's slug and its deployed router name differ for several
    Locations, and a scaffold built on the slug wires a middleware to a
    router that does not exist or strips a prefix the router never matches.
    Either way the worker 404s, which is the failure these packs warn about.
    """
    router = j.traefik_router or sl
    if j.traefik_strip:
        strip, prefix = j.traefik_strip.split("|", 1)
        return router, strip, prefix
    match = re.search(r"PathPrefix\(`([^`]+)`\)", j.traefik_rule or "")
    prefix = match.group(1) if match else f"/{sl}"
    return router, f"strip-{prefix.lstrip('/')}", prefix


def _epics(ent, j: Joined, name) -> list[tuple[str, list[str]]]:
    _, _, route_prefix = route_names(j, slug(name))
    e: list[tuple[str, list[str]]] = []
    if not j.path_exists:
        e.append(
            (
                "Stand up the service",
                [
                    f"As an operator, I can reach `GET /health` on {name} so the compose healthcheck passes.",
                    f"As a developer, `{ent.worker_path}` exists with a FastAPI app and Dockerfile.",
                    "As a reviewer, the worker imports nothing from `src/` (build-context constraint).",
                ],
            )
        )
    if not j.compose_service:
        e.append(
            (
                "Declare the deployment",
                [
                    f"As an operator, {name} has a `docker-compose.production.yml` service with an explicit `PORT`.",
                    "As an operator, a named volume backs the SQLite file so restarts do not lose state.",
                    "As an operator, a healthcheck polls `/health` and marks the container unhealthy on failure.",
                ],
            )
        )
    if j.traefik_rule and j.compose_service:
        if j.traefik_strip:
            criteria = [
                f"As a client, requests to `{route_prefix}` reach the worker "
                "with the prefix stripped.",
                "As a reviewer, a stripprefix middleware exists and is referenced by the router.",
            ]
        elif worker_serves_prefix(j.build_context, route_prefix) is True:
            criteria = [
                f"As a client, requests to `{route_prefix}` reach the worker with the "
                "prefix intact, which is what its own routes expect.",
                "As a reviewer, NO stripprefix middleware is attached — adding one "
                "would break every route.",
            ]
        else:
            # The acceptance criterion for a defect is the fix, not a
            # description of the broken state. Asking a reviewer to confirm a
            # middleware "exists" when section 3 has just proven it does not,
            # and that its absence 404s the service, is how a pack sends
            # somebody to re-add the thing it told them was deliberate.
            criteria = [
                f"As a client, requests to `{route_prefix}` reach a route the worker "
                "actually serves — today they do not, and this epic is that fix.",
                f"As an implementer, EITHER a stripprefix middleware for `{route_prefix}` "
                "is added to the compose labels, OR the worker's router is given the "
                "prefix. One of the two, not neither.",
                "As a reviewer, a request through Traefik returns something other than 404.",
            ]
        e.append(("Verify routing end to end", criteria))
    e.append(
        (
            "Implement the abilities",
            [f"As a user, I can exercise: {a.split(':')[0]}." for a in ent.abilities]
            + [f"As an auditor, every action emits an Observatory event carrying `{ent.pid}`."],
        )
    )
    if not j.test_files:
        e.append(
            (
                "Prove it works",
                [
                    f"As a maintainer, `tests/` covers {name}'s health, status and each ability.",
                    "As a maintainer, the offline mode above is tested, not assumed.",
                ],
            )
        )
    return e


def _rival_worker(ent, name, priority_md) -> str:
    """Detect a dedicated worker competing with the registered one.

    Several Locations record a *generic* infrastructure worker as their
    `worker_path` (Cryptex → rate-limit-service, The HIVE → queue-service,
    The Void → config-service, Section 7 → geo-service) while CLAUDE.md's
    worker map documents a *dedicated named* worker that also exists on disk.
    Both directories are real, so one of them is not the implementation — and
    the port, route and readiness in this pack follow whichever the registry
    names. Flagged rather than silently resolved: picking one is a decision for
    the estate, not a lookup.

    Detection reads the worker map's description column, which names the
    Location outright ("The HIVE — task queue / agent coordination"). An
    earlier version guessed at slug variants and missed Section 7 → the-dutchy
    and The Void → infinity-void entirely, because those names share no
    substring with their Location.
    """
    if not ent.worker_path or not ent.worker_path.startswith("workers/"):
        return ""
    registered = Path(ent.worker_path.rstrip("/")).name
    for svc, meta in priority_md.items():
        if svc == registered:
            continue
        desc = meta.get("desc", "")
        # match on the Location name at a word boundary in the description
        if (
            re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", desc)
            and (ROOT / "workers" / svc).is_dir()
        ):
            return svc
    return ""


def _debt(ent, j: Joined, name, port, priority_md) -> list[tuple[str, str, str]]:
    d: list[tuple[str, str, str]] = []
    rival = _rival_worker(ent, name, priority_md)
    if rival:
        d.append(
            (
                f"Two candidate implementations: registered `{ent.worker_path}` vs `workers/{rival}/`",
                "both directories exist on disk",
                "Registry and CLAUDE.md name different workers for this Location — "
                "port, route and readiness above follow the registered one",
            )
        )
    if ent.worker_path and not j.path_exists:
        d.append(
            (
                f"Registered path `{ent.worker_path}` does not exist",
                "filesystem check",
                "Registry claims an implementation that is not there",
            )
        )
    if ent.worker_port and j.compose_port and str(ent.worker_port) != j.compose_port:
        d.append(
            (
                f"Port mismatch: registry {ent.worker_port} vs compose {j.compose_port}",
                "`platform.py` vs compose",
                "Traffic may route to a port nothing is listening on",
            )
        )
    if not port:
        d.append(
            (
                "No port assigned",
                "`worker_port` is None and compose has none",
                "Not independently deployable",
            )
        )
    if j.compose_service and not j.traefik_rule:
        d.append(
            (
                "Compose service has no Traefik router",
                "compose labels",
                "Reachable inside the network only — no external route",
            )
        )
    if j.path_exists and not j.test_files:
        d.append(
            ("No test files under the code path", "filesystem check", "Regressions land silently")
        )
    if "🔧" in j.status:
        d.append(
            (
                f"Status is {j.status}",
                "CLAUDE.md service table",
                "Partial — not production-complete",
            )
        )
    if not j.oss_repo and ent.pillar.value == "Creativity":
        d.append(
            (
                "No OSS foundation recorded",
                "CLAUDE.md foundations table",
                "Build-vs-adopt decision is undocumented",
            )
        )
    return d


def _document(lines: list[str]) -> str:
    """Join rendered lines the way the repository's own hooks want them.

    Trailing whitespace and a trailing blank line are both fixed up by
    pre-commit, which would rewrite every generated pack the moment it ran and
    leave `--check` failing forever on a diff nobody wrote. A generator that
    disagrees with the formatter turns its own drift gate into noise, so the
    agreement is enforced here rather than remembered at each call site.
    """
    cleaned = [line.rstrip() for line in lines]
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned) + "\n"


def render_index(rows, c_split, r_split) -> str:
    L = ["# Solution Packs — index", ""]
    L += [
        f"One pack per Location ({len(rows)} total), generated by",
        "`scripts/build_solution_packs.py` from the platform registers.",
        "",
        "**Read the quadrant before the packs.** Criticality is what depends on a",
        "Location; Readiness is how much already exists. They are kept as two axes",
        "rather than multiplied into a single score, because the same status and",
        "dependency facts feed both — collapsing them would double-count and quietly",
        "rank safe, unimportant work above important, unfinished work.",
        "",
        f"Quadrants split at each axis's median across all {len(rows)} Locations "
        f"(criticality {c_split:g}, readiness {r_split:g}). The split is relative: "
        '"Defer" means below this estate\'s own middle, not unimportant.',
        "",
    ]
    order = {
        "Finish first — above-median dependency, above-median readiness": 0,
        "Invest — above-median dependency, below-median readiness": 1,
        "Harvest — built out, below-median dependency; polish and ship": 2,
        "Defer — below median on both axes": 3,
    }
    for q in sorted(order, key=lambda k: order[k]):
        sel = [r for r in rows if r["quadrant"] == q]
        if not sel:
            continue
        L.append(f"## {q}  ({len(sel)})")
        L.append("")
        L.append("| Location | PID | Pillar | Crit | Ready | Dependents | Port | Pack |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in sorted(sel, key=lambda x: (-x["crit"], -x["ready"], x["name"])):
            L.append(
                f"| {r['name']} | `{r['pid']}` | {r['pillar']} | {r['crit']}/10 | "
                f"{r['ready']}/10 | {r['deps']} | {r['port'] or '—'} | [pack]({r['file']}) |"
            )
        L.append("")
    return _document(L)


def build(out_dir: Path) -> list[dict]:
    from src.entities.platform import (  # noqa: E402
        PLATFORM_ENTITIES,
        get_job_description,
        get_orchestration_tier,
    )

    global _tier, _job
    _tier = lambda n: getattr(get_orchestration_tier(n), "value", str(get_orchestration_tier(n)))  # noqa: E731
    _job = get_job_description

    entity_md, priority_md, oss_md = parse_claude_md()
    compose = parse_compose()
    deps = build_dependency_index(PLATFORM_ENTITIES)

    # Two passes: score everything first so the quadrant split can use the
    # estate's own medians rather than a threshold picked in advance.
    scored = []
    for name, ent in PLATFORM_ENTITIES.items():
        j = join_entity(name, ent, entity_md, priority_md, oss_md, compose)
        scored.append((name, ent, j, criticality(ent, j, deps.get(name, 0)), readiness(ent, j)))

    c_split = statistics.median(s[3][0] for s in scored)
    r_split = statistics.median(s[4][0] for s in scored)

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, ent, j, crit, ready in scored:
        q = quadrant(crit[0], ready[0], c_split, r_split)
        fname = f"{slug(name)}.md"
        (out_dir / fname).write_text(
            render_pack(
                name, ent, j, crit, ready, q, deps.get(name, 0), c_split, r_split, priority_md
            ),
            encoding="utf-8",
        )
        rows.append(
            {
                "name": name,
                "pid": ent.pid,
                "pillar": ent.pillar.value,
                "crit": crit[0],
                "ready": ready[0],
                "deps": deps.get(name, 0),
                "port": ent.worker_port or j.compose_port,
                "file": fname,
                "quadrant": q,
            }
        )
    (out_dir / "README.md").write_text(render_index(rows, c_split, r_split), encoding="utf-8")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if committed packs are stale")
    args = ap.parse_args()

    if args.check:
        tmp = Path(tempfile.mkdtemp())
        try:
            build(tmp)
            names = {p.name for p in tmp.iterdir()} | {
                p.name for p in OUT_DIR.iterdir() if p.suffix == ".md"
            }
            stale = [
                n
                for n in sorted(names)
                if not (OUT_DIR / n).exists()
                or not (tmp / n).exists()
                or not filecmp.cmp(OUT_DIR / n, tmp / n, shallow=False)
            ]
            if stale:
                print(
                    f"[ERROR] {len(stale)} pack(s) stale: {', '.join(stale[:8])}", file=sys.stderr
                )
                print("Run: python3 scripts/build_solution_packs.py", file=sys.stderr)
                return 1
            print(f"Solution packs current ({len(names)} files)")
            return 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    rows = build(OUT_DIR)
    from collections import Counter

    q = Counter(r["quadrant"] for r in rows)
    print(f"Generated {len(rows)} packs + index → {OUT_DIR.relative_to(ROOT)}")
    for k, v in q.most_common():
        print(f"  {v:>3}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

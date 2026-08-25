#!/usr/bin/env python3
"""Platform-wide service review, derived from live repo state.

WHY THIS EXISTS

Every previous answer to "what's running, what's connected, what needs work"
has been a hand-maintained table, and hand-maintained tables drift: CLAUDE.md
lists `dimensional-nexus-service` as a deployed P3 worker, and no compose
service builds it. This regenerates the whole picture from the files that
actually decide it — `docker-compose.production.yml`, each worker's Dockerfile,
`api.py`, and `src/entities/platform.py` — so the answer cannot be stale unless
the repo is.

WHAT IT DECIDES, AND ON WHAT EVIDENCE

Each service gets a lifecycle state and a set of named connection checks. Every
check is a yes/no against a file, never a judgement call:

  deployed          a compose service builds or pulls it
  port_agreement    compose's routed port matches the port the container binds
                    (Dockerfile CMD --port wins over the Python default, since
                    that is what actually runs)
  imports_resolve   no unguarded import of a root package the build context
                    excludes — the failure that kept 7 workers from starting
  sibling_urls_dns  no `localhost:<port>` default aimed at a port a sibling
                    compose service owns
  healthcheck       compose defines one, so a wedged container is noticed
  telemetry_reaches whether `instrument_worker` can actually import in the
                    image, rather than being silently skipped
  entity_mapped     a Location in the entity registry claims this service

Lifecycle:
  RUNNING       deployed, every applicable check passes
  NEEDS_WORK    deployed, at least one check fails
  ORPHANED      real code and a Dockerfile, but nothing builds it
  IN_PROCESS    a router mounted in api.py with no service of its own
  INFRA         third-party image (traefik, grafana, …) — not our code to check

SFSC SCOPE

A capability is *in* the Shared Functional Services Core when it lives in
`Dimensional/`. It is a *candidate* when the same cross-cutting concern is
implemented independently in two or more services — measured by scanning for
the concern's signature, not by opinion. Concerns owned by exactly one service
are out of scope by definition: that is not shared, it is that service's job.

Writes docs/architecture/service-review.json and .md. `--check` re-derives and
diffs, for CI.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"
WORKERS = ROOT / "workers"
OUT_JSON = ROOT / "docs" / "architecture" / "service-review.json"
OUT_MD = ROOT / "docs" / "architecture" / "SERVICE-REVIEW.md"

ROOT_PACKAGES = {"src", "Dimensional", "shared_core"}


# Images we pull rather than build. Their internals are not ours to review, but
# they are still part of the running estate, so they are counted, not dropped.
def is_infra(cfg: dict) -> bool:
    return "build" not in cfg and "image" in cfg


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_compose() -> dict[str, dict]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in (data.get("services") or {}).items() if isinstance(v, dict)}


def build_context(cfg: dict) -> Path | None:
    b = cfg.get("build")
    ctx = b.get("context") if isinstance(b, dict) else b
    if not isinstance(ctx, str):
        return None
    ctx = ctx.rstrip("/").lstrip("./")
    return ROOT if ctx in ("", ".") else ROOT / ctx


def dockerfile_for(cfg: dict) -> Path | None:
    b = cfg.get("build")
    if not isinstance(b, dict):
        ctx = build_context(cfg)
        return (ctx / "Dockerfile") if ctx else None
    ctx = build_context(cfg)
    df = b.get("dockerfile", "Dockerfile")
    if ctx is None:
        return None
    p = ROOT / df if str(df).startswith("workers/") else ctx / df
    return p


# --------------------------------------------------------------------------
# Port agreement
# --------------------------------------------------------------------------

# Matches both CMD forms: shell `--port 8018` and JSON-array `"--port", "8018"`.
_CMD_PORT = re.compile(r"--port[=\s\"',]+(\d+)")
_LABEL_PORT = re.compile(r"loadbalancer\.server\.port=(\d+)")


def env_map(cfg: dict) -> dict[str, str]:
    env = cfg.get("environment") or []
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    out = {}
    for item in env:
        k, _, v = str(item).partition("=")
        out[k] = v
    return out


def compose_port(cfg: dict) -> int | None:
    """The port compose actually routes traffic to."""
    for label in cfg.get("labels") or []:
        m = _LABEL_PORT.search(str(label))
        if m:
            return int(m.group(1))
    for spec in cfg.get("ports") or []:
        parts = str(spec).split(":")
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
    for spec in cfg.get("expose") or []:
        if str(spec).isdigit():
            return int(spec)
    env = cfg.get("environment") or []
    pairs = env.items() if isinstance(env, dict) else (str(e).split("=", 1) for e in env)
    for pair in pairs:
        pair = list(pair)
        if len(pair) == 2 and pair[0] == "PORT" and str(pair[1]).isdigit():
            return int(pair[1])
    return None


def _real_cmd(dockerfile_text: str) -> str | None:
    """The image's actual entrypoint CMD.

    A Dockerfile contains more than one line beginning with CMD: HEALTHCHECK's
    own `CMD` continuation looks identical at the start of a line, and it very
    often mentions a port ("…/health"). Taking the first match reads the health
    probe as the entrypoint. The real CMD is the last top-level one — HEALTHCHECK
    CMDs are indented continuations of their HEALTHCHECK line.
    """
    real = None
    for line in dockerfile_text.splitlines():
        if line.startswith("CMD"):  # top-level, not the indented HEALTHCHECK CMD
            real = line
    return real


def bind_port(cfg: dict) -> tuple[int | None, str]:
    """The port the container binds, and where that was decided.

    Dockerfile CMD beats the Python default: a `uvicorn --port N` in CMD
    overrides `os.getenv("PORT", ...)` at container level, so reading only the
    Python default reports phantom mismatches. That distinction is what turned
    an earlier "4 broken workers" finding into 1 real one.

    Both CMD forms have to be handled. Shell form is `--port 8018`; JSON-array
    form is `"--port", "8018"`, where the quote and comma sit between the flag
    and its value. A regex written for only the shell form silently falls
    through to the Python default and invents a mismatch.
    """
    ctx = build_context(cfg)
    df = dockerfile_for(cfg)
    entry_file = None
    if df and df.is_file():
        cmd = _real_cmd(df.read_text(encoding="utf-8", errors="ignore"))
        if cmd:
            m = _CMD_PORT.search(cmd)
            if m:
                return int(m.group(1)), "Dockerfile CMD"
            # No port in CMD — the process reads it from the environment. Read
            # the file CMD actually runs, not a guess at the conventional name.
            fm = re.search(r"([\w./-]+\.py)", cmd)
            if fm:
                entry_file = fm.group(1).split("/")[-1]

    if ctx and ctx != ROOT:
        env = env_map(cfg)
        candidates = [entry_file] if entry_file else ["worker.py", "main.py"]
        for cand in candidates:
            f = ctx / cand if cand else None
            if f and f.is_file():
                t = f.read_text(encoding="utf-8", errors="ignore")
                # Which env var the bind port comes from, and its fallback.
                # Restricted to the listen port: `SMTP_PORT`, `REDIS_PORT` and
                # friends are ports this service *calls*, and matching any
                # *_PORT reported email-service as binding 587.
                m = re.search(
                    r'os\.getenv\(\s*["\'](PORT|\w+_PORT)["\']\s*'
                    r'(?:,\s*["\']?(\d+)|\)\s*or\s*["\'](\d+))',
                    t,
                )
                if m:
                    var, default = m.group(1), int(m.group(2) or m.group(3))
                    # The default only runs when compose leaves the var unset.
                    # Reading the default unconditionally reported 9 healthy
                    # services as misrouted — every one of them had compose
                    # setting the very variable being ignored.
                    if var in env and str(env[var]).isdigit():
                        return int(env[var]), f"compose {var}"
                    return default, f"{cand} {var} default (compose sets no {var})"
    return None, "undetermined"


# --------------------------------------------------------------------------
# Import safety (shared shape with check_worker_build_context.py)
# --------------------------------------------------------------------------


def guarded_spans(tree: ast.AST) -> list[tuple[int, int]]:
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches = False
        for h in node.handlers:
            if h.type is None:
                catches = True
                break
            names = {n.id for n in ast.walk(h.type) if isinstance(n, ast.Name)}
            if names & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
                catches = True
                break
        if catches:
            for stmt in node.body:
                spans.append((stmt.lineno, getattr(stmt, "end_lineno", stmt.lineno)))
    return spans


def scan_imports(ctx: Path) -> dict[str, list]:
    """Cross-boundary imports in a build context, split by whether they resolve."""
    out = {"unguarded": [], "guarded": [], "vendored": []}
    if ctx == ROOT:
        return out  # whole repo is in the image
    for py in sorted(ctx.rglob("*.py")):
        rel_parts = py.relative_to(ctx).parts
        if any(p in ROOT_PACKAGES for p in rel_parts[:-1]):
            continue  # this is the vendored copy, not a dependant
        if "tests" in rel_parts or py.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, ValueError):
            continue
        spans = guarded_spans(tree)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if node.module.split(".")[0] in ROOT_PACKAGES:
                    mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names if a.name.split(".")[0] in ROOT_PACKAGES]
            for mod in mods:
                top = mod.split(".")[0]
                entry = f"{py.relative_to(ROOT)}:{node.lineno} {mod}"
                if (ctx / top).is_dir():
                    out["vendored"].append(entry)
                elif any(a <= node.lineno <= b for a, b in spans):
                    out["guarded"].append(entry)
                else:
                    out["unguarded"].append(entry)
    return out


# --------------------------------------------------------------------------
# Sibling URL check
# --------------------------------------------------------------------------


def owned_ports(compose: dict[str, dict]) -> dict[int, str]:
    out = {}
    for name, cfg in compose.items():
        p = compose_port(cfg)
        if p:
            out.setdefault(p, name)
    return out


def _url_checker():
    """Load scripts/check_service_urls.py and reuse its rules.

    Reimplementing this check produced 17 false positives in one run —
    `FRONTEND_URL -> localhost:3000` reported as aimed at grafana because
    grafana happens to own 3000, and every root-context service blamed for
    repo-wide URLs in api.py. The existing checker already carries the
    exemptions (KNOWN_EXTERNAL, with a recorded reason each) and the
    `src/` -> tranc3-backend ownership mapping that make it report zero. Import
    it rather than write a second, worse copy of the same judgement.
    """
    import importlib.util

    path = ROOT / "scripts" / "check_service_urls.py"
    spec = importlib.util.spec_from_file_location("_check_service_urls", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scan_urls_all(compose: dict[str, dict]) -> dict[str, list[str]]:
    """service -> live localhost defaults aimed at a sibling, via the real checker."""
    try:
        mod = _url_checker()
        port_owner, declared = mod.parse_compose()
    except Exception as exc:  # never let the review die on a helper
        return {"__error__": [f"could not load check_service_urls.py: {exc}"]}

    out: dict[str, list[str]] = defaultdict(list)
    for py in sorted(ROOT.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", "node_modules/", "scripts/")) or "/tests/" in rel:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for var, port in mod.URL_DEFAULT.findall(text):
            if var in mod.KNOWN_EXTERNAL:
                continue
            target = port_owner.get(port)
            if not target:
                continue
            declarer = mod.owning_service(py)
            if declarer and var in declared.get(declarer, set()):
                continue  # compose overrides the default; it is dead code
            if declarer == target:
                continue
            out[declarer or "<unattributed>"].append(f"{rel}: {var} -> localhost:{port} ({target})")
    return dict(out)


# --------------------------------------------------------------------------
# Entity registry
# --------------------------------------------------------------------------


def entity_claims() -> dict[str, str]:
    """worker dir name -> Location that claims it."""
    sys.path.insert(0, str(ROOT))
    try:
        from src.entities.platform import PLATFORM_ENTITIES
    except Exception:
        return {}
    out = {}
    for loc, ent in PLATFORM_ENTITIES.items():
        wp = getattr(ent, "worker_path", None)
        if wp:
            out[str(wp).rstrip("/").split("/")[-1]] = loc
    return out


# --------------------------------------------------------------------------
# SFSC scope
# --------------------------------------------------------------------------

# A concern is identified by a signature that is specific enough not to fire on
# unrelated code. Each is something a platform would normally solve once.
# Each signature must match an *implementation* of the concern, not a use of it.
# Reading `INTERNAL_SECRET` from the environment is using a shared convention —
# 67 services do, and counting those as 67 duplicate implementations made the
# most-used convention on the platform look like its worst duplication. What
# duplicates is the comparison logic, so the signature is the compare, not the
# variable name.
CONCERNS = {
    "circuit breaker": re.compile(r"class\s+_?CircuitBreaker\b|class\s+CircuitState\b"),
    "internal-secret verification": re.compile(
        r"compare_digest\s*\([^)]*(?:INTERNAL_SECRET|internal_secret)|"
        r"def\s+\w*(?:verify|require|check)_internal\w*\s*\("
    ),
    "log sanitisation": re.compile(r"def\s+sanitize_for_log\b|class\s+SafeLogger\b"),
    "path traversal guard": re.compile(
        r"def\s+safe_join\b|def\s+sanitize_filename\b|class\s+PathTraversalError\b"
    ),
    "token-bucket rate limit": re.compile(r"class\s+\w*TokenBucket\w*\b|def\s+_?token_bucket\b"),
    "OTel worker setup": re.compile(r"def\s+instrument_worker\b|instrument_worker\("),
    "JWT verify": re.compile(r"def\s+verify_jwt\b|jwt\.decode\s*\("),
}


def dimensional_inventory() -> dict[str, Any]:
    dim = ROOT / "Dimensional"
    mods = sorted(p.relative_to(ROOT).as_posix() for p in dim.rglob("*.py"))
    covered = {}
    for concern, pat in CONCERNS.items():
        hits = [m for m in mods if pat.search((ROOT / m).read_text(errors="ignore"))]
        covered[concern] = hits
    return {"module_count": len(mods), "concern_coverage": covered}


def concern_spread(compose: dict[str, dict]) -> dict[str, dict]:
    """For each concern, which independent build contexts implement it."""
    spread: dict[str, set[str]] = defaultdict(set)
    for name, cfg in compose.items():
        ctx = build_context(cfg)
        if ctx is None or ctx == ROOT:
            continue
        for py in ctx.rglob("*.py"):
            if any(p in ROOT_PACKAGES for p in py.relative_to(ctx).parts[:-1]):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for concern, pat in CONCERNS.items():
                if pat.search(text):
                    spread[concern].add(name)
    dim = dimensional_inventory()["concern_coverage"]
    out = {}
    for concern in CONCERNS:
        services = sorted(spread.get(concern, ()))
        out[concern] = {
            "in_dimensional": bool(dim.get(concern)),
            "dimensional_modules": dim.get(concern, []),
            "services_implementing_independently": services,
            "verdict": _verdict(bool(dim.get(concern)), len(services)),
        }
    return out


def _strip_prose(src: str) -> str:
    """Remove docstrings and comments so prose is never classified as code."""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    return re.sub(r"#[^\n]*", "", src)


_DEF_BODY = re.compile(
    r"def\s+\w*(?:verify|require|check)_internal\w*\s*\(.*?(?=\ndef |\nclass |\Z)", re.S
)


def internal_secret_variance(compose: dict[str, dict], services: list[str]) -> dict:
    """How the 40-odd hand-rolled internal-secret checks actually differ.

    The count alone understates it. Duplication is a maintenance cost;
    duplication that has drifted into different *security* behaviour is a
    vulnerability. Measured, not asserted: whether the comparison is
    constant-time, and whether an unset secret fails open.
    """
    out = {"total": len(services), "constant_time": [], "timing_unsafe": [], "fail_open": []}
    for name in services:
        ctx = build_context(compose[name])
        if not ctx:
            continue
        for py in sorted(ctx.rglob("*.py")):
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in _DEF_BODY.finditer(text):
                # Strip docstrings and comments before classifying. A docstring
                # explaining "this used to be `if INTERNAL_SECRET and ...`"
                # otherwise reads as that code and reports a fixed service as
                # still vulnerable — which is exactly what happened once the
                # four fail-open checks were fixed and documented.
                body = _strip_prose(m.group(0))[:600]
                if "compare_digest" in body:
                    out["constant_time"].append(name)
                elif "!=" in body or "==" in body:
                    out["timing_unsafe"].append(name)
                # Two shapes of the same fail-open, and matching only the
                # first undercounted: `if SECRET and x != SECRET: raise` skips
                # the check when the secret is unset, and so does an early
                # `if not SECRET: return` guard above the comparison.
                if re.search(r"if\s+\w*INTERNAL_SECRET\w*\s+and\b", body) or re.search(
                    r"if\s+not\s+\w*INTERNAL_SECRET\w*\s*:\s*\n\s*return\b", body
                ):
                    out["fail_open"].append(name)
    for k in ("constant_time", "timing_unsafe", "fail_open"):
        out[k] = sorted(set(out[k]))
    return out


def _verdict(in_dim: bool, n: int) -> str:
    if in_dim and n == 0:
        return "IN SCOPE — in the core, nothing duplicating it"
    if in_dim and n:
        return f"IN SCOPE, NOT REACHING — in the core, but {n} service(s) implement it anyway"
    if n >= 2:
        return f"CANDIDATE — {n} services implement it independently, core has nothing"
    if n == 1:
        return "OUT OF SCOPE — one service only, that is its own job"
    return "ABSENT — nothing implements it"


# --------------------------------------------------------------------------
# Review
# --------------------------------------------------------------------------


def review_service(
    name: str,
    cfg: dict,
    ports: dict[int, str],
    claims: dict[str, str],
    url_offenders: dict[str, list[str]],
) -> dict:
    if is_infra(cfg):
        return {
            "service": name,
            "lifecycle": "INFRA",
            "image": cfg.get("image"),
            "checks": {},
            "failures": [],
        }

    ctx = build_context(cfg)
    df = dockerfile_for(cfg)
    ctx_rel = ctx.relative_to(ROOT).as_posix() if ctx else None
    checks: dict[str, Any] = {}

    cp = compose_port(cfg)
    bp, bp_src = bind_port(cfg)
    if cp is None or bp is None:
        checks["port_agreement"] = {"ok": None, "detail": f"compose={cp} bind={bp} ({bp_src})"}
    else:
        checks["port_agreement"] = {
            "ok": cp == bp,
            "detail": f"compose routes {cp}, container binds {bp} via {bp_src}",
        }

    imports = scan_imports(ctx) if ctx else {"unguarded": [], "guarded": [], "vendored": []}
    checks["imports_resolve"] = {
        "ok": not imports["unguarded"],
        "detail": (
            f"{len(imports['unguarded'])} unguarded, {len(imports['guarded'])} guarded, "
            f"{len(imports['vendored'])} vendored"
        ),
        "offenders": imports["unguarded"],
    }

    bad_urls = url_offenders.get(name, [])
    checks["sibling_urls_dns"] = {
        "ok": not bad_urls,
        "detail": f"{len(bad_urls)} live localhost default(s) aimed at a sibling",
        "offenders": bad_urls,
    }

    # Compose inherits the image's HEALTHCHECK when it declares none of its own,
    # so a Dockerfile-level probe counts. Requiring it in compose specifically
    # flagged cryptex and observatory, both of which do have one.
    df_has_hc = False
    if df and df.is_file():
        df_has_hc = "HEALTHCHECK" in df.read_text(encoding="utf-8", errors="ignore")
    where = "compose" if "healthcheck" in cfg else ("Dockerfile" if df_has_hc else None)
    checks["healthcheck"] = {
        "ok": where is not None,
        "detail": f"defined in {where}" if where else "none — a wedged container goes unnoticed",
    }

    # Telemetry only counts as reaching if the import can resolve in the image.
    wants_otel = bool(imports["guarded"] or imports["unguarded"] or imports["vendored"]) and any(
        "worker_setup" in e for e in sum(imports.values(), [])
    )
    if not wants_otel:
        checks["telemetry_reaches"] = {"ok": None, "detail": "does not call instrument_worker"}
    else:
        reaches = ctx == ROOT or any("worker_setup" in e for e in imports["vendored"])
        checks["telemetry_reaches"] = {
            "ok": reaches,
            "detail": (
                "src/ present in image"
                if reaches
                else "import is guarded but src/ is absent — telemetry silently off"
            ),
        }

    # Informational, never a failure. There are 43 Locations and 88 buildable
    # services: most workers are plumbing (cache, cdn, geo, rate-limit) that no
    # Location should claim, so scoring "unclaimed" as a defect failed 68 of 88
    # and buried the four checks that mean something. The defect worth catching
    # here is the opposite direction — a Location claiming a worker_path that is
    # not deployed — and `build_topology_map.py` already reports those as
    # `stale_claim` edges.
    claimed_by = claims.get(ctx_rel.split("/")[-1]) if ctx_rel else None
    checks["entity_mapped"] = {
        "ok": None,
        "detail": (
            f"claimed by {claimed_by}"
            if claimed_by
            else "no Location claims it — expected for platform plumbing"
        ),
    }

    failures = [k for k, v in checks.items() if v.get("ok") is False]
    return {
        "service": name,
        "lifecycle": "RUNNING" if not failures else "NEEDS_WORK",
        "build_context": ctx_rel,
        "checks": checks,
        "failures": failures,
    }


def orphan_dirs(compose: dict[str, dict]) -> list[dict]:
    referenced = set()
    for cfg in compose.values():
        b = cfg.get("build")
        if not b:
            continue
        blob = json.dumps(b)
        referenced.update(re.findall(r"workers/([A-Za-z0-9_.-]+)", blob))
    out = []
    for d in sorted(p for p in WORKERS.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if d.name in referenced:
            continue
        out.append(
            {
                "service": d.name,
                "lifecycle": "ORPHANED",
                "build_context": d.relative_to(ROOT).as_posix(),
                "python_files": len(list(d.rglob("*.py"))),
                "has_dockerfile": (d / "Dockerfile").is_file(),
                "checks": {},
                "failures": ["not built by any compose service"],
            }
        )
    return out


def mounted_routers() -> list[str]:
    text = (ROOT / "api.py").read_text(encoding="utf-8", errors="ignore")
    return sorted(set(re.findall(r"include_router\(\s*([A-Za-z_][\w.]*)", text)))


def build() -> dict:
    compose = load_compose()
    ports = owned_ports(compose)
    claims = entity_claims()
    concerns = concern_spread(compose)
    url_offenders = scan_urls_all(compose)
    services = [
        review_service(n, c, ports, claims, url_offenders) for n, c in sorted(compose.items())
    ]
    services += orphan_dirs(compose)

    by_state = defaultdict(list)
    for s in services:
        by_state[s["lifecycle"]].append(s["service"])

    failure_index = defaultdict(list)
    for s in services:
        for f in s["failures"]:
            failure_index[f].append(s["service"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "totals": {k: len(v) for k, v in sorted(by_state.items())},
        "by_state": {k: sorted(v) for k, v in sorted(by_state.items())},
        "failures_by_check": {k: sorted(v) for k, v in sorted(failure_index.items())},
        "sfsc": {
            "dimensional": dimensional_inventory(),
            "concerns": concerns,
            "internal_secret_variance": internal_secret_variance(
                compose,
                concerns["internal-secret verification"]["services_implementing_independently"],
            ),
        },
        "mounted_routers": mounted_routers(),
        "services": services,
    }


def render_md(g: dict) -> str:
    L = []
    a = L.append
    a("# Platform Service Review")
    a("")
    a(f"Generated from repo state at `{g['commit']}`. Regenerate with")
    a("`python scripts/build_service_review.py`; CI checks freshness with `--check`.")
    a("")
    a("## Where the estate stands")
    a("")
    a("| State | Count | Meaning |")
    a("|---|---:|---|")
    meanings = {
        "RUNNING": "deployed and every applicable check passes",
        "NEEDS_WORK": "deployed, but at least one connection check fails",
        "ORPHANED": "real code and a Dockerfile, nothing builds it",
        "INFRA": "third-party image — counted, not checked",
    }
    for state, n in g["totals"].items():
        a(f"| **{state}** | {n} | {meanings.get(state, '')} |")
    a("")

    a("## What is failing, by check")
    a("")
    if not g["failures_by_check"]:
        a("Nothing. Every deployed service passes every applicable check.")
    else:
        a("| Check | Services | Which |")
        a("|---|---:|---|")
        for check, svcs in sorted(g["failures_by_check"].items(), key=lambda kv: -len(kv[1])):
            shown = ", ".join(f"`{s}`" for s in svcs[:8])
            if len(svcs) > 8:
                shown += f" … +{len(svcs) - 8}"
            a(f"| {check} | {len(svcs)} | {shown} |")
    a("")

    a("## Dimensionals — what is in scope, what is not")
    a("")
    a(f"`Dimensional/` holds {g['sfsc']['dimensional']['module_count']} modules. ")
    a("A concern is *in scope* when the shared core owns it; a *candidate* when two or")
    a("more services solve it independently; *out of scope* when exactly one service")
    a("does, because that is not shared code, it is that service's job.")
    a("")
    a("| Concern | In core | Services doing it themselves | Verdict |")
    a("|---|:---:|---:|---|")
    for concern, d in sorted(
        g["sfsc"]["concerns"].items(),
        key=lambda kv: -len(kv[1]["services_implementing_independently"]),
    ):
        a(
            f"| {concern} | {'yes' if d['in_dimensional'] else 'no'} "
            f"| {len(d['services_implementing_independently'])} | {d['verdict']} |"
        )
    a("")

    v = g["sfsc"]["internal_secret_variance"]
    if v["total"]:
        a("### Why `internal-secret verification` is the first one to fix")
        a("")
        a(f"{v['total']} services each write their own check, and they have not stayed")
        a("the same. `Dimensional/security.py` already exposes a constant-time compare")
        a("that none of them import.")
        a("")
        a("| Behaviour | Services |")
        a("|---|---:|")
        a(f"| constant-time (`compare_digest`) | {len(v['constant_time'])} |")
        a(f"| timing-unsafe (`==` / `!=`) | {len(v['timing_unsafe'])} |")
        a(f"| **fails open when the secret is unset** | {len(v['fail_open'])} |")
        a("")
        if v["fail_open"]:
            a("Fails open — an unset `INTERNAL_SECRET` disables the check rather than")
            a("refusing the request:")
            a("")
            for s in v["fail_open"]:
                a(f"- `{s}`")
            a("")

    for state in ("NEEDS_WORK", "ORPHANED"):
        names = g["by_state"].get(state, [])
        if not names:
            continue
        a(f"## {state}")
        a("")
        for s in g["services"]:
            if s["lifecycle"] != state:
                continue
            a(f"### `{s['service']}`")
            for f in s["failures"]:
                det = s["checks"].get(f, {})
                a(f"- **{f}** — {det.get('detail', '')}")
                for off in (det.get("offenders") or [])[:4]:
                    a(f"  - `{off}`")
            a("")

    a("## Running clean")
    a("")
    running = g["by_state"].get("RUNNING", [])
    a(f"{len(running)} services pass every applicable check:")
    a("")
    a(", ".join(f"`{s}`" for s in running) or "_none_")
    a("")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if committed output is stale")
    args = ap.parse_args()

    g = build()
    md = render_md(g)
    js = json.dumps(g, indent=2, sort_keys=True)

    if args.check:
        if not OUT_JSON.is_file() or not OUT_MD.is_file():
            print("service review has never been generated", file=sys.stderr)
            return 1
        old = json.loads(OUT_JSON.read_text())
        new = json.loads(js)
        old.pop("generated_at", None), new.pop("generated_at", None)
        old.pop("commit", None), new.pop("commit", None)
        if old != new:
            print(
                "service review is stale — rerun scripts/build_service_review.py", file=sys.stderr
            )
            return 1
        print("service review: up to date")
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(js + "\n", encoding="utf-8")
    OUT_MD.write_text(md, encoding="utf-8")
    t = g["totals"]
    print(
        f"service review: {sum(t.values())} services — "
        + ", ".join(f"{k} {v}" for k, v in t.items())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Measure whether the platform's declared Location-to-Location flows are real.

WHY THIS EXISTS

`docs/governance/LOCATION-TRAFFIC-MATRIX.md` recorded, correctly, that nothing in
this repository can answer "does all X route through Y". The one mechanism built
for it -- `ServiceMesh.get_dependency_graph()` -- returns an empty graph for
every service, because no registration call site has ever passed `dependencies=`.
So every claim of the form "all photo generation goes through Sashas Photo
Studio" has been unfalsifiable: no way to confirm it, and no way to notice the
day it stops being true.

This script closes that. `config/estate/flow_contract.yaml` declares each
intended flow together with the probes that would evidence it; this module runs
the probes against the working tree and derives a verdict. The verdict is
*derived*, never declared -- a rule cannot assert its own health, for the same
reason `vulnerability_census.py` no longer infers `blocked` from register
membership.

VERDICTS

  enforced   every probe passes -- the hub exists and something routes to it
  partial    the hub exists and some, but not all, coupling probes pass
  unwired    the hub exists and NOTHING routes to it (built, never connected)
  absent     no implementation found at all
  unknown    a probe could not be evaluated

`unwired` is the category worth having. It separates "we have not built this"
from the more expensive failure: code that exists, imports cleanly, passes its
tests, and is reached by nothing -- `src/basement/promotion.py` being the
present example.

FAIL-CLOSED

An unevaluable probe yields `unknown`, never a pass. `--check` treats `unknown`
as failure. A probe that raises is reported, not swallowed.

REGRESSION, NOT ABSOLUTE

The estate has a real backlog of unbuilt flows; failing the build on all of them
would make the gate noise that everyone learns to wave through. `--check`
instead compares against `config/estate/flow_baseline.json` and fails only on
*regression* -- a rule that was enforced and is no longer, or a rule missing from
the baseline entirely. Improving a rule requires refreshing the baseline, which
is a visible, reviewable act rather than a silent one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
CONTRACT = REPO / "config" / "estate" / "flow_contract.yaml"
BASELINE = REPO / "config" / "estate" / "flow_baseline.json"
REPORT = REPO / "logs" / "flow_conformance.json"
CONTRACT_DOC = REPO / "docs" / "governance" / "LOCATION-FLOW-CONTRACT.md"

# Verdicts ordered worst -> best. Used to decide what counts as a regression.
VERDICT_RANK = {"unknown": 0, "absent": 1, "unwired": 2, "partial": 3, "enforced": 4}

# Probes that prove a thing exists, vs probes that prove something reaches it.
# The split is what makes `unwired` distinguishable from `absent`.
EXISTENCE_KINDS = {"module_exists", "worker_exists", "router_mounted", "compose_service"}
COUPLING_KINDS = {"inbound_imports", "http_dependency", "symbol_called", "code_pattern"}


class ProbeError(RuntimeError):
    """A probe could not be evaluated. Never silently treated as a pass."""


def _inside_repo(path: Path) -> Path:
    """Refuse any path that escapes the repository."""
    resolved = (REPO / path).resolve() if not path.is_absolute() else path.resolve()
    if not resolved.is_relative_to(REPO):
        raise ValueError(f"path escapes the repository: {path}")
    return resolved


# ── probes ───────────────────────────────────────────────────────────────────


def _probe_module_exists(spec: dict[str, Any]) -> bool:
    return _inside_repo(Path(spec["path"])).exists()


def _probe_worker_exists(spec: dict[str, Any]) -> bool:
    return _inside_repo(Path(spec["path"])).exists()


def _probe_router_mounted(spec: dict[str, Any]) -> bool:
    """The router is not merely defined -- api.py includes it.

    A router that exists but is never included is exactly the dead-duplicate
    pattern CLAUDE.md records for src/studio, src/lab, src/artifactory and
    others, so 'defined' is not the question worth asking.
    """
    api = (REPO / "api.py").read_text(encoding="utf-8")
    return bool(re.search(rf"include_router\(\s*{re.escape(spec['token'])}\s*\)", api))


def _probe_compose_service(spec: dict[str, Any]) -> bool:
    compose = (REPO / "docker-compose.production.yml").read_text(encoding="utf-8")
    return bool(re.search(rf"^  {re.escape(spec['name'])}:\s*$", compose, re.MULTILINE))


def _probe_inbound_imports(spec: dict[str, Any]) -> bool:
    """Count modules OUTSIDE the target's own tree that import it.

    Self-imports prove nothing: a package importing itself is cohesion, not
    routing. Tests are excluded for the same reason -- a test exercising a hub
    is not the platform using it.
    """
    dotted = spec["module"]
    prefix = dotted.replace(".", "/")
    found = subprocess.run(
        ["grep", "-rl", "--include=*.py", f"from {dotted}", "src", "workers", "api.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.split()
    external = [f for f in found if not f.startswith(prefix) and "/test" not in f]
    return len(external) >= int(spec.get("min", 1))


def _probe_http_dependency(spec: dict[str, Any]) -> bool:
    """One worker names another worker's URL -- real cross-service routing.

    Workers are separate processes; coupling between them is HTTP, not imports,
    so an import-only probe would score the whole worker fleet as disconnected.
    """
    target = _inside_repo(Path(spec["path"]))
    if not target.exists():
        return False
    haystack = (
        "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in target.rglob("*.py"))
        if target.is_dir()
        else target.read_text(encoding="utf-8", errors="replace")
    )
    return spec["env"] in haystack


def _strip_prose(source: str) -> str:
    """Remove comments and docstrings so a probe cannot match on description.

    This exists because the first run of this checker scored the
    Basement-to-Library promotion as `enforced` on the strength of a single
    match: the docstring in THIS FILE explaining that `promote()` is called by
    nothing. A tool that accepts its own prose as evidence is worse than no
    tool, so prose is removed before any code probe looks at a file.
    """
    without_docstrings = re.sub(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'', "", source)
    return re.sub(r"(?m)#.*$", "", without_docstrings)


def _code_files(target: Path, glob: str = "*.py") -> list[Path]:
    """Python sources under `target`, excluding caches and this checker itself.

    __pycache__ is excluded because compiled bytecode contains every string
    literal in the module and grep happily matches inside it -- a probe that
    reads .pyc files is matching the same source twice and calling it
    corroboration.
    """
    files = sorted(target.rglob(glob)) if target.is_dir() else [target]
    return [
        f for f in files if "__pycache__" not in f.parts and f.resolve() != Path(__file__).resolve()
    ]


def _probe_symbol_called(spec: dict[str, Any]) -> bool:
    """The function is not just defined -- code outside its module calls it.

    This is the probe that catches the expensive case. `src/basement/promotion.py`
    defines `promote()`, is fully tested, and is invoked by nothing; without this
    probe the Basement-to-Library flow would score as built.
    """
    symbol = spec["symbol"]
    home = _inside_repo(Path(spec["module"].replace(".", "/")))
    call = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    hits = 0
    for root in ("src", "workers", "scripts"):
        for path in _code_files(REPO / root):
            if path.is_relative_to(home) or "/test" in str(path):
                continue
            if call.search(_strip_prose(path.read_text(encoding="utf-8", errors="replace"))):
                hits += 1
    api = _strip_prose((REPO / "api.py").read_text(encoding="utf-8"))
    if call.search(api):
        hits += 1
    return hits >= int(spec.get("min", 1))


def _probe_code_pattern(spec: dict[str, Any]) -> bool:
    """A pattern appears in real code -- not in a comment, docstring or cache.

    Patterns must be written to be true only when the flow is: a route, a call,
    a dispatch, an environment variable. A pattern that would also match an
    entity-table description or a persona name in a metadata literal proves
    nothing -- the first run of this checker scored Arcadia's forum as enforced
    on the strength of `primary_function="... Forum & Email Hub"`.
    """
    target = _inside_repo(Path(spec["path"]))
    if not target.exists():
        return False
    pattern = re.compile(spec["pattern"], re.IGNORECASE)
    strip = spec.get("strip_prose", True)
    for path in _code_files(target, spec.get("glob", "*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(_strip_prose(text) if strip else text):
            return True
    return False


PROBES = {
    "module_exists": _probe_module_exists,
    "worker_exists": _probe_worker_exists,
    "router_mounted": _probe_router_mounted,
    "compose_service": _probe_compose_service,
    "inbound_imports": _probe_inbound_imports,
    "http_dependency": _probe_http_dependency,
    "symbol_called": _probe_symbol_called,
    "code_pattern": _probe_code_pattern,
}


def run_probe(spec: dict[str, Any]) -> bool:
    kind = spec.get("kind")
    probe = PROBES.get(kind)
    if probe is None:
        raise ProbeError(f"unknown probe kind: {kind!r}")
    try:
        return bool(probe(spec))
    except ProbeError:
        raise
    except Exception as exc:  # noqa: BLE001 -- surfaced as `unknown`, never as a pass
        raise ProbeError(f"{kind} probe failed: {exc}") from exc


# ── verdict ──────────────────────────────────────────────────────────────────


def classify(existence: list[bool], coupling: list[bool], errored: bool) -> str:
    """Derive a rule's verdict from its probe results.

    Deliberately total and side-effect free, so the table below is the whole
    behaviour and a test can pin every branch:

        errored            -> unknown   (fail-closed: an unevaluable rule is
                                         never reported as healthy)
        nothing exists     -> absent
        exists, no coupler -> unwired   (built and reached by nothing)
        all pass           -> enforced
        otherwise          -> partial
    """
    if errored:
        return "unknown"
    if existence and not any(existence):
        return "absent"
    if coupling and not any(coupling):
        return "unwired"
    if all(existence) and all(coupling):
        return "enforced"
    return "partial"


def evaluate(rule: dict[str, Any]) -> dict[str, Any]:
    existence: list[bool] = []
    coupling: list[bool] = []
    details: list[dict[str, Any]] = []
    errored = False

    for spec in rule.get("probes", []):
        kind = spec.get("kind")
        try:
            passed = run_probe(spec)
            note = None
        except ProbeError as exc:
            passed, note, errored = False, str(exc), True
        details.append({"kind": kind, "passed": passed, "note": note})
        if kind in EXISTENCE_KINDS:
            existence.append(passed)
        elif kind in COUPLING_KINDS:
            coupling.append(passed)

    return {
        "id": rule["id"],
        "claim": rule["claim"],
        "hub": rule["hub"],
        "verdict": classify(existence, coupling, errored),
        "probes": details,
        "note": rule.get("note"),
    }


def load_contract() -> list[dict[str, Any]]:
    data = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return data["rules"]


def build_report() -> dict[str, Any]:
    results = [evaluate(r) for r in load_contract()]
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule_count": len(results),
        "counts": counts,
        "rules": results,
    }


def check_against_baseline(report: dict[str, Any]) -> list[str]:
    """Return contract/baseline disagreements. Empty list means the gate passes.

    The comparison is EXACT in both directions, which is a correction. The first
    implementation failed only on a *lower* verdict, and that quietly broke the
    ratchet it was supposed to be: if a flow improved from `partial` to
    `enforced` and nobody refreshed the baseline, the run passed -- and the
    baseline still read `partial`, so a later slide back from `enforced` to
    `partial` also passed, because it now matched. The gate would have been
    green across the whole round trip, having recorded an improvement it then
    silently gave back.

    An improvement is therefore a failure too, with a message that says so and
    names the fix. That is not pedantry: refreshing the baseline is the act that
    makes the improvement real, and a gate that does not require it turns
    `--write-baseline` into an optional courtesy.

    IDs present only in the baseline fail as well, so deleting a rule from the
    contract is a visible removal rather than a flow that stops being watched
    without anyone noticing.
    """
    if not BASELINE.exists():
        return ["no baseline recorded -- run --write-baseline and review the result"]
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures: list[str] = []
    seen: set[str] = set()

    for rule in report["rules"]:
        seen.add(rule["id"])
        was = baseline.get(rule["id"])
        if was is None:
            failures.append(
                f"{rule['id']}: not in the baseline (new rule needs a recorded verdict)"
            )
            continue
        if rule["verdict"] == was:
            continue
        direction = "regressed" if VERDICT_RANK[rule["verdict"]] < VERDICT_RANK[was] else "improved"
        failures.append(
            f"{rule['id']}: {direction} {was} -> {rule['verdict']} ({rule['claim']})"
            + ("" if direction == "regressed" else " -- refresh the baseline to record it")
        )

    for missing in sorted(set(baseline) - seen):
        failures.append(
            f"{missing}: in the baseline but not in the contract "
            "(a deleted rule must be removed from the baseline deliberately)"
        )
    return failures


#: The document bolds a verdict for emphasis in some rows and not others,
#: which is a presentation choice and must not change what is read.
_DOC_VERDICT_ROW = re.compile(
    r"^\|\s*`(?P<id>FLOW-\d+)`\s*\|[^|]*\|[^|]*\|\s*\*{0,2}(?P<verdict>\w+)\*{0,2}\s*\|"
)
_DOC_COUNT_ROW = re.compile(r"^\|\s*`(?P<verdict>\w+)`\s*\|\s*(?P<count>\d+)\s*\|\s*$")


def check_contract_document(baseline: dict[str, str]) -> list[str]:
    """Fail when the written contract and the recorded baseline disagree.

    LOCATION-FLOW-CONTRACT.md states each flow's verdict and a count table,
    by hand. The baseline is refreshed by `--write-baseline`, the document is
    not, and the two had already parted: FLOW-064 reached `enforced` and the
    document still called it `unwired`, with counts of 22/12 against the
    baseline's 23/11. A governance document that a reader trusts instead of
    the code is worse than none, and the drift is silent by construction —
    nothing reads the document.
    """
    if not CONTRACT_DOC.exists():
        return [f"{CONTRACT_DOC.relative_to(REPO)} is missing"]

    text = CONTRACT_DOC.read_text(encoding="utf-8")
    failures: list[str] = []

    stated: dict[str, str] = {}
    counts: dict[str, int] = {}
    for line in text.splitlines():
        row = _DOC_VERDICT_ROW.match(line.strip())
        if row:
            stated[row.group("id")] = row.group("verdict")
            continue
        count = _DOC_COUNT_ROW.match(line.strip())
        if count:
            counts[count.group("verdict")] = int(count.group("count"))

    for rule_id, verdict in sorted(baseline.items()):
        if rule_id not in stated:
            failures.append(f"{rule_id}: recorded as {verdict} but the contract document omits it")
        elif stated[rule_id] != verdict:
            failures.append(
                f"{rule_id}: document says {stated[rule_id]}, baseline records {verdict}"
            )
    for rule_id in sorted(set(stated) - set(baseline)):
        failures.append(f"{rule_id}: in the contract document but not in the baseline")

    actual: dict[str, int] = {}
    for verdict in baseline.values():
        actual[verdict] = actual.get(verdict, 0) + 1
    for verdict in VERDICT_RANK:
        expected = actual.get(verdict, 0)
        if counts.get(verdict, 0) != expected:
            failures.append(
                f"count table says {counts.get(verdict, 0)} {verdict}, baseline holds {expected}"
            )
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="fail on regression against the baseline")
    ap.add_argument(
        "--write-baseline", action="store_true", help="record current verdicts as the baseline"
    )
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = ap.parse_args()

    report = build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        order = ["enforced", "partial", "unwired", "absent", "unknown"]
        print(f"Location flow conformance -- {report['rule_count']} declared flows")
        print("  " + ", ".join(f"{report['counts'].get(v, 0)} {v}" for v in order))
        print()
        for verdict in order:
            rules = [r for r in report["rules"] if r["verdict"] == verdict]
            if not rules:
                continue
            print(f"{verdict.upper()}")
            for r in rules:
                print(f"  {r['id']}  {r['hub']:<26} {r['claim']}")
            print()

    if args.write_baseline:
        BASELINE.write_text(
            json.dumps({r["id"]: r["verdict"] for r in report["rules"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"baseline written to {BASELINE.relative_to(REPO)}")
        return 0

    if args.check:
        failures = check_against_baseline(report)
        failures += check_contract_document(json.loads(BASELINE.read_text(encoding="utf-8")))
        if failures:
            print("FLOW CONFORMANCE FAILED", file=sys.stderr)
            for f in failures:
                print(f"  {f}", file=sys.stderr)
            return 1
        print("flow conformance: contract matches the baseline exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

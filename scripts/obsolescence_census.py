#!/usr/bin/env python3
"""Measure whether the estate's dependencies are still *alive*, not just unbreached.

WHY THIS EXISTS

`scripts/vulnerability_census.py` answers "what is known to be vulnerable?".
That is a necessary question and an insufficient one, because it can only see
risk that has already been discovered, written up, and assigned an identifier.
It is silent on the risk that arrives first and lasts longest: a dependency
whose upstream has stopped.

The 2026 OSSRA report puts numbers on how normal that is. Across 947 audited
commercial codebases: 93% contained components with no upstream development in
over two years, 92% contained components four or more years out of date, and
only 7% of all components were running the latest available version. More than
two-thirds of components were over two years old.

The reason this matters is not tidiness. It is that when a CVE lands in a
project nobody maintains, there is no patch to take. The choice at that moment
is fork-and-maintain, rip-out-and-refactor, or carry the risk -- and all three
are expensive precisely because they are being decided under time pressure. The
information needed to avoid that position is available *years* earlier, and free.

TWO AXES, NOT ONE

A version-lag report ("you are 12 releases behind") conflates two different
situations that call for opposite responses. This measures them separately:

  * **Upstream liveness** -- days since the project's most recent release of any
    version. This is a fact about *them*: is anyone still shipping?
  * **Our lag** -- how far the pinned version sits behind the latest, in both
    releases and elapsed time. This is a fact about *us*.

Crossed, they give the four states that actually differ in what you should do:

                     | upstream releasing   | upstream dormant
    -----------------|----------------------|---------------------------------
    we are current   | HEALTHY              | STRANDED  -- we hold the last
                     |                      | release that may ever exist
    we are behind    | LAGGING -- our debt, | ZOMBIE    -- behind, with no
                     | fixable by updating  | upstream to update to

LAGGING is work. STRANDED is a planning problem: nothing is wrong today, and
there is no upstream to rely on tomorrow, so it wants either a deliberate
exit or a decision to steward the component ourselves. ZOMBIE is both at once
and is the state OSSRA is really describing.

DORMANT IS AN OBSERVATION, NOT AN ACCUSATION

A quiet project is not necessarily an abandoned one. Small, complete libraries
legitimately stop releasing because they are finished -- there is no bug to fix
and no feature to add. Treating "no release in two years" as proof of
abandonment would flag those and train everyone to ignore the report, which is
the failure mode this is trying to avoid rather than cause.

So the vocabulary here is deliberately descriptive. `dormant` means exactly
"no release in N days", which is a checkable fact. Whether that dormancy is
maturity or abandonment is a judgement a human makes once, and records -- see
`OBSOLESCENCE_ACCEPTED` below.

FAILING TO CHECK IS NOT THE SAME AS CHECKING CLEAN

Same rule as the vulnerability census: if a registry cannot be reached, that
package is recorded as `errored` and `checked_ok` goes false. A network problem
must never render as "everything is maintained". This is the failure mode that
has bitten this estate repeatedly -- a tool exiting 0 while having read less
than it claimed -- and it is designed out here rather than patched later.

USAGE

    python scripts/obsolescence_census.py            # write the census
    python scripts/obsolescence_census.py --check    # CI: fail on ZOMBIE
    python scripts/obsolescence_census.py --check --fail-on stranded

CONNECTIVITY

The census is written as structured JSON at `logs/obsolescence_census.json` with
a stable schema, so it is consumable beyond CI: The Observatory can ingest it as
a periodic estate-health signal, and CranBania can raise a review card per
STRANDED component rather than waiting for the annual audit to notice. Under the
EU Cyber Resilience Act this is also the evidence that component maintenance
trajectory was evaluated at selection time and tracked continuously, which the
CRA expects of any product placed on the EU market for a five-year support
period.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import http.client
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CENSUS = REPO / "logs" / "obsolescence_census.json"

# The surfaces whose *direct* dependencies are measured. Direct-only is a
# deliberate scope, not a shortcut: the CRA requires an SBOM covering at least
# direct dependencies, a transitive sweep of this estate would be thousands of
# packages against two public registries, and -- most importantly -- a transitive
# component is not independently actionable. You cannot update it; you update
# the direct dependency that pulls it.
PY_MANIFESTS = ("requirements.txt",)
NPM_DIRS = (
    "web",
    "tranc3-bots",
    "cloudflare/tranc3-ai",
    "cloudflare/infinity-void",
    "cloudflare/trancendos-api-gateway",
)

# OSSRA's own threshold for "showing no development": two years.
DORMANT_DAYS = 730

# Being a couple of patch releases behind is not maintenance debt, it is Tuesday.
# This is the point at which our lag stops being noise and starts being a fact
# worth reporting.
LAGGING_DAYS = 365

HTTP_TIMEOUT = 20
MAX_WORKERS = 8
RETRIES = 3

# Where a human has recorded that a dormant component is deliberately carried.
# Same principle as the vulnerability census's accepted-risk register: an
# undocumented dormant dependency and a reviewed one are different states, and
# the report is only useful if it can tell them apart.
ACCEPT_FILE = REPO / "docs" / "governance" / "OBSOLESCENCE-ACCEPTED.md"
ACCEPT_ROW = re.compile(r"^\|\s*`?([A-Za-z0-9._@/-]+)`?\s*\|")

HEALTHY, LAGGING, STRANDED, ZOMBIE = "healthy", "lagging", "stranded", "zombie"
STATES = (HEALTHY, LAGGING, STRANDED, ZOMBIE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime | None:
    """Parse a registry timestamp, tolerating the several shapes they emit."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    # PyPI emits microseconds; npm emits milliseconds; both may omit either.
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _get_json(url: str) -> dict:
    """Fetch JSON with bounded retries.

    Raises on final failure rather than returning a sentinel, because a caller
    that cannot tell "no data" from "empty data" is exactly how a scan reports
    clean for something it never read.
    """
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "trancendos-obsolescence-census",
                },
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            # IncompleteRead descends from HTTPException, NOT OSError, so without
            # this it escaped the retry loop entirely. It is also the failure this
            # loop most needs to cover: some registry documents are large (the
            # wrangler metadata is ~29MB of version history) and a truncated
            # transfer is transient, not a real answer about the package.
            http.client.HTTPException,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"{url}: {last}")


def _accepted_names() -> set[str]:
    """Package names a human has reviewed and recorded as deliberately carried."""
    names: set[str] = set()
    if not ACCEPT_FILE.is_file():
        return names
    for line in ACCEPT_FILE.read_text(errors="replace").splitlines():
        match = ACCEPT_ROW.match(line.strip())
        if match and match.group(1).lower() not in {"package", "name"}:
            names.add(match.group(1).lower())
    return names


def _read_python_pins(manifest: str) -> list[tuple[str, str]]:
    """(name, pinned_version) for every exactly-pinned requirement."""
    path = REPO / manifest
    pins = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            # Non-exact pins have no single version to compare against. Recorded
            # as a finding rather than skipped silently -- an unpinned dependency
            # is itself a supply-chain weakness (it is what a compromised release
            # needs to reach you), so it should surface, not vanish.
            name = re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].strip()
            if name:
                pins.append((name, ""))
            continue
        name, _, version = line.partition("==")
        pins.append((re.split(r"\[", name, maxsplit=1)[0].strip(), version.split()[0].strip()))
    return pins


def _read_npm_pins(rel_dir: str) -> list[tuple[str, str]]:
    """(name, declared_range) for every direct dependency of one package.json."""
    path = REPO / rel_dir / "package.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text())
    pins = []
    for block in ("dependencies", "devDependencies"):
        for name, spec in (data.get(block) or {}).items():
            pins.append((name, str(spec)))
    return pins


def _our_lag(
    pinned: str, latest: str, our_when: datetime | None, latest_when: datetime | None
) -> float | None:
    """Elapsed time between our pinned release and the latest STABLE release.

    Measured against the latest stable specifically, not against the newest
    upload of any kind. A project that publishes a release candidate after its
    last stable is still the newest thing in the registry, and comparing to it
    would report a lag for a pin that is in fact current -- which is how a
    dependency on the latest version gets mislabelled as neglected. Whether
    those pre-releases happened still counts toward upstream *liveness*; it just
    does not count against *us*.

    Returns 0.0 when we hold the latest stable, and None when the comparison
    cannot be made (an npm range rather than an exact version, a yanked
    release), because unknown must stay distinguishable from fine.
    """
    if pinned and latest and pinned == latest:
        return 0.0
    if our_when is None or latest_when is None:
        return None
    return max(0.0, (latest_when - our_when).total_seconds() / 86400)


def _classify(latest_age_days: float, our_lag_days: float | None, dormant_days: int) -> str:
    """Cross upstream liveness with our own lag into one of the four states."""
    dormant = latest_age_days >= dormant_days
    behind = our_lag_days is not None and our_lag_days >= LAGGING_DAYS
    if dormant and behind:
        return ZOMBIE
    if dormant:
        return STRANDED
    if behind:
        return LAGGING
    return HEALTHY


def _probe_pypi(name: str, pinned: str, dormant_days: int) -> dict:
    data = _get_json(f"https://pypi.org/pypi/{urllib.request.quote(name)}/json")
    releases = data.get("releases") or {}
    latest = (data.get("info") or {}).get("version") or ""

    # Newest upload across ALL releases, not just the latest version string --
    # a project that only ships patches to an old line is still alive.
    newest: datetime | None = None
    for files in releases.values():
        for f in files or []:
            when = _parse_iso(f.get("upload_time_iso_8601") or "")
            if when and (newest is None or when > newest):
                newest = when
    if newest is None:
        raise RuntimeError(f"{name}: no dated releases on PyPI")

    def uploaded(version: str) -> datetime | None:
        for f in releases.get(version) or []:
            when = _parse_iso(f.get("upload_time_iso_8601") or "")
            if when:
                return when
        return None

    now = _now()
    latest_age = (now - newest).total_seconds() / 86400
    our_lag = _our_lag(pinned, latest, uploaded(pinned), uploaded(latest))
    return {
        "name": name,
        "ecosystem": "pip",
        "pinned": pinned,
        "latest": latest,
        "last_release_at": newest.isoformat(),
        "days_since_last_release": round(latest_age, 1),
        "our_version_lag_days": round(our_lag, 1) if our_lag is not None else None,
        "state": _classify(latest_age, our_lag, dormant_days),
    }


def _probe_npm(name: str, spec: str, dormant_days: int) -> dict:
    data = _get_json(f"https://registry.npmjs.org/{urllib.request.quote(name, safe='@/')}")
    times = data.get("time") or {}
    latest = ((data.get("dist-tags") or {}).get("latest")) or ""

    newest: datetime | None = None
    for key, value in times.items():
        if key in {"created", "modified"}:
            continue
        when = _parse_iso(str(value))
        if when and (newest is None or when > newest):
            newest = when
    if newest is None:
        raise RuntimeError(f"{name}: no dated versions on the npm registry")

    # npm specs are ranges (^1.2.3), not pins, so exact-version lookup is only
    # attempted for the exact-version case; otherwise our lag is unknown and is
    # reported as unknown rather than guessed.
    exact = spec.strip()
    our_when = _parse_iso(str(times.get(exact, ""))) if re.fullmatch(r"\d[\w.+-]*", exact) else None

    now = _now()
    latest_age = (now - newest).total_seconds() / 86400
    our_lag = _our_lag(exact, latest, our_when, _parse_iso(str(times.get(latest, ""))))
    return {
        "name": name,
        "ecosystem": "npm",
        "pinned": spec,
        "latest": latest,
        "last_release_at": newest.isoformat(),
        "days_since_last_release": round(latest_age, 1),
        "our_version_lag_days": round(our_lag, 1) if our_lag is not None else None,
        "state": _classify(latest_age, our_lag, dormant_days),
    }


def build_census(dormant_days: int = DORMANT_DAYS) -> dict:
    """Probe every direct dependency and classify it; never guess on failure."""
    accepted = _accepted_names()
    jobs: list[tuple[str, str, str, str]] = []  # (ecosystem, surface, name, spec)

    for manifest in PY_MANIFESTS:
        for name, version in _read_python_pins(manifest):
            jobs.append(("pip", manifest, name, version))
    for rel_dir in NPM_DIRS:
        for name, spec in _read_npm_pins(rel_dir):
            jobs.append(("npm", rel_dir, name, spec))

    findings: list[dict] = []
    errors: list[dict] = []

    def run(job):
        ecosystem, surface, name, spec = job
        try:
            probe = (
                _probe_pypi(name, spec, dormant_days)
                if ecosystem == "pip"
                else _probe_npm(name, spec, dormant_days)
            )
            probe["surface"] = surface
            probe["accepted"] = name.lower() in accepted
            return ("ok", probe)
        except Exception as exc:  # noqa: BLE001 - any failure means "unknown", never "fine"
            return (
                "err",
                {"name": name, "ecosystem": ecosystem, "surface": surface, "reason": str(exc)},
            )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for kind, payload in pool.map(run, jobs):
            (findings if kind == "ok" else errors).append(payload)

    # An unpinned Python requirement is its own finding, surfaced rather than
    # buried: it is the condition a compromised or typosquatted release needs.
    unpinned = [f["name"] for f in findings if f["ecosystem"] == "pip" and not f["pinned"]]

    counts = {state: sum(1 for f in findings if f["state"] == state) for state in STATES}
    unaccepted = [f for f in findings if f["state"] in (ZOMBIE, STRANDED) and not f["accepted"]]

    return {
        "generated_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dormant_threshold_days": dormant_days,
        "lagging_threshold_days": LAGGING_DAYS,
        "checked_ok": not errors,
        "packages_checked": len(findings),
        "packages_errored": len(errors),
        "errored": errors,
        "counts": counts,
        "unpinned_python": unpinned,
        "undocumented_dormant": [f["name"] for f in unaccepted],
        "findings": sorted(findings, key=lambda f: -f["days_since_last_release"]),
    }


def main() -> int:
    """Write the census; with --check, fail on the chosen severity or worse."""
    ap = argparse.ArgumentParser(description="Measure dependency obsolescence across the estate.")
    ap.add_argument("--check", action="store_true", help="exit non-zero on failing findings")
    ap.add_argument(
        "--fail-on",
        choices=("zombie", "stranded", "never"),
        default="zombie",
        help="severity that fails --check (default: zombie)",
    )
    ap.add_argument("--dormant-days", type=int, default=DORMANT_DAYS)
    args = ap.parse_args()

    if args.dormant_days < 1:
        print("[ERROR] --dormant-days must be positive", file=sys.stderr)
        return 2

    census = build_census(args.dormant_days)
    CENSUS.parent.mkdir(parents=True, exist_ok=True)
    CENSUS.write_text(json.dumps(census, indent=2) + "\n")

    counts = census["counts"]
    print(f"packages checked : {census['packages_checked']} ({census['packages_errored']} errored)")
    print(f"  healthy        : {counts[HEALTHY]}")
    print(f"  lagging        : {counts[LAGGING]}   (we are behind; upstream is releasing)")
    print(f"  stranded       : {counts[STRANDED]}   (we are current; upstream has gone quiet)")
    print(f"  zombie         : {counts[ZOMBIE]}   (behind, with no upstream to update to)")
    if census["unpinned_python"]:
        print(f"  unpinned (pip) : {', '.join(census['unpinned_python'])}")

    for finding in census["findings"]:
        if finding["state"] in (ZOMBIE, STRANDED):
            flag = "" if finding["accepted"] else "  UNDOCUMENTED"
            print(
                f"  {finding['state']:<9} {finding['name']:<28} "
                f"last release {finding['days_since_last_release']:.0f}d ago{flag}"
            )

    if not args.check:
        return 0

    if not census["checked_ok"]:
        print(
            f"\n[FAIL] {census['packages_errored']} package(s) could not be checked; "
            "an unreachable registry is not a clean result.",
            file=sys.stderr,
        )
        for err in census["errored"][:10]:
            print(f"        {err['name']}: {err['reason']}", file=sys.stderr)
        return 1

    if args.fail_on == "never":
        print("\nObsolescence census: RECORDED (no severity gate)")
        return 0

    failing = {ZOMBIE} if args.fail_on == "zombie" else {ZOMBIE, STRANDED}
    offenders = [f for f in census["findings"] if f["state"] in failing and not f["accepted"]]
    if offenders:
        print(
            f"\n[FAIL] {len(offenders)} undocumented {args.fail_on}-or-worse component(s):",
            file=sys.stderr,
        )
        for f in offenders:
            print(
                f"        {f['name']} ({f['state']}) — last release {f['days_since_last_release']:.0f}d ago",
                file=sys.stderr,
            )
        print(
            f"\n        Either update/replace them, or record the decision in\n"
            f"        {ACCEPT_FILE.relative_to(REPO)} with a reason.",
            file=sys.stderr,
        )
        return 1

    print(f"\nObsolescence census: PASSED (no undocumented {args.fail_on}-or-worse components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

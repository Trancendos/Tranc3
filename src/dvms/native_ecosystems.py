"""Go and Rust dependency scanning — the measured reason Cryptex missed 374 findings.

WHY THIS EXISTS

The census scanned pip and npm. This tree also ships **3 `go.mod`** and
**9 `Cargo.toml`** files across `aeonmind/`, `rust_extensions/`,
`src/nanoservices/` and three Rust workers, and none of them were ever read by
it. That is not a gap in coverage depth; it is a whole class of surface the
platform's own vulnerability control could not see.

It is exactly why a gRPC-Go heap-exhaustion advisory, `golang.org/x/net`, the
PyO3 and protobuf crates and their neighbours appear in an external report and
never in Cryptex's. The census was not wrong about what it scanned. It was
silent about what it did not, which is the worse failure: a control that
reports green over surfaces it never opened.

WHY OSV AND NOT `govulncheck` / `cargo-audit`

Both of those need their own toolchain, their own install step in every CI job,
and their own vulnerability database fetch. OSV.dev serves the same advisories
— the Go vulnerability database and RustSec both publish INTO it — over one
batched HTTP call, with no toolchain at all.

The trade is real and worth stating plainly rather than discovering later:

  * `govulncheck` does call-graph **reachability**. It reports the subset of
    advisories whose vulnerable symbol your code actually calls, and so reports
    fewer findings than this does.
  * This resolves package *versions* and asks whether any advisory affects
    them. It cannot know whether the vulnerable function is ever called.

So this OVER-reports relative to `govulncheck`, never under-reports. For a
gate that is the correct direction — a finding you must dismiss costs a
minute, a finding you never saw costs an incident — but it means a Go finding
here is "this version is affected", not "this code is exploitable", and the
census records that distinction rather than letting a reader assume the
stronger claim.

WHAT COUNTS AS UNSCANNABLE

Six of the nine `Cargo.toml` files have no `Cargo.lock`. A `Cargo.toml`
declares version *ranges* (`serde = "1.0"`), and an advisory applies to an
exact version, so without a lockfile there is nothing to ask OSV about. Those
surfaces are reported **errored**, never skipped and never counted clean —
the same rule `_scan_npm` already applies to a `package.json` with no
lockfile. An unscannable surface that reports as clean is the failure mode
this whole module exists to correct.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/"

#: An id is interpolated into `OSV_VULN_URL`, so its shape is checked rather
#: than trusted. `GHSA-../../etc` satisfies a prefix match and would walk the
#: API path; anything but the strict form is refused.
_SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9._-]+$")

#: OSV accepts up to 1000 queries per batch. Half that keeps a single request
#: small enough to retry cheaply when the API is slow.
BATCH_SIZE = 500

#: Matches the census's own retry discipline: a transient API failure must not
#: read as a clean scan, and must not cost a whole scheduled run either.
ATTEMPTS = 3
BACKOFF_SECONDS = 5
TIMEOUT_SECONDS = 60

# `github.com/google/uuid v1.21.0` inside a require block, and the single-line
# form `require github.com/x/y v1.2.3`. The `// indirect` marker is kept: an
# indirect dependency is still compiled into the binary and still exploitable,
# and dropping it is how a transitive advisory becomes somebody else's problem.
_GO_REQUIRE_LINE = re.compile(
    r"^\s*(?:require\s+)?(?P<name>[A-Za-z0-9][^\s]*\.[^\s]*/[^\s]*)\s+(?P<version>v[^\s/]+)"
)
_GO_BLOCK_OPEN = re.compile(r"^\s*require\s*\(\s*$")

# A `[[package]]` stanza in Cargo.lock. Only registry packages are queried: a
# path or git dependency has no crates.io advisory to match.
_LOCK_NAME = re.compile(r'^name\s*=\s*"(?P<value>[^"]+)"')
_LOCK_VERSION = re.compile(r'^version\s*=\s*"(?P<value>[^"]+)"')
_LOCK_SOURCE = re.compile(r'^source\s*=\s*"(?P<value>[^"]+)"')


@dataclass
class NativeSurface:
    """One Go module or Rust crate, and what scanning it produced."""

    surface: str
    ecosystem: str
    errored: bool = False
    reason: str = ""
    findings: List[dict] = field(default_factory=list)
    #: Packages successfully resolved to an exact version and queried. Reported
    #: so "no findings" can be told apart from "nothing was asked".
    queried: int = 0

    def to_dict(self) -> dict:
        return {
            "surface": self.surface,
            "ecosystem": self.ecosystem,
            "errored": self.errored,
            "reason": self.reason,
            "findings": self.findings,
            "packages_queried": self.queried,
        }


def parse_go_mod(text: str) -> List[Tuple[str, str]]:
    """(module, version) pairs from a go.mod, direct and indirect alike."""
    out: List[Tuple[str, str]] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0] if not raw.strip().startswith("//") else ""
        stripped = line.strip()
        if _GO_BLOCK_OPEN.match(line):
            in_block = True
            continue
        if in_block and stripped == ")":
            in_block = False
            continue
        if not stripped:
            continue
        # Outside a require block only an explicit `require x v1` line counts;
        # `module`, `go`, `toolchain` and `replace` lines are not dependencies.
        if not in_block and not stripped.startswith("require "):
            continue
        match = _GO_REQUIRE_LINE.match(line)
        if match:
            out.append((match.group("name"), match.group("version")))
    return out


def parse_cargo_lock(text: str) -> List[Tuple[str, str]]:
    """(crate, version) pairs for registry packages in a Cargo.lock.

    Parsed line-wise rather than with a TOML reader so a lockfile whose format
    version this Python does not know still yields its package list. A crate
    with no `source` is the workspace's own member crate and has no advisory to
    look up, so it is excluded rather than queried and silently missed.
    """
    out: List[Tuple[str, str]] = []
    name: Optional[str] = None
    version: Optional[str] = None
    source: Optional[str] = None

    def flush() -> None:
        if name and version and source and source.startswith("registry+"):
            out.append((name, version))

    for raw in text.splitlines():
        line = raw.strip()
        if line == "[[package]]":
            flush()
            name = version = source = None
            continue
        for pattern, target in (
            (_LOCK_NAME, "name"),
            (_LOCK_VERSION, "version"),
            (_LOCK_SOURCE, "source"),
        ):
            match = pattern.match(line)
            if match:
                value = match.group("value")
                if target == "name":
                    name = value
                elif target == "version":
                    version = value
                else:
                    source = value
                break
    flush()
    return out


def _released_fix(vuln: dict) -> List[str]:
    """Fixed versions that are actual releases, not commit hashes.

    A GIT range names a commit. A commit is not a version anybody can pin, and
    calling it a fix sends a reader after a release that has not shipped —
    which would classify a genuinely unfixable finding as `fixable` and fail
    the gate over work nobody can do.

    This reads the FULL OSV record. It has to: `/v1/querybatch` returns only
    `{id, modified}` per hit, with no `affected` block at all, so running this
    over a batch result reports "no released fix" for every finding on earth.
    Measured, not reasoned about — the first run of this module said exactly
    that about `GHSA-vp52-pcj8-j9qc`, which OSV records as fixed in gRPC-Go
    1.83.1. `hydrate` exists to close that hole and `query_osv` refuses to
    return a finding it could not hydrate.
    """
    fixes: List[str] = []
    for affected in vuln.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        for entry in affected.get("ranges") or []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("type", "")).upper() == "GIT":
                continue
            for event in entry.get("events") or []:
                if isinstance(event, dict) and event.get("fixed"):
                    fixes.append(str(event["fixed"]))
    return sorted(set(fixes))


def _severity(vuln: dict) -> str:
    specific = vuln.get("database_specific")
    if isinstance(specific, dict) and specific.get("severity"):
        return str(specific["severity"]).lower()
    return "unknown"


def hydrate(identifier: str, opener=None) -> Optional[dict]:
    """The full OSV record for one advisory, or `None` if it could not be read.

    `None` is never treated as "no fix exists" by any caller. Not knowing
    whether a patch shipped and asserting that none did are different claims,
    and only the second one lets a real remediation get filed as accepted risk.
    """
    if not _SAFE_ID.match(identifier):
        return None
    url = OSV_VULN_URL + identifier
    if not url.startswith(OSV_VULN_URL):  # pragma: no cover - defensive
        return None
    send = opener or urllib.request.urlopen
    for attempt in range(1, ATTEMPTS + 1):
        try:
            # The prefix is a module constant and `_SAFE_ID` has already
            # restricted the only variable part, so the scheme cannot be
            # redirected by any input reaching this line.
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with send(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            payload = None
        if isinstance(payload, dict):
            return payload
        if attempt < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * (2 ** (attempt - 1)))
    return None


def _post_batch(queries: Sequence[dict], opener=None) -> Optional[List[dict]]:
    """One OSV batch call, retried. `None` means unscannable, never clean."""
    body = json.dumps({"queries": list(queries)}).encode("utf-8")
    request = urllib.request.Request(
        OSV_BATCH_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    send = opener or urllib.request.urlopen
    for attempt in range(1, ATTEMPTS + 1):
        try:
            # The URL is the module-level constant above; nothing a caller
            # supplies reaches it, so the scheme cannot be redirected.
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with send(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return payload["results"]
        if attempt < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * (2 ** (attempt - 1)))
    return None


def query_osv(
    packages: Sequence[Tuple[str, str]], ecosystem: str, opener=None
) -> Optional[List[dict]]:
    """Advisories affecting these exact versions, or `None` if OSV was unusable.

    `None` and `[]` are different answers and are kept different: the first
    means nobody asked, the second means nobody found anything. Collapsing them
    is how an unreachable API becomes a green scan.

    Two calls per advisory, not one. `/v1/querybatch` answers "is this version
    affected" and returns nothing but an id, so every finding is then hydrated
    from `/v1/vulns/{id}` for the fix versions and severity. A hit that cannot
    be hydrated makes the WHOLE surface unscannable rather than being reported
    with an empty `fix_versions`, because an empty list there is read as "no
    patch exists" and would let a remediable finding be dispositioned as an
    accepted risk. One extra call per distinct advisory is cheap; this estate
    has one.
    """
    if not packages:
        return []
    hits: List[Tuple[str, str, str]] = []
    for start in range(0, len(packages), BATCH_SIZE):
        chunk = packages[start : start + BATCH_SIZE]
        queries = [
            {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
            for name, version in chunk
        ]
        results = _post_batch(queries, opener=opener)
        if results is None:
            return None
        # A short results list would silently mis-pair the tail of the chunk, so
        # stop at whichever runs out: under-reporting the packages OSV did
        # answer for is better than attributing an advisory to the wrong crate.
        for (name, version), result in zip(chunk, results, strict=False):
            if not isinstance(result, dict):
                continue
            for vuln in result.get("vulns") or []:
                if isinstance(vuln, dict) and vuln.get("id"):
                    hits.append((name, version, str(vuln["id"])))

    records: Dict[str, dict] = {}
    for identifier in sorted({identifier for _, _, identifier in hits}):
        record = hydrate(identifier, opener=opener)
        if record is None:
            return None
        records[identifier] = record

    findings: List[dict] = []
    for name, version, identifier in hits:
        record = records[identifier]
        aliases = [str(a) for a in (record.get("aliases") or [])]
        findings.append(
            {
                "package": name,
                "version": version,
                "id": identifier,
                "aliases": sorted(set(aliases) - {identifier}),
                "severity": _severity(record),
                "summary": str(record.get("summary") or "")[:200],
                "fix_versions": _released_fix(record),
            }
        )
    return findings


def _discover(root: str, filename: str, excluded: Iterable[str]) -> List[str]:
    found: List[str] = []
    skip = {"node_modules", ".git", ".venv", "venv", "__pycache__", "target"}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        if filename not in files:
            continue
        rel = os.path.relpath(os.path.join(base, filename), root).replace(os.sep, "/")
        if any(rel.startswith(f"{prefix}/") or rel == prefix for prefix in excluded):
            continue
        found.append(rel)
    return sorted(found)


def discover_go_modules(root: str, excluded: Iterable[str] = ()) -> List[str]:
    return _discover(root, "go.mod", excluded)


def discover_rust_crates(root: str, excluded: Iterable[str] = ()) -> List[str]:
    return _discover(root, "Cargo.toml", excluded)


def scan_go_module(root: str, rel: str, opener=None) -> NativeSurface:
    surface = NativeSurface(surface=rel, ecosystem="go")
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        surface.errored = True
        surface.reason = f"go.mod unreadable: {type(exc).__name__}"
        return surface
    packages = parse_go_mod(text)
    surface.queried = len(packages)
    results = query_osv(packages, "Go", opener=opener)
    if results is None:
        surface.errored = True
        surface.reason = f"OSV unreachable after {ATTEMPTS} attempts"
        return surface
    surface.findings = results
    return surface


def scan_rust_crate(root: str, rel: str, opener=None) -> NativeSurface:
    surface = NativeSurface(surface=rel, ecosystem="cargo")
    lock = os.path.join(os.path.dirname(os.path.join(root, rel)), "Cargo.lock")
    if not os.path.isfile(lock):
        surface.errored = True
        surface.reason = (
            "no Cargo.lock — Cargo.toml declares version ranges and an advisory "
            "applies to an exact version, so there is nothing to query"
        )
        return surface
    try:
        with open(lock, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        surface.errored = True
        surface.reason = f"Cargo.lock unreadable: {type(exc).__name__}"
        return surface
    packages = parse_cargo_lock(text)
    surface.queried = len(packages)
    results = query_osv(packages, "crates.io", opener=opener)
    if results is None:
        surface.errored = True
        surface.reason = f"OSV unreachable after {ATTEMPTS} attempts"
        return surface
    surface.findings = results
    return surface


def scan_all(root: str, excluded: Iterable[str] = (), opener=None) -> List[Dict]:
    """Every Go module and Rust crate in the tree, in the census's surface shape."""
    excluded = tuple(excluded)
    out: List[Dict] = []
    for rel in discover_go_modules(root, excluded):
        out.append(scan_go_module(root, rel, opener=opener).to_dict())
    for rel in discover_rust_crates(root, excluded):
        out.append(scan_rust_crate(root, rel, opener=opener).to_dict())
    return out

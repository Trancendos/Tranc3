#!/usr/bin/env python3
"""Emit a CycloneDX SBOM per container, from the manifests each one ships.

The owner asked that anything inside a container be logged, and noted that other
AIs had said "mark these as SBOMs" without being sure. They are right to be
unsure, because "SBOM" covers two artifacts that differ in what they can tell
you, and conflating them produces an inventory that looks complete and is not:

  * an **image SBOM** is produced from a built image (syft, trivy, docker sbom).
    It sees everything: OS packages from the base layer, system libraries,
    language packages, files added by every RUN. It is the one that answers "is
    this CVE in my estate".
  * a **source SBOM** is produced from the dependency manifests in the repository.
    It sees declared application dependencies and nothing else -- no base-image
    packages, no transitive resolution, no OS libraries.

This script emits the second kind, and says so in every document it writes:
`trancendos:sbom-scope = source`. It does that because the first kind needs syft
or trivy and a built image, neither of which exists in every environment this
runs in -- and an empty SBOM directory is a worse answer than an honestly
labelled partial one. What it must never do is emit a source SBOM labelled as
though it were an image SBOM; a container whose base layer is unexamined would
then read as fully inventoried.

`--strict` refuses to emit source SBOMs at all, for use once image SBOMs exist.

Usage:
    python3 scripts/build_container_sboms.py           # write source SBOMs
    python3 scripts/build_container_sboms.py --check   # fail if stale
    python3 scripts/build_container_sboms.py --report  # coverage only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.cmdb.containers import SBOM_DIR, discover  # noqa: E402

CYCLONEDX_VERSION = "1.6"

# PEP 508-ish: name, optional extras, optional pinned version. Deliberately
# conservative -- a line it cannot parse is recorded as unparsed rather than
# guessed at, because a wrong version in an SBOM is worse than a missing one.
_REQ_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]+\])?\s*"
    r"(?:(?P<op>==|>=|~=|<=|>|<)\s*(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*))?"
)


def _parse_requirements(path: Path) -> tuple[list[dict], list[str]]:
    components: list[dict] = []
    unparsed: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQ_RE.match(line)
        if not match:
            unparsed.append(line)
            continue
        name = match.group("name")
        version = match.group("version") or ""
        component = {
            "type": "library",
            "name": name,
            "bom-ref": f"pkg:pypi/{name}" + (f"@{version}" if version else ""),
            "purl": f"pkg:pypi/{name}" + (f"@{version}" if version else ""),
        }
        if version:
            component["version"] = version
        else:
            # An unpinned dependency is a fact about the container, not a gap in
            # the SBOM: it means the contents differ between two builds of the
            # same image, which is exactly what an inventory should surface.
            component["properties"] = [
                {"name": "trancendos:pinned", "value": "false"},
                {"name": "trancendos:constraint", "value": line},
            ]
        components.append(component)
    return components, unparsed


def build_sbom(container) -> dict:
    components: list[dict] = []
    unparsed: list[str] = []
    sources: list[str] = []
    for manifest in container.requirements:
        path = REPO / manifest
        if not path.is_file() or path.suffix != ".txt":
            continue
        parsed, bad = _parse_requirements(path)
        components.extend(parsed)
        unparsed.extend(bad)
        sources.append(manifest)

    # De-duplicate on bom-ref, keeping first occurrence.
    seen: set[str] = set()
    deduped = []
    for component in components:
        ref = component["bom-ref"]
        if ref in seen:
            continue
        seen.add(ref)
        deduped.append(component)

    properties = [
        # The scope label. Everything downstream -- the CI register, the Ice Box
        # management view, any future CVE match -- has to be able to tell that
        # this document did not look inside the base image.
        {"name": "trancendos:sbom-scope", "value": "source"},
        {
            "name": "trancendos:sbom-scope-note",
            "value": (
                "Declared application dependencies only. Base-image OS packages, "
                "system libraries and transitively resolved versions are NOT "
                "included. Generate an image SBOM with syft or trivy for those."
            ),
        },
        {"name": "trancendos:provenance", "value": container.provenance},
        {"name": "trancendos:jurisdiction", "value": container.jurisdiction or "_unrouted_"},
        {"name": "trancendos:custodian", "value": "The Ice Box"},
        {"name": "trancendos:ci-id", "value": container.ci_id},
    ]
    for base in container.base_images:
        properties.append({"name": "trancendos:base-image", "value": base})
    for manifest in sources:
        properties.append({"name": "trancendos:manifest", "value": manifest})
    for line in unparsed:
        properties.append({"name": "trancendos:unparsed-requirement", "value": line})
    if not sources:
        properties.append(
            {
                "name": "trancendos:no-manifest",
                "value": (
                    "No requirements manifest ships with this container. For a pulled "
                    "third-party image this is expected and an image SBOM is the only "
                    "way to know its contents."
                ),
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_VERSION,
        # Deterministic serial: a content hash, so regenerating an unchanged
        # container does not produce a diff and --check stays meaningful.
        "serialNumber": "urn:uuid:" + hashlib.sha256(container.ci_id.encode()).hexdigest()[:32],
        "version": 1,
        "metadata": {
            "component": {
                "type": "container",
                "name": container.service,
                "bom-ref": container.ci_id,
                "version": container.image or "built-from-source",
            },
            "properties": properties,
        },
        "components": deduped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if any SBOM is stale")
    parser.add_argument("--report", action="store_true", help="print coverage only")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="refuse to emit source-scope SBOMs (use once image SBOMs exist)",
    )
    args = parser.parse_args(argv)

    containers = discover()
    if not containers:
        print("no containers found — is docker-compose.production.yml present?", file=sys.stderr)
        return 1

    if args.report:
        with_manifest = sum(1 for c in containers if c.requirements)
        print(f"containers:            {len(containers)}")
        print(f"  built here:          {sum(1 for c in containers if c.provenance == 'built')}")
        print(f"  pulled third-party:  {sum(1 for c in containers if c.provenance == 'pulled')}")
        print(f"  shipping a manifest: {with_manifest}")
        print(f"  with an SBOM:        {sum(1 for c in containers if c.has_sbom)}")
        print(
            "\nEvery SBOM this script writes is source-scope. No image SBOM exists "
            "for any container until syft or trivy runs against a built image."
        )
        return 0

    if args.strict:
        print(
            "--strict: refusing to emit source-scope SBOMs. Generate image SBOMs "
            "with syft or trivy instead.",
            file=sys.stderr,
        )
        return 1

    SBOM_DIR.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    written = 0
    for container in containers:
        payload = json.dumps(build_sbom(container), indent=2, ensure_ascii=False) + "\n"
        target = REPO / container.sbom_ref
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != payload:
                stale.append(container.sbom_ref)
            continue
        target.write_text(payload, encoding="utf-8")
        written += 1

    if args.check:
        if stale:
            for ref in stale[:20]:
                print(f"STALE: {ref}", file=sys.stderr)
            if len(stale) > 20:
                print(f"... and {len(stale) - 20} more", file=sys.stderr)
            print("\nRun: python3 scripts/build_container_sboms.py", file=sys.stderr)
            return 1
        print(f"{len(containers)} container SBOMs are current")
        return 0

    print(f"wrote {written} source-scope SBOMs to {SBOM_DIR.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

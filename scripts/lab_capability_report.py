#!/usr/bin/env python3
"""What The Lab could verify *inside its own image*, not on your laptop.

The trap this avoids
--------------------
`src/lab/languages.py` measures the verification tier from binaries on PATH.
Run it on a developer machine and it reports nine languages at TEST, because
that machine has node, go and gcc. Run the same code inside
`workers/the-lab`, built from `python:3.11-slim` with fastapi, starlette,
uvicorn and httpx, and almost none of it is there.

Both numbers are true and only one is about the platform. So this script does
not ask the host what it has: it reads the worker's Dockerfile and
requirements, derives the toolchain that image will actually contain, and
reports the matrix under *that*.

The derivation is deliberately conservative. A binary counts as present only
when something in the image demonstrably installs it — the base image's own
interpreter, an `apt-get install`, a `pip install`, or a `COPY --from` of a
toolchain image. Anything else is absent, so a language cannot claim a tier
by accident.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.lab.languages import LANGUAGES, Verification, skills_matrix  # noqa: E402

WORKER = REPO / "workers" / "the-lab"

#: Binaries a base image is known to provide. Only the interpreter families
#: the estate actually builds on are listed; an unrecognised base contributes
#: nothing, which keeps an unknown image from inflating the matrix.
_BASE_IMAGE_BINARIES: dict[str, tuple[str, ...]] = {
    "python": ("python", "python3", "pip", "sh"),
    "node": ("node", "npm", "npx", "sh"),
    "golang": ("go", "gofmt", "sh"),
    "rust": ("cargo", "rustc", "rustfmt", "sh"),
    "eclipse-temurin": ("java", "javac", "sh"),
}

#: pip distributions that put a differently-named console script on PATH.
_PIP_CONSOLE_SCRIPTS: dict[str, tuple[str, ...]] = {
    "ruff": ("ruff",),
    "mypy": ("mypy",),
    "pytest": ("pytest",),
    "sqlfluff": ("sqlfluff",),
    "yamllint": ("yamllint",),
    "pre-commit": ("pre-commit",),
}


def _image_binaries(reference: str) -> set[str]:
    """Binaries a known base image provides, from an image reference."""
    image = reference.split("@")[0].split(":")[0]
    for prefix, binaries in _BASE_IMAGE_BINARIES.items():
        if image == prefix or image.endswith(f"/{prefix}"):
            return set(binaries)
    return set()


def final_stage(dockerfile: str) -> str:
    """The lines belonging to the last build stage.

    A multi-stage Dockerfile installs toolchains in a builder stage that is
    then discarded — nothing it apt-gets or pip-installs is in the shipped
    image unless a later stage copies it across. Scanning the whole file
    credited those binaries to the running container and would have reported
    verification tiers for tools that are not there, which is the exact
    over-claim this whole module exists to prevent. The Lab's own Dockerfile
    has one stage today; that is a fact about today, not a property to rely on.
    """
    lines = dockerfile.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().upper().startswith("FROM ")]
    if not starts:
        return dockerfile
    return "\n".join(lines[starts[-1] :])


def _base_binaries(dockerfile: str) -> set[str]:
    """The final stage's own base, plus any toolchain image it copies from.

    `COPY --from=<image>` in the final stage does put that image's contents
    into the shipped one, so a recognised toolchain image counts. A
    `--from=<earlier stage>` names a stage rather than an image and matches
    nothing, which errs toward under-reporting.
    """
    stage = final_stage(dockerfile)
    found: set[str] = set()
    for line in stage.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            found |= _image_binaries(line.split()[1])
            continue
        match = re.search(r"COPY\s+--from=(\S+)", stripped, re.IGNORECASE)
        if match:
            found |= _image_binaries(match.group(1))
    return found


def _apt_binaries(dockerfile: str) -> set[str]:
    """Packages an apt-get install line brings in, taken at their own name.

    Debian package names and binary names usually coincide for toolchains
    (gcc, g++, shellcheck). Where they do not, the binary simply reads as
    absent, which errs toward under-reporting capability.
    """
    found: set[str] = set()
    for match in re.finditer(
        r"apt-get\s+(?:-\S+\s+)*install\s+([^\n&|]+)", final_stage(dockerfile)
    ):
        for token in match.group(1).split():
            if token.startswith("-") or token in {"\\", "&&"}:
                continue
            found.add(token)
    return found


def _pip_binaries(dockerfile: str, requirements: str) -> set[str]:
    found: set[str] = set()
    names: set[str] = set()
    for match in re.finditer(r"pip\s+install\s+([^\n&|]+)", final_stage(dockerfile)):
        for token in match.group(1).split():
            if token.startswith("-") or token.endswith(".txt"):
                continue
            names.add(re.split(r"[=<>\[]", token)[0].strip().lower())
    for line in requirements.splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[=<>\[]", line)[0].strip().lower())
    for name in names:
        found.update(_PIP_CONSOLE_SCRIPTS.get(name, ()))
    return found


def image_toolchain(worker_dir: Path = WORKER) -> set[str]:
    """Every binary the built image can be shown to contain."""
    dockerfile = (worker_dir / "Dockerfile").read_text()
    requirements_path = worker_dir / "requirements.txt"
    requirements = requirements_path.read_text() if requirements_path.exists() else ""
    return (
        _base_binaries(dockerfile)
        | _apt_binaries(dockerfile)
        | _pip_binaries(dockerfile, requirements)
    )


def report(worker_dir: Path = WORKER) -> dict[str, object]:
    available = image_toolchain(worker_dir)

    def which(binary: str) -> str | None:
        return f"/usr/bin/{binary}" if binary in available else None

    matrix = skills_matrix(which)
    matrix["image_toolchain"] = sorted(available)
    try:
        matrix["worker"] = str(worker_dir.relative_to(REPO))
    except ValueError:
        # A caller pointing at a checkout outside this repo gets the path it
        # gave. Reporting is not worth raising over.
        matrix["worker"] = str(worker_dir)
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the matrix as JSON.")
    args = parser.parse_args(argv)

    matrix = report()
    if args.json:
        print(json.dumps(matrix, indent=2))
        return 0

    print(f"The Lab — language capability inside {matrix['worker']}")
    print("=" * 64)
    print(f"Languages declared:        {matrix['total']}")
    print(f"Verifiable in this image:  {matrix['verifiable']}")
    print(f"Toolchain in this image:   {', '.join(matrix['image_toolchain']) or 'none'}")
    print()
    print("By verification tier:")
    for tier in Verification:
        print(f"  {tier.value:<6} {matrix['by_verification'][tier.value]:>3}")
    print()
    generate_only = [
        entry["id"]
        for entry in matrix["languages"]
        if entry["verification"] == Verification.NONE.value
    ]
    if generate_only:
        print("Generated but unverifiable — nothing in the image can check these:")
        for chunk in range(0, len(generate_only), 6):
            print("  " + ", ".join(generate_only[chunk : chunk + 6]))
        print()
    print(
        "Generation is unconstrained; verification is not. A language at "
        "`none` means The Lab can write it and prove nothing about it."
    )
    missing = sorted(
        {
            tool.binary
            for lang in LANGUAGES
            for tool in lang.toolchain
            if tool.binary not in matrix["image_toolchain"]
        }
    )
    print(f"\nBinaries that would raise a tier if installed: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from pathlib import Path, PurePosixPath

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

#: Where each of those images actually keeps the executables listed above.
#: A `COPY --from` brings a tool across only when its source path is one of
#: these directories or an ancestor of it. This used to be a single generic
#: list of "toolchain roots" shared by every image, which was wrong in both
#: directions at once: it credited `/usr/bin` for golang and rust, which
#: keep nothing there (`/usr/local/go/bin`, `/usr/local/cargo/bin`), and it
#: did not recognise those directories themselves, so the one COPY that
#: really does ship a Go toolchain read as shipping nothing.
_BASE_IMAGE_ROOTS: dict[str, tuple[str, ...]] = {
    "python": ("/usr/local/bin",),
    "node": ("/usr/local/bin",),
    "golang": ("/usr/local/go/bin",),
    "rust": ("/usr/local/cargo/bin",),
    "eclipse-temurin": ("/opt/java/openjdk/bin",),
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


def _image_key(reference: str) -> str | None:
    """The known base image an image reference names, or None."""
    image = reference.split("@")[0].split(":")[0]
    for prefix in _BASE_IMAGE_BINARIES:
        if image == prefix or image.endswith(f"/{prefix}"):
            return prefix
    return None


def _image_binaries(reference: str) -> set[str]:
    """Binaries a known base image provides, from an image reference."""
    key = _image_key(reference)
    return set(_BASE_IMAGE_BINARIES[key]) if key else set()


def _logical_lines(dockerfile: str) -> list[str]:
    """Dockerfile instructions — comments dropped, continuations joined.

    Two things the raw lines get wrong. A `#` line is not an instruction, so
    scanning raw text credited a commented-out `# RUN apt-get install gcc`
    as an install and reported a verification tier for a compiler nobody
    ships. And a trailing backslash continues one instruction across several
    lines, so a `pip install \\` followed by `  -r requirements.txt` — the
    ordinary way that line is written — read as a pip install of nothing.
    Both are fixed here once, for every scanner below.
    """
    out: list[str] = []
    buffer = ""
    for raw in dockerfile.splitlines():
        line = raw.strip()
        if line.startswith("#") or (not buffer and not line):
            # A comment is never an argument, inside a continuation or out.
            continue
        if line.endswith("\\"):
            buffer += line[:-1].strip() + " "
            continue
        joined = (buffer + line).strip()
        buffer = ""
        if joined:
            out.append(joined)
    if buffer.strip():
        out.append(buffer.strip())
    return out


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
    lines = _logical_lines(dockerfile)
    starts = [i for i, line in enumerate(lines) if line.upper().startswith("FROM ")]
    if not starts:
        return "\n".join(lines)
    return "\n".join(lines[starts[-1] :])


def _covers(source: str, executables: str) -> bool:
    """Does copying `source` bring everything in `executables` with it?"""
    src = PurePosixPath(source.rstrip("/") or "/")
    target = PurePosixPath(executables)
    return src == target or src in target.parents


def _copies_the_toolchain(source_paths: list[str], image: str) -> bool:
    """Does this COPY bring *this image's* executables across?

    `COPY --from=golang:1.22 /app/binary /app/binary` copies one file. It
    does not put `go` and `gofmt` in the shipped image, and crediting them
    because the source image happens to contain them is the over-claim this
    whole report exists to prevent — reintroduced through the back door.
    Which paths do carry them is a property of the image, not a constant:
    `/usr/bin` ships a Go toolchain from nowhere, and `/usr/local/go` ships
    one from golang and nothing at all from python.
    """
    key = _image_key(image)
    if key is None:
        return False
    return any(
        _covers(path, executables)
        for path in source_paths
        for executables in _BASE_IMAGE_ROOTS[key]
    )


def _base_binaries(dockerfile: str) -> set[str]:
    """The final stage's own base, plus a toolchain image it copies wholesale.

    `COPY --from=<image> <src> <dst>` only puts `<src>` into the shipped
    image. A narrow source copies data; only a copy rooted at a toolchain
    directory brings the executables. A `--from=<earlier stage>` names a
    stage rather than an image and matches no known base, which errs toward
    under-reporting.
    """
    stage = final_stage(dockerfile)
    found: set[str] = set()
    for line in stage.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            found |= _image_binaries(line.split()[1])
            continue
        match = re.search(r"COPY\s+--from=(\S+)\s+(.*)$", stripped, re.IGNORECASE)
        if match:
            sources = [t for t in match.group(2).split() if not t.startswith("--")][:-1]
            if _copies_the_toolchain(sources, match.group(1)):
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


#: `pip install -r requirements.txt`, in any of its spellings: `pip3`, a
#: `python -m pip` invocation, `--requirement`, and the `=`-joined or
#: directly-attached argument forms. Requiring a literal `pip install` with
#: a space-separated `-r` missed real Dockerfiles and silently dropped the
#: whole requirements file from the toolchain.
_REQUIREMENTS_INSTALL = re.compile(
    r"(?:python[\d.]*\s+-m\s+)?pip[\d.]*\s+install\b[^\n&|]*?"
    r"(?:--requirement|-r)[=\s]*\S*\.txt"
)


def _pip_binaries(dockerfile: str, requirements: str) -> set[str]:
    """Console scripts pip puts on PATH — in the FINAL stage only.

    requirements.txt is credited only when the final stage actually installs
    from it. A multi-stage build that pip-installs in a discarded builder
    ships none of those tools, and crediting the file regardless would report
    verification tiers for a toolchain the running container does not have.
    """
    stage = final_stage(dockerfile)
    found: set[str] = set()
    names: set[str] = set()
    for match in re.finditer(r"pip\s+install\s+([^\n&|]+)", stage):
        for token in match.group(1).split():
            if token.startswith("-") or token.endswith(".txt"):
                continue
            names.add(re.split(r"[=<>\[]", token)[0].strip().lower())
    if _REQUIREMENTS_INSTALL.search(stage):
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

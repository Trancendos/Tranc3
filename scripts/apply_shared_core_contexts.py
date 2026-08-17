#!/usr/bin/env python3
"""Deliver the Shared Functional Services Core to own-context workers.

THE PROBLEM

73 services in `docker-compose.production.yml` build from their own directory
(`context: ./workers/<name>`), so nothing at the repo root is in their images.
`Dimensional/` (the SFSC) and `src/observability/` are unreachable to them. The
consequences are measured, not hypothetical:

  * 37 of those workers import `src.observability.worker_setup`. The import is
    guarded, so it does not crash them — it silently does nothing. Prometheus
    metrics and OTel tracing are absent platform-wide while CLAUDE.md claims
    "W3C TraceContext propagation across all workers".
  * 41 services hand-rolled their own X-Internal-Secret check because they could
    not import a shared one. Four failed open; 18 compared with `!=`.

THE MECHANISM: NAMED BUILD CONTEXTS

BuildKit lets a build read from contexts other than its own, addressed by name:

    COPY --from=sharedcore . /app/Dimensional/

supplied by `additional_contexts:` in Compose, or `--build-context` on a direct
`docker build`. The worker's own context is untouched, nothing is duplicated in
git, and there is exactly one copy of the core to keep correct.

WHY NOT THE ALTERNATIVES

  Vendoring (copy the trees into each build context) works — hive-service and
  dimensional-nexus-service already do it — but it means 37 duplicated subtrees,
  each carrying a "keep in sync" promise. `check_worker_build_context.py`
  machine-checks that promise, which makes vendoring safe, not cheap.

  A shared base image (`docker/Dockerfile.worker-base`, removed alongside this
  script) was the previous plan. It was rejected on evidence: it needs a
  registry the build can reach, it needs publishing *before* every worker build
  or each `FROM` fails, and it forces one Python minor version on all consumers —
  36 of the 37 are python:3.11 but `imind` is python:3.12, which would have
  needed a second base image. Named contexts have none of those properties: no
  registry, no ordering constraint, and the Python version is irrelevant because
  only files are copied.

  A wheel does not solve it at all: a local wheel must still be inside the build
  context to be installed, which is the original problem with a build step
  attached.

WHAT THIS SCRIPT WRITES

For each own-context worker whose Python actually references the core:

  * `docker-compose.production.yml` — an `additional_contexts:` block naming
    `sharedcore` and/or `observability` (only what that worker uses).
  * `workers/<name>/Dockerfile` — the matching `COPY --from=…` lines plus
    `ENV PYTHONPATH=/app`, inserted immediately before the `USER` line so the
    copy still runs as root. The `--chown` target is read from that Dockerfile's
    own `USER` — the estate uses three different names (worker, appuser,
    tranc3), so a hardcoded one would leave files unreadable by the process.

`src/observability` is copied without an `src/__init__.py`: `src` resolves as a
PEP 420 namespace package, so the marker file is unnecessary and copying one
would misleadingly imply the rest of `src/` is present.

Run with `--check` in CI: it exits 1 if any worker's Dockerfile and its Compose
entry disagree, which is the one way this mechanism can fail at build time
(a `COPY --from=sharedcore` with no context supplying `sharedcore`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"

# Context name -> (repo-relative source, destination inside the image)
CONTEXTS = {
    "sharedcore": ("./Dimensional", "/app/Dimensional/"),
    "observability": ("./src/observability", "/app/src/observability/"),
}

_CONTEXT_NAMES = "|".join(re.escape(n) for n in CONTEXTS)

BEGIN = "# --- Shared Functional Services Core (SFSC) — named build contexts ---"
END = "# --- end SFSC ---"


def own_context_workers() -> list[str]:
    """List services that build from their own directory rather than the repo root.

    Read from Compose rather than from `workers/` on disk: a directory with no
    Compose service is not deployed, and giving it the core would be busywork on
    something nothing runs.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"context:\s*\./workers/([a-z0-9\-]+)", text)))


def needed_contexts(worker: str) -> list[str]:
    """Decide which contexts a worker needs, from what its Python actually imports.

    Deliberately driven by the source rather than by a hand-kept list: a worker
    that stops importing the core should stop being given it, and the next
    worker to add an import should be picked up without anyone remembering to
    edit this file.

    A worker that already vendors a tree is left alone, because a named context
    would overwrite it rather than merge with it. hive-service is the concrete
    case: it vendors `Dimensional/` with `__init__.py` deliberately emptied,
    because the canonical `Dimensional/__init__.py` eagerly imports the whole
    package (bus, security, dimensionals, gas, genetics, infinity, liquid) and
    hive-service installs none of those dependencies. Copying the canonical tree
    over the trimmed one would restore that eager import and break the worker at
    startup — turning a delivery mechanism into an outage.
    """
    wd = ROOT / "workers" / worker
    if not wd.is_dir():
        return []
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in wd.rglob("*.py"))
    needed = []
    if re.search(r"\b(from|import)\s+Dimensional\b", text) and not (wd / "Dimensional").is_dir():
        needed.append("sharedcore")
    if "src.observability" in text and not (wd / "src" / "observability").is_dir():
        needed.append("observability")
    return needed


def render_dockerfile_block(names: list[str], user: str) -> str:
    """Render the COPY block for one worker, naming only the contexts it uses.

    A worker that never imports `Dimensional` does not get it copied in: an
    unused context still has to be supplied at build time, so granting one
    creates a build dependency that buys nothing.
    """
    flags = " ".join(
        f"--build-context {n}={_relative_from_worker(CONTEXTS[n][0])}" for n in names
    )
    lines = [
        BEGIN,
        "# Not copied into this directory — there is one copy of the core, at the",
        "# repo root. Supplied by docker-compose.production.yml, or for a direct",
        f"#   docker build {flags} .",
        "# See scripts/apply_shared_core_contexts.py for why this is not a base image.",
    ]
    for n in names:
        src_desc, dest = CONTEXTS[n]
        lines.append(f"COPY --from={n} --chown={user}:{user} . {dest}")
    lines.append("ENV PYTHONPATH=/app")
    lines.append(END)
    return "\n".join(lines)


def _relative_from_worker(repo_relative: str) -> str:
    """Convert a repo-root-relative path to one usable from inside `workers/<name>`.

    The Compose value and the `docker build` value differ: Compose resolves
    against the project directory, a direct build against the shell's cwd. The
    comment in the Dockerfile documents the direct-build form, so it has to be
    written from the worker's own directory or copy-pasting it would fail.
    """
    return "../../" + repo_relative.removeprefix("./")


def patch_dockerfile(worker: str, names: list[str]) -> tuple[bool, str]:
    """Insert or refresh the SFSC block in one worker's Dockerfile.

    Returns (changed, message). Idempotent: an existing block between the BEGIN
    and END markers is replaced wholesale, so re-running after a worker's
    imports change rewrites rather than duplicates.
    """
    df = ROOT / "workers" / worker / "Dockerfile"
    if not df.is_file():
        return False, f"{worker}: no Dockerfile"
    text = df.read_text(encoding="utf-8")

    user_match = re.search(r"^USER (\S+)\s*$", text, re.M)
    if not user_match:
        return False, f"{worker}: no USER line to anchor the block to"
    user = user_match.group(1)

    block = render_dockerfile_block(names, user)
    existing = re.search(
        rf"^{re.escape(BEGIN)}.*?^{re.escape(END)}\n", text, re.S | re.M
    )
    if existing:
        if existing.group(0).rstrip("\n") == block:
            return False, f"{worker}: already current"
        new_text = text[: existing.start()] + block + "\n" + text[existing.end() :]
    else:
        # Insert above any comment lines attached to USER, not between them and
        # the directive they describe: several Dockerfiles carry a
        # "# Security: drop to non-root user" line whose meaning depends on
        # sitting immediately above USER.
        insert_at = user_match.start()
        preceding = text[:insert_at].splitlines(keepends=True)
        while preceding and preceding[-1].lstrip().startswith("#"):
            insert_at -= len(preceding.pop())
        new_text = text[:insert_at] + block + "\n\n" + text[insert_at:]

    df.write_text(new_text, encoding="utf-8")
    return True, f"{worker}: Dockerfile updated ({', '.join(names)})"


def patch_compose(text: str, worker: str, names: list[str]) -> tuple[str, bool]:
    """Add `additional_contexts:` to one service's build block.

    Handles both spellings in use — the inline flow mapping
    `build: { context: …, dockerfile: … }` and the expanded block form — and
    normalises the inline one to block form, because a flow mapping cannot carry
    a nested mapping readably.

    Edits the file as text rather than round-tripping through a YAML dumper: the
    compose file is 4000+ lines of hand-maintained anchors, comments and merge
    keys, and re-emitting it would rewrite all of them to make a five-line
    change.
    """
    entries = "\n".join(f"        {n}: {CONTEXTS[n][0]}" for n in names)
    block_add = f"      additional_contexts:\n{entries}\n"

    inline = re.search(
        rf"^([ \t]*)build: \{{ context: \./workers/{re.escape(worker)}, "
        rf"dockerfile: (\S+) \}}[ \t]*\n",
        text,
        re.M,
    )
    if inline:
        indent = inline.group(1)
        replacement = (
            f"{indent}build:\n"
            f"{indent}  context: ./workers/{worker}\n"
            f"{indent}  dockerfile: {inline.group(2)}\n"
            f"{block_add}"
        )
        return text[: inline.start()] + replacement + text[inline.end() :], True

    # `dockerfile:` is optional — ffmpeg-worker omits it and relies on the
    # default filename. Requiring it silently skipped that service, and the
    # cross-check in `verify` is what surfaced the miss.
    #
    # The trailing group must match ONLY existing additional_contexts entries.
    # An earlier `[ \t]+\S+: \S+\n` also matched the `container_name:` line that
    # follows the build block, so a second run swallowed it into the group and
    # replaced it with the rebuilt contexts — silently deleting container_name
    # from 37 services. Restricting the entry names to the known contexts and
    # their values to `./`-rooted paths makes the group unable to run past the
    # block it belongs to.
    expanded = re.search(
        rf"^([ \t]*)context: \./workers/{re.escape(worker)}[ \t]*\n"
        rf"([ \t]*dockerfile: \S+[ \t]*\n)?"
        rf"((?:[ \t]*additional_contexts:\n(?:[ \t]+(?:{_CONTEXT_NAMES}): \./\S+\n)+)?)",
        text,
        re.M,
    )
    if not expanded:
        return text, False
    if expanded.group(3) == block_add:
        return text, False
    rebuilt = expanded.group(0)[: len(expanded.group(0)) - len(expanded.group(3))] + block_add
    return text[: expanded.start()] + rebuilt + text[expanded.end() :], True


def verify(workers: list[str]) -> list[str]:
    """Cross-check every Dockerfile's COPY names against its Compose contexts.

    This is the failure this mechanism can actually produce: a Dockerfile that
    reads `--from=sharedcore` while its Compose entry supplies no such context
    builds fine locally (where someone passed `--build-context` by hand) and
    fails in the deployment that matters. Checking both sides against each other
    catches it in CI instead.
    """
    compose_text = COMPOSE.read_text(encoding="utf-8")
    errors: list[str] = []
    for w in workers:
        df = ROOT / "workers" / w / "Dockerfile"
        if not df.is_file():
            continue
        declared = set(re.findall(r"^COPY --from=(\w+) ", df.read_text(encoding="utf-8"), re.M))
        declared &= set(CONTEXTS)
        service = re.search(
            rf"context: \./workers/{re.escape(w)}[ \t]*\n"
            rf"(?:[ \t]*dockerfile: \S+[ \t]*\n)?"
            rf"((?:[ \t]*additional_contexts:\n(?:[ \t]+(?:{_CONTEXT_NAMES}): \./\S+\n)+)?)",
            compose_text,
            re.M,
        )
        supplied = set(re.findall(r"(\w+): \./", service.group(1))) if service else set()
        missing = declared - supplied
        if missing:
            errors.append(
                f"{w}: Dockerfile copies from {sorted(missing)} but "
                f"docker-compose.production.yml supplies {sorted(supplied) or 'none'} — "
                f"this build fails with 'could not find context'"
            )
        unused = supplied - declared
        if unused:
            errors.append(
                f"{w}: compose supplies {sorted(unused)} that the Dockerfile never "
                f"copies from — remove it or the build carries a dependency it does not use"
            )
    return errors


def main() -> int:
    """Apply (or check) shared-core delivery across every own-context worker."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="verify Dockerfiles and Compose agree; write nothing, exit 1 on drift",
    )
    args = ap.parse_args()

    workers = own_context_workers()
    targets = {w: n for w in workers if (n := needed_contexts(w))}

    if args.check:
        errors = verify(workers)
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(
            f"shared-core contexts: {len(targets)} of {len(workers)} own-context "
            f"worker(s) need the core, {len(errors)} error(s)"
        )
        return 1 if errors else 0

    compose_text = COMPOSE.read_text(encoding="utf-8")
    changed_compose = 0
    for w, names in sorted(targets.items()):
        compose_text, did = patch_compose(compose_text, w, names)
        changed_compose += did
    COMPOSE.write_text(compose_text, encoding="utf-8")

    changed_df = 0
    for w, names in sorted(targets.items()):
        did, msg = patch_dockerfile(w, names)
        changed_df += did
        print(f"  {msg}")

    print(
        f"\n{len(targets)} worker(s) need the core; "
        f"{changed_df} Dockerfile(s) and {changed_compose} compose entr(ies) updated"
    )
    errors = verify(workers)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

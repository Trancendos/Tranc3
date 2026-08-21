"""Guard the vendored worker copies against silent drift from their source modules.

`workers/hive-service/` and `workers/dimensional-nexus-service/` each carry a
partial copy of the repo-root `Dimensional/` package (and, for hive, a slice of
`src/`). That vendoring is deliberate: `docker-compose.production.yml` gives each
worker a build context of its own directory, so `COPY` cannot reach repo root.

Both Dockerfiles instruct "Keep in sync with the source modules under ..." — but
nothing enforced it, and both copies had in fact drifted. The drift was the good
kind (the workers carried a CORS fix the root modules were still missing), which
is exactly why it went unnoticed: everything passed, and the *deployed* code was
the correct one while the canonical source stayed vulnerable. A future drift in
the other direction — a fix landing in root and never reaching the container —
would be just as silent and considerably worse.

This test turns that comment into a check. When it fails, copy the file rather
than editing one side: the two must be byte-identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Worker directory -> the package roots it vendors, relative to both the worker
# directory and the repo root. Every *.py beneath these, in either location, is
# compared.
VENDORED_TREES: dict[str, tuple[str, ...]] = {
    "workers/hive-service": ("Dimensional", "src"),
    "workers/dimensional-nexus-service": ("Dimensional",),
}


# Package inits deliberately emptied in the vendored copies. The root versions
# eagerly import the whole tree (`Dimensional/__init__.py` pulls in EventBus,
# models, registry, security, ...), none of which the partial copy contains, so
# emptying them is what makes it importable at all.
#
# Declared explicitly rather than inferred from "the vendored file is empty".
# That inference would also swallow a *real* init that got accidentally emptied
# — blanking `Dimensional/hive/__init__.py` breaks `from Dimensional.hive import
# Hive` in the container, and the check would have called it a shim and stayed
# green. Anything not named here is compared, including files that happen to be
# empty on both sides (`src/errors/__init__.py`), which simply compare equal.
NAMESPACE_SHIMS = frozenset(
    {
        "Dimensional/__init__.py",
        "Dimensional/infinity/__init__.py",
        "src/__init__.py",
    }
)


def _vendored_files() -> list[tuple[str, Path, Path]]:
    """Every vendored .py paired with its repo-root counterpart.

    Missing trees are a hard error, not a skip. Silently dropping a renamed tree
    would quietly narrow coverage while the suite stayed green — the same class
    of failure this module exists to catch. It also anchors ``REPO_ROOT``: if the
    tests directory ever moves, the paths stop resolving and this raises instead
    of discovering nothing.
    """
    pairs: list[tuple[str, Path, Path]] = []
    for worker, trees in VENDORED_TREES.items():
        worker_dir = REPO_ROOT / worker
        assert worker_dir.is_dir(), (
            f"VENDORED_TREES lists '{worker}', which does not exist at {worker_dir}. "
            "Update the mapping if the worker moved, or remove the entry if the "
            "vendoring is gone — do not let it silently drop out of coverage."
        )
        for tree in trees:
            base = worker_dir / tree
            assert base.is_dir(), (
                f"'{worker}' is declared as vendoring '{tree}', but {base} does not "
                "exist. Update VENDORED_TREES rather than leaving this package root "
                "unchecked."
            )
            for copy in sorted(base.rglob("*.py")):
                rel = copy.relative_to(worker_dir).as_posix()
                if rel in NAMESPACE_SHIMS:
                    continue
                pairs.append((f"{worker}::{rel}", copy, REPO_ROOT / rel))
    return pairs


VENDORED = _vendored_files()


def test_vendored_file_list_is_not_empty():
    """A refactor that moves or deletes the vendored trees must not silently
    turn this whole module into a no-op that still reports green."""
    assert VENDORED, (
        "found no vendored .py files under "
        f"{list(VENDORED_TREES)} — if the vendoring was removed (e.g. the build "
        "context moved to repo root), delete this test with it rather than "
        "leaving it passing vacuously"
    )


# The files whose drift would be a security regression rather than an
# inconvenience: the two app factories that install CORSMiddleware, and the
# module they now resolve their allow-list from.
SECURITY_CRITICAL = {
    "workers/hive-service::Dimensional/cors.py",
    "workers/hive-service::Dimensional/hive/hive_core.py",
    "workers/dimensional-nexus-service::Dimensional/cors.py",
    "workers/dimensional-nexus-service::Dimensional/nexus/nexus_core.py",
}


def test_security_critical_copies_are_covered():
    """Anchor coverage to named files, not just "the list is non-empty".

    Discovery is `rglob`, so a deleted vendored module simply stops appearing in
    the parametrization and everything still passes — losing drift protection for
    precisely the file this guard exists to protect, with no failure anywhere.
    `test_vendored_file_list_is_not_empty` does not help: the other copies keep
    the list non-empty.
    """
    covered = {name for name, _, _ in VENDORED}
    missing = sorted(SECURITY_CRITICAL - covered)
    assert not missing, (
        f"these vendored files are no longer being drift-checked: {missing}. They "
        "install or configure CORS in a deployed worker, so an unnoticed "
        "divergence reopens a security hole. If the vendoring genuinely moved, "
        "update SECURITY_CRITICAL to match — do not let the entry just vanish."
    )


def test_every_declared_shim_is_actually_a_shim():
    """Keep NAMESPACE_SHIMS honest — a stale entry silently excludes a real file.

    Two ways an entry stops being legitimate, both of which quietly drop a file
    from the drift check if nobody notices:

    * the vendored copy grew real content, so it is no longer a stub and should
      be compared like anything else;
    * the root counterpart became empty, so there was nothing to stub out and the
      exclusion buys nothing.
    """
    problems: list[str] = []
    for worker in VENDORED_TREES:
        worker_dir = REPO_ROOT / worker
        for rel in sorted(NAMESPACE_SHIMS):
            copy = worker_dir / rel
            if not copy.exists():
                continue  # this worker does not vendor that package
            if copy.stat().st_size != 0:
                problems.append(
                    f"{worker}::{rel} is declared a namespace shim but is not empty "
                    "— remove it from NAMESPACE_SHIMS so it gets compared"
                )
            source = REPO_ROOT / rel
            if source.exists() and source.stat().st_size == 0:
                problems.append(
                    f"{worker}::{rel} is declared a namespace shim, but {rel} is empty "
                    "at root too — there is nothing to stub out, so remove it from "
                    "NAMESPACE_SHIMS and let the byte comparison cover it"
                )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name,copy,source", VENDORED, ids=[p[0] for p in VENDORED])
def test_vendored_copy_matches_source(name: str, copy: Path, source: Path):
    assert source.exists(), (
        f"{name} is vendored but has no counterpart at {source.relative_to(REPO_ROOT)} — "
        "either the source module moved (update the copy and the Dockerfile comment) "
        "or the copy is orphaned and should be deleted"
    )
    assert copy.read_bytes() == source.read_bytes(), (
        f"{name} has drifted from {source.relative_to(REPO_ROOT)}. The worker build "
        "context cannot reach repo root, so this file is a deliberate copy that must "
        "stay byte-identical. Copy the correct version over the other — do not "
        "hand-merge, and check which side is actually correct before choosing: the "
        "deployed container runs the worker copy, but the root module is what the "
        "test suite and shared_core import."
    )

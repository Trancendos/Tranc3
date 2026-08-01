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


def _is_namespace_shim(path: Path) -> bool:
    """An empty vendored ``__init__.py`` is a deliberate namespace shim, not drift.

    The root package inits eagerly import the whole tree (``Dimensional/__init__.py``
    pulls in EventBus, models, registry, security, ...), none of which the vendored
    subset contains. Emptying them is what makes a partial copy importable at all.

    Emptiness is the test rather than a hardcoded path list, so a *non*-empty
    ``__init__.py`` — ``Dimensional/hive/__init__.py`` and
    ``Dimensional/nexus/__init__.py``, which export real API — is still compared.
    """
    return path.name == "__init__.py" and path.stat().st_size == 0


def _vendored_files() -> list[tuple[str, Path, Path]]:
    """Every vendored .py paired with its repo-root counterpart."""
    pairs: list[tuple[str, Path, Path]] = []
    for worker, trees in VENDORED_TREES.items():
        worker_dir = REPO_ROOT / worker
        for tree in trees:
            base = worker_dir / tree
            if not base.is_dir():
                continue
            for copy in sorted(base.rglob("*.py")):
                if _is_namespace_shim(copy):
                    continue
                rel = copy.relative_to(worker_dir).as_posix()
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

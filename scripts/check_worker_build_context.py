#!/usr/bin/env python3
"""Build-context import validation — catches workers that cannot start.

THE FAILURE THIS CATCHES

74 of the services in `docker-compose.production.yml` build from their own
directory (`context: ./workers/<name>`), not from the repo root. Nothing outside
that directory is in the image. `src/`, `Dimensional/` and `shared_core/` are
therefore absent, and any `from src.… import …` executed at import time or during
FastAPI's `lifespan` raises ImportError *inside the container* while passing
every local test — because locally the repo root is on `sys.path` and the module
resolves fine.

When that import sits inside `lifespan`, the ImportError escapes the startup
context manager and the worker never comes up. Seven workers were in exactly
that state (infinity-void, mlflow-service, queue-service, search-service,
triposr-worker, turings-hub-service, vault-service), all of them importing
`src.observability.worker_setup` for OpenTelemetry: optional telemetry taking
down the service it was meant to observe.

WHAT COUNTS AS OK

Twenty-seven other workers import the same module correctly, and their pattern
is the estate's convention:

    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.<name>")
    except Exception:
        pass  # telemetry is optional — never block startup

So a cross-boundary import is fine when *either*:

  * it is guarded by a `try` whose handlers catch ImportError / Exception, so
    the worker degrades instead of dying; or
  * the package is vendored into the build context (e.g.
    `workers/hive-service/Dimensional/`), so it genuinely resolves in the image.

Anything else is an unguarded dependency on code that will not be there.

WHAT THIS DELIBERATELY DOES NOT FLAG

Test files. They run in CI from the repo root, where the imports resolve, and
they are not shipped in the image.

Root-context services (`context: .`) get the whole repo, so `src/` is present
and the imports are real. They are skipped entirely.

VENDOR DRIFT

Two workers (hive-service, dimensional-nexus-service) take the other route and
vendor the modules they need into their own build context, with the Dockerfile
copying them in explicitly. Their Dockerfiles carry the instruction "keep in
sync with the source modules" — a promise nothing was checking. This script
checks it: every vendored file must be byte-identical to its canonical source.

The one exception is a vendored `__init__.py` that has been deliberately emptied.
A package `__init__` normally imports the whole package; a worker that vendors
only `Dimensional.hive` cannot execute that, so blanking the file is the correct
move rather than drift. An empty vendored `__init__.py` therefore passes, and a
non-empty one that differs from canonical does not.

Exit 0 when every cross-boundary import in an own-context worker is guarded or
vendored, and every vendored file matches its source, 1 otherwise.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"

# Packages that live at the repo root and are therefore outside an own-context
# build. `Dimensional` is the platform's Shared Functional Services Core (SFSC);
# `shared_core` is its backward-compatibility shim layer.
ROOT_PACKAGES = {"src", "Dimensional", "shared_core"}


def own_context_services() -> dict[str, Path]:
    """Map service name → build context dir, for services not built from root."""
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    out: dict[str, Path] = {}
    for name, cfg in (data.get("services") or {}).items():
        if not isinstance(cfg, dict):
            continue
        build = cfg.get("build")
        ctx = build.get("context") if isinstance(build, dict) else build
        if not isinstance(ctx, str):
            continue  # image-only service, nothing to build
        ctx = ctx.rstrip("/")
        if ctx in (".", ""):
            continue  # whole repo is in the image
        path = ROOT / ctx.lstrip("./")
        if path.is_dir():
            out[name] = path
    return out


def guarded_line_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Line spans of `try` bodies whose handlers would swallow an ImportError."""
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches = False
        for handler in node.handlers:
            if handler.type is None:  # bare except
                catches = True
                break
            names = {n.id for n in ast.walk(handler.type) if isinstance(n, ast.Name)} | {
                n.attr for n in ast.walk(handler.type) if isinstance(n, ast.Attribute)
            }
            if names & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
                catches = True
                break
        if catches:
            for stmt in node.body:
                spans.append((stmt.lineno, getattr(stmt, "end_lineno", stmt.lineno)))
    return spans


def cross_boundary_imports(path: Path) -> list[tuple[int, str, bool]]:
    """Return (lineno, module, guarded) for each import of a root package."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, ValueError):
        return []
    spans = guarded_line_ranges(tree)

    def is_guarded(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in spans)

    found: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] in ROOT_PACKAGES:
                modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules += [a.name for a in node.names if a.name.split(".")[0] in ROOT_PACKAGES]
        for module in modules:
            found.append((node.lineno, module, is_guarded(node.lineno)))
    return found


def is_test_file(path: Path, context: Path) -> bool:
    rel = path.relative_to(context)
    return "tests" in rel.parts or rel.name.startswith("test_") or rel.name.endswith("_test.py")


def check_vendored(context: Path, errors: list[str], info: list[str]) -> int:
    """Compare every vendored root-package file against its canonical source."""
    checked = 0
    for pkg in sorted(ROOT_PACKAGES):
        vendor_root = context / pkg
        if not vendor_root.is_dir():
            continue
        for copy in sorted(vendor_root.rglob("*.py")):
            rel = copy.relative_to(context)
            canonical = ROOT / rel
            checked += 1
            here = copy.read_text(encoding="utf-8", errors="ignore")
            if copy.name == "__init__.py" and not here.strip():
                info.append(
                    f"{copy.relative_to(ROOT)}: intentionally emptied — the worker vendors "
                    f"only part of `{pkg}`, so the package's real __init__ cannot run"
                )
                continue
            if not canonical.exists():
                errors.append(
                    f"{copy.relative_to(ROOT)}: vendored copy has no canonical source at "
                    f"{rel} — it can never be kept in sync, and no one owns it"
                )
                continue
            if canonical.read_text(encoding="utf-8", errors="ignore") != here:
                errors.append(
                    f"{copy.relative_to(ROOT)}: has drifted from {rel}. The Dockerfile "
                    f"promises these stay in sync; re-copy the canonical file or explain "
                    f"the divergence in the worker's Dockerfile."
                )
    return checked


def main() -> int:
    services = own_context_services()
    errors: list[str] = []
    info: list[str] = []
    scanned = 0
    vendored_checked = 0

    for name in sorted(services):
        context = services[name]
        vendored_checked += check_vendored(context, errors, info)
        for py in sorted(context.rglob("*.py")):
            # A vendored copy is the thing being depended on, not a dependant.
            if any(part in ROOT_PACKAGES for part in py.relative_to(context).parts[:-1]):
                continue
            if is_test_file(py, context):
                continue
            for lineno, module, guarded in cross_boundary_imports(py):
                scanned += 1
                rel = py.relative_to(ROOT)
                top = module.split(".")[0]
                vendored = (context / top).is_dir()
                if vendored:
                    info.append(
                        f"{rel}:{lineno}: imports `{module}` — `{top}/` is vendored into "
                        f"`{context.relative_to(ROOT)}`, so it resolves in the image"
                    )
                elif guarded:
                    info.append(
                        f"{rel}:{lineno}: imports `{module}` — outside the build context "
                        f"but guarded, so `{name}` degrades instead of failing to start"
                    )
                else:
                    errors.append(
                        f"{rel}:{lineno}: unguarded `import {module}`, but `{name}` builds "
                        f"from `{context.relative_to(ROOT)}` so `{top}/` is not in the image. "
                        f"This raises ImportError in the container. Wrap it in "
                        f"try/except Exception, or vendor `{top}/` into the build context."
                    )

    for line in info:
        print(f"[INFO]  {line}")
    for line in errors:
        print(f"[ERROR] {line}", file=sys.stderr)

    print(
        f"\nbuild-context check: {scanned} cross-boundary import(s) and "
        f"{vendored_checked} vendored file(s) across {len(services)} own-context "
        f"service(s), {len(info)} informational, {len(errors)} error(s)"
    )
    if errors:
        print("Build context check: FAILED", file=sys.stderr)
        return 1
    print("Build context check: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

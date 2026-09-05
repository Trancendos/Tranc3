#!/usr/bin/env python3
"""Keep The Lab's accepted languages and the platform registry in step.

`src/lab/languages.py` is the canonical registry: it holds each language's
toolchain and the verification tier that toolchain unlocks. `workers/the-lab`
cannot import it — its Docker build context is main.py plus the shared core —
so the worker mirrors the ids and the aliases.

A mirror nothing checks is a fork waiting to happen, and the failure would be
quiet in the worst direction: a language added to the registry, reported in
the capability matrix, and refused by the running service with a 400.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.lab.languages import LANGUAGES  # noqa: E402

WORKER = REPO / "workers" / "the-lab" / "main.py"


def _literal(name: str, tree: ast.Module):
    """Read a module-level literal assignment without importing the module.

    The worker raises at import when INTERNAL_SECRET is unset, which is
    correct for a worker and unhelpful for a static check.
    """
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit(f"check_lab_languages: {name} not found in {WORKER.relative_to(REPO)}")


def main(argv: list[str] | None = None) -> int:
    tree = ast.parse(WORKER.read_text(), filename=str(WORKER))
    accepted = set(_literal("ALLOWED_LANGUAGES", tree))
    aliases = dict(_literal("LANGUAGE_ALIASES", tree))

    registry_ids = {entry.id for entry in LANGUAGES}
    registry_aliases = {alias: entry.id for entry in LANGUAGES for alias in entry.aliases}

    problems: list[str] = []

    for missing in sorted(registry_ids - accepted):
        problems.append(
            f"{missing}: in the registry, refused by the worker — "
            f"the capability matrix would report it and the service would 400"
        )
    for extra in sorted(accepted - registry_ids):
        problems.append(
            f"{extra}: accepted by the worker, absent from the registry — "
            f"its toolchain and verification tier are undeclared"
        )

    for alias, target in sorted(registry_aliases.items()):
        if aliases.get(alias) != target:
            problems.append(
                f"alias {alias!r}: registry resolves it to {target!r}, "
                f"worker resolves it to {aliases.get(alias)!r}"
            )
    for alias, target in sorted(aliases.items()):
        if alias not in registry_aliases:
            problems.append(f"alias {alias!r}: accepted by the worker, absent from the registry")
        if target not in registry_ids:
            problems.append(f"alias {alias!r}: resolves to {target!r}, which is not a language")

    if problems:
        print("Lab language check: FAILED")
        for problem in problems:
            print(f"  [ERROR] {problem}")
        print()
        print(
            "src/lab/languages.py is canonical. Update ALLOWED_LANGUAGES and "
            "LANGUAGE_ALIASES in workers/the-lab/main.py to match it."
        )
        return 1

    print(
        f"Lab language check: PASSED — {len(accepted)} languages and "
        f"{len(aliases)} aliases match the registry"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

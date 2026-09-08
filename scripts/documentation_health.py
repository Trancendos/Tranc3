#!/usr/bin/env python3
"""Validate living-document contracts without generating undocumented claims.

The repository and GitHub Wiki are two publication surfaces, not two competing
sources of truth. This tool keeps the boundary explicit: code-adjacent sources
are mapped to one reviewed canonical document, while ``wiki-content/`` remains
the version-controlled source for the GitHub Wiki mirror.

It intentionally does not call a language model or rewrite prose. A changed
source requires a human-reviewed canonical document update; deterministic
navigation or registry failures remain hard failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config" / "docs" / "living_documents.yaml"
DEFAULT_CATALOG = ROOT / "docs" / "DOCUMENTATION_CATALOG.md"
DEFAULT_SIDEBAR = ROOT / "wiki-content" / "_Sidebar.md"
DOC_DIRECTORIES = (ROOT / "docs", ROOT / "wiki-content")
VALID_KINDS = frozenset({"tutorial", "how-to", "reference", "explanation"})


@dataclass(frozen=True)
class DocumentContract:
    identifier: str
    title: str
    canonical: str
    kind: str
    owner: str
    source_paths: tuple[str, ...]


def _repository_path(path: str, root: Path = ROOT) -> Path:
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"path escapes repository root: {path}") from error
    return candidate


def load_contracts(path: Path = DEFAULT_REGISTRY) -> list[DocumentContract]:
    with path.open(encoding="utf-8") as registry_file:
        data = yaml.safe_load(registry_file)
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        raise ValueError("registry must define a documents list")

    contracts: list[DocumentContract] = []
    for index, item in enumerate(data["documents"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"documents[{index}] must be a mapping")
        fields = ("id", "title", "canonical", "kind", "owner", "source_paths")
        missing = [field for field in fields if field not in item]
        if missing:
            raise ValueError(f"documents[{index}] missing: {', '.join(missing)}")
        sources = item["source_paths"]
        if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
            raise ValueError(f"documents[{index}].source_paths must be a list of strings")
        contracts.append(
            DocumentContract(
                identifier=str(item["id"]),
                title=str(item["title"]),
                canonical=str(item["canonical"]),
                kind=str(item["kind"]),
                owner=str(item["owner"]),
                source_paths=tuple(sources),
            )
        )
    return contracts


def validate_contracts(contracts: Iterable[DocumentContract], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    identifiers: set[str] = set()
    canonicals: set[str] = set()
    for contract in contracts:
        if contract.identifier in identifiers:
            errors.append(f"duplicate document contract id: {contract.identifier}")
        identifiers.add(contract.identifier)
        if contract.canonical in canonicals:
            errors.append(f"multiple contracts claim canonical document: {contract.canonical}")
        canonicals.add(contract.canonical)
        if contract.kind not in VALID_KINDS:
            errors.append(
                f"{contract.identifier} uses invalid documentation kind {contract.kind!r}"
            )
        for path in (contract.canonical, *contract.source_paths):
            if not _repository_path(path, root).exists():
                errors.append(f"{contract.identifier} references missing path: {path}")
    return errors


def wiki_pages(sidebar: Path = DEFAULT_SIDEBAR) -> list[str]:
    return sorted(
        page.stem for page in sidebar.parent.glob("*.md") if not page.name.startswith("_")
    )


def sidebar_targets(sidebar: Path = DEFAULT_SIDEBAR) -> set[str]:
    text = sidebar.read_text(encoding="utf-8")
    targets: set[str] = set()
    for line in text.splitlines():
        if "](" not in line or not line.rstrip().endswith(")"):
            continue
        target = line.rsplit("](", maxsplit=1)[1].rstrip()
        targets.add(target[:-1].removesuffix(".md"))
    return targets


def unlisted_wiki_pages(sidebar: Path = DEFAULT_SIDEBAR) -> list[str]:
    targets = sidebar_targets(sidebar)
    return [page for page in wiki_pages(sidebar) if page not in targets]


def identical_documents(directories: Iterable[Path] = DOC_DIRECTORIES) -> list[list[str]]:
    content_hashes: dict[str, list[str]] = defaultdict(list)
    for directory in directories:
        for document in directory.rglob("*.md"):
            if document.name.startswith("_"):
                continue
            digest = hashlib.sha256(document.read_bytes()).hexdigest()
            content_hashes[digest].append(str(document.relative_to(ROOT)))
    return sorted(sorted(paths) for paths in content_hashes.values() if len(paths) > 1)


def changed_paths(base_ref: str, root: Path = ROOT) -> tuple[list[str], str | None]:
    merge_base = subprocess.run(
        ["git", "merge-base", base_ref, "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if merge_base.returncode != 0:
        detail = merge_base.stderr.strip() or f"git merge-base exited {merge_base.returncode}"
        return [], f"cannot resolve documentation comparison base {base_ref!r}: {detail}"
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{merge_base.stdout.strip()}...HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if diff.returncode != 0:
        detail = diff.stderr.strip() or f"git diff exited {diff.returncode}"
        return [], f"cannot inspect changed paths: {detail}"
    return [path for path in diff.stdout.splitlines() if path], None


def source_changes_missing_canonical_updates(
    contracts: Iterable[DocumentContract], changed: Iterable[str]
) -> list[str]:
    changed_paths_set = set(changed)
    errors: list[str] = []
    for contract in contracts:
        source_changed = any(
            changed_path == source or changed_path.startswith(f"{source.rstrip('/')}/")
            for source in contract.source_paths
            for changed_path in changed_paths_set
        )
        if source_changed and contract.canonical not in changed_paths_set:
            errors.append(
                f"{contract.identifier} source changed without reviewing canonical document "
                f"{contract.canonical}"
            )
    return errors


def render_catalog(contracts: Iterable[DocumentContract]) -> str:
    rows = [
        "# Documentation Catalog",
        "",
        "> Generated from `config/docs/living_documents.yaml` by "
        "`scripts/documentation_health.py --catalog`. Do not edit the table directly.",
        "",
        "## Use This Map",
        "",
        "- Start here to choose the canonical document for a platform concern.",
        "- Treat `wiki-content/` as the reviewed source for the GitHub Wiki; the live wiki is a one-way publication mirror.",
        "- Update a mapped canonical document in the same change as its source, or explicitly amend the registry after review.",
        "",
        "## Living Document Contracts",
        "",
        "| Topic | Canonical document | Kind | Owner | Change signals |",
        "|---|---|---|---|---|",
    ]
    for contract in contracts:
        sources = ", ".join(f"`{source}`" for source in contract.source_paths)
        rows.append(
            f"| {contract.title} | `{contract.canonical}` | {contract.kind} | "
            f"{contract.owner} | {sources} |"
        )
    rows.extend(
        [
            "",
            "## Documentation Model",
            "",
            "The catalog uses the four Diataxis forms: tutorials teach, how-to guides solve a task, reference documents state facts, and explanations provide context. The registry is a federated knowledge model: each domain owns its canonical page and change signals while common validation runs centrally. It is not a machine-learning system and does not autonomously alter operational or security guidance.",
            "",
            "Run `python scripts/documentation_health.py --check --base-ref origin/main --check-catalog` to validate navigation, registry paths, source-to-document review coupling, and the generated catalog.",
            "",
        ]
    )
    return "\n".join(rows)


def audit(
    registry_path: Path = DEFAULT_REGISTRY,
    sidebar: Path = DEFAULT_SIDEBAR,
    base_ref: str | None = None,
    check_catalog: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        contracts = load_contracts(registry_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return {"contracts": 0, "errors": [str(error)], "warnings": warnings}

    errors.extend(validate_contracts(contracts))
    unlisted = unlisted_wiki_pages(sidebar)
    if unlisted:
        errors.append(f"wiki pages absent from _Sidebar.md: {', '.join(unlisted)}")

    duplicates = identical_documents()
    for group in duplicates:
        warnings.append(
            f"identical documentation requires consolidation review: {', '.join(group)}"
        )

    changed: list[str] = []
    if base_ref:
        changed, comparison_error = changed_paths(base_ref)
        if comparison_error:
            errors.append(comparison_error)
        else:
            errors.extend(source_changes_missing_canonical_updates(contracts, changed))

    catalog_matches = True
    if check_catalog:
        expected = render_catalog(contracts)
        catalog_matches = (
            DEFAULT_CATALOG.exists() and DEFAULT_CATALOG.read_text(encoding="utf-8") == expected
        )
        if not catalog_matches:
            errors.append(
                "docs/DOCUMENTATION_CATALOG.md is stale; run "
                "python scripts/documentation_health.py --catalog"
            )

    return {
        "contracts": len(contracts),
        "changed_paths": len(changed),
        "identical_groups": duplicates,
        "catalog_matches": catalog_matches,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="return non-zero on documentation errors"
    )
    parser.add_argument("--base-ref", help="Git ref used to enforce source-to-document reviews")
    parser.add_argument(
        "--check-catalog", action="store_true", help="fail when the generated catalog is stale"
    )
    parser.add_argument(
        "--catalog", action="store_true", help="print the generated documentation catalog"
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args()

    if args.catalog:
        print(render_catalog(load_contracts()))
        return 0

    report = audit(base_ref=args.base_ref, check_catalog=args.check_catalog)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Documentation health: {report['contracts']} contract(s), "
            f"{len(report['errors'])} error(s), {len(report['warnings'])} advisory warning(s)"
        )
        for finding in report["errors"]:
            print(f"ERROR: {finding}")
        for finding in report["warnings"]:
            print(f"WARNING: {finding}")
    return 1 if args.check and report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

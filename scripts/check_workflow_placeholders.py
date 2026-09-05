#!/usr/bin/env python3
"""A workflow that still says `example` was never configured, and never ran.

Eight marketplace security workflows were added to this repository from
GitHub's starter templates and committed unedited. The result was not eight
scanners: it was five permanently red checks on every pull request, and the
slow lesson that a red X means nothing.

  cloudrail.yml       an action deleted from the marketplace, running
                      `terraform init` at a root holding no Terraform
  ethicalcheck.yml    `oas-url: http://netbanking.apisec.ai:8080/v2/api-docs`
                      — the vendor's demo host, pen-tested weekly on our
                      behalf, and `email: xxx@apisec.ai`
  endorlabs.yml       `namespace: "example"`, the template's own placeholder,
                      under a comment saying to replace it
  nowsecure-…-sbom    `group_id: {{ groupId }}`, which is not valid YAML at
                      all, building an Android app this repository does not
                      contain

Every one of those is mechanically detectable, and none of it needed a human
to notice. This is that check.

Two rules:

  1. Every workflow file must parse as YAML. `{{ groupId }}` is a mapping key
     that cannot be hashed, so GitHub rejected the whole file — a workflow
     that cannot be read is not a workflow, and nothing said so.

  2. No *value* may be an unreplaced placeholder. Values, not raw text:
     a comment that explains a placeholder — including the ones above — is
     documentation, and a check that could not tell the difference would
     punish writing the explanation down.

Standard library plus PyYAML, which CI already installs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRS = (".github/workflows", ".forgejo/workflows")

#: Values that are placeholders whatever the surrounding key. Compared
#: case-insensitively against the whole stripped value.
_PLACEHOLDER_VALUES = {
    "example",
    "changeme",
    "change-me",
    "placeholder",
    "todo",
    "tbd",
    "xxx",
    "your-token",
    "your_token",
    "your-namespace",
    "your_namespace",
    "my-project",
}

#: `{{ ... }}` tokens that are a real templating language rather than an
#: unfilled blank. `docker/metadata-action` takes Go templates in its `tags`
#: and `labels` — `.forgejo/workflows/registry-push.yml` uses
#: `enable={{is_default_branch}}`, correctly — and flagging those would make
#: this check cry wolf on working code the first time it ran. The list is the
#: action's documented set; a `{{ ... }}` opening with anything else is a
#: blank nobody filled in, which is what `{{ groupId }}` was.
_TEMPLATE_TOKENS = {
    "is_default_branch",
    "version",
    "major",
    "minor",
    "patch",
    "raw",
    "base_ref",
    "sha",
    "branch",
    "tag",
    "date",
    "commit_date",
    "tz",
}

_CURLY = re.compile(r"(?<!\$)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)?")


def _unfilled_curly(value: str) -> str | None:
    """The first `{{ … }}` in `value` that is not a known template token."""
    for match in _CURLY.finditer(value):
        token = match.group(1) or ""
        if token not in _TEMPLATE_TOKENS:
            return match.group(0)
    return None


#: Patterns that mark a value as a template's, not ours.
_PLACEHOLDER_PATTERNS = (
    # `<your-org>`, `<TOKEN>`: angle brackets around the whole value.
    (re.compile(r"^<[^>]+>$"), "an angle-bracket placeholder"),
    # The `xxx@vendor.example` address every starter template ships with.
    (re.compile(r"\bxxx@"), "a placeholder email address"),
)


def _values(node: object, path: str = "") -> list[tuple[str, str]]:
    """(location, value) for every string leaf in a parsed workflow."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.extend(_values(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_values(value, f"{path}[{index}]"))
    elif isinstance(node, str):
        found.append((path or "<root>", node))
    return found


def check() -> list[str]:
    failures: list[str] = []

    for directory in WORKFLOW_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.y*ml")):
            relative = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                failures.append(f"{relative}: could not be read ({exc})")
                continue

            try:
                document = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                detail = str(exc).replace("\n", " ")
                failures.append(
                    f"{relative}: is not valid YAML, so GitHub cannot run it at all — {detail}"
                )
                continue

            for location, value in _values(document):
                stripped = value.strip()
                if stripped.lower() in _PLACEHOLDER_VALUES:
                    failures.append(
                        f"{relative}: `{location}` is still {value!r}, the template's "
                        "placeholder. Replace it, drive it from a repository "
                        "variable, or delete the workflow."
                    )
                    continue
                unfilled = _unfilled_curly(stripped)
                if unfilled is not None:
                    failures.append(
                        f"{relative}: `{location}` contains an unreplaced "
                        f"`{{{{ … }}}}` template placeholder ({unfilled.strip()!r}). "
                        "GitHub does not expand these, and as a mapping key it makes "
                        "the whole file unparseable."
                    )
                    continue
                for pattern, description in _PLACEHOLDER_PATTERNS:
                    if pattern.search(stripped):
                        failures.append(
                            f"{relative}: `{location}` contains {description} "
                            f"({value.strip()[:60]!r})."
                        )
                        break
    return failures


def main() -> int:
    failures = check()
    if failures:
        print(
            "[ERROR] A workflow is unreadable or still carries a template placeholder.\n"
            "        Such a workflow does not scan anything; it only reports red, and a\n"
            "        check that is always red is one nobody reads.\n"
        )
        for failure in failures:
            print(f"  {failure}")
        return 1
    counted = sum(
        len(list((ROOT / d).glob("*.y*ml"))) for d in WORKFLOW_DIRS if (ROOT / d).is_dir()
    )
    print(
        f"Workflow placeholders: PASSED — {counted} workflow(s) parse, and none carries "
        "an unreplaced template value"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

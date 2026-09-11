#!/usr/bin/env python3
"""CLAUDE.md's list of pre-commit hooks must match the hooks that actually run.

WHY THIS EXISTS
---------------
CLAUDE.md described the pre-commit gate as running **black** and **isort**.
Neither is configured. The repository formats with `ruff-format`, which honours
`[tool.ruff] line-length = 100`; black's default is 88. Anyone -- human or
agent -- who read that section, ran `black`, and committed would have every
file reformatted back by pre-commit.ci on the next push, forever, with no
error message anywhere saying why. That happened in this session, twice, before
anyone read the config instead of the documentation.

The same section omitted three hooks that DO run, including two local ones
(`security-scanner`, `security-autofix`) that modify files. A contributor
reading only the documentation would not know those existed.

Neither direction is a small error. Documentation that names a tool the estate
does not run sends people to the wrong tool; documentation that omits a tool
that rewrites their files makes the rewrite look like magic.

WHAT IT ENFORCES
----------------
Every hook id in `.pre-commit-config.yaml` appears somewhere in CLAUDE.md's
pre-commit section, and every tool that section names as a hook exists in the
config. Trivial file hygiene hooks are grouped rather than listed one by one --
the section would become a transcript otherwise -- so the group is declared
here, in code, with the reason.

    python scripts/check_precommit_documented.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".pre-commit-config.yaml"
DOC = ROOT / "CLAUDE.md"
SECTION = "### Pre-commit Hooks"

# The eleven pre-commit-hooks basics -- trailing whitespace, end-of-file, the
# check-* parsers, detect-private-key, large files, no-commit-to-branch,
# check-ast, debug-statements. Listing each would turn a guidance document into
# a transcript of a config file, so they are covered by one line naming the
# repository they come from. That is a decision, and it lives here rather than
# being an unexplained absence.
GROUPED_PREFIXES = (
    "check-",
    "trailing-",
    "end-of-file",
    "detect-private-key",
    "no-commit-to-branch",
    "debug-statements",
)
GROUPED_MARKER = "pre-commit-hooks"


def configured_hooks() -> list[str]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return [
        hook["id"]
        for repo in data.get("repos", [])
        for hook in repo.get("hooks", [])
        if hook.get("id")
    ]


def documented_section() -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.find(SECTION)
    if start < 0:
        return ""
    # Up to the next heading of the same or higher level.
    rest = text[start + len(SECTION) :]
    end = re.search(r"\n#{1,3} ", rest)
    return rest[: end.start()] if end else rest


def documented_tools(section: str) -> set[str]:
    r"""Tool names the section presents as hooks: every bolded name in a list item.

    Every bolded name in the item's LEADING run, not just the first, and not
    every bold on the line. Two failures bracket the right rule:

    * `^- \*\*([^*]+)\*\*` stopped at the first bold, so

              - **security-scanner** / **security-autofix** -- local; ...

      registered `security-scanner` and dropped `security-autofix`. Deleting
      that second hook from the config then left this check green -- the exact
      failure this file exists to prevent, in the file that prevents it.
      Reported by cubic on PR #1150.

    * Taking every bold on the line instead over-collects, because bold is also
      used for emphasis mid-sentence:

              - **ruff-format** -- Code formatting. **This is the formatter,
                not black.**

      That second run is a warning to the reader, not a hook id, and treating
      it as one makes the check demand a hook called "this is the formatter,
      not black." -- which is what happened when the naive fix was tried.

    So: consume bold runs from the start of the item, allowing only `/` and `,`
    between them, and stop at the first ordinary prose. A name is a hook id
    because of where it sits in the sentence, not because it is bold.
    """
    names: set[str] = set()
    for line in section.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("- **"):
            continue
        rest = stripped[2:].lstrip()
        while True:
            match = re.match(r"\*\*([^*]+)\*\*", rest)
            if not match:
                break
            names.add(match.group(1).strip().lower())
            rest = rest[match.end() :]
            separator = re.match(r"\s*[/,]\s*", rest)
            if not separator:
                break
            rest = rest[separator.end() :]
    return names


def main() -> int:
    section = documented_section()
    if not section.strip():
        print(f"{DOC.name} has no '{SECTION}' section to check against.", file=sys.stderr)
        return 2

    hooks = configured_hooks()
    named = documented_tools(section)
    lowered = section.lower()
    grouped_claimed = GROUPED_MARKER in lowered
    grouped_configured = [h for h in hooks if h.startswith(GROUPED_PREFIXES)]

    # Matched against the NAMED list, not against the section's prose.
    #
    # The original test was `hook.lower() not in lowered` -- a substring search
    # over the whole section. cubic reported it as a substring bug and proposed
    # token boundaries, which is better but still wrong in the same direction:
    # a token search over prose passes any hook id that happens to be an
    # ordinary English word. Proving that took planting a hook called
    # `security`, which sailed through a boundary-matched search because the
    # section opens "zero-cost security gate".
    #
    # Matching against the bold list instead removes the whole class: a hook is
    # documented when the section LISTS it, which is what the sentence
    # "documented" was always supposed to mean. The looser form only existed
    # because nobody checked whether the strict one would pass -- it does, on
    # the nose: 11 non-grouped hooks, 11 names, no difference either way.
    undocumented = []
    for hook in grouped_configured:
        if not grouped_claimed:
            undocumented.append(f"{hook} (and its pre-commit-hooks siblings)")
    for hook in hooks:
        if hook.startswith(GROUPED_PREFIXES):
            continue
        if hook.lower() not in named:
            undocumented.append(hook)

    configured = {h.lower() for h in hooks}
    phantom = sorted(name for name in named if name not in configured)

    # The group is a claim like any other, so it can go stale like any other.
    # `grouped_claimed` was only ever read to EXCUSE configured hooks; nothing
    # checked the reverse. Drop every pre-commit-hooks entry from the config and
    # the documentation kept describing eleven hygiene hooks that no longer ran,
    # with this check green -- an unfalsifiable sentence, which is the one thing
    # a documentation gate must not permit. Reported by cubic on PR #1150.
    if grouped_claimed and not grouped_configured:
        phantom.append(f"the '{GROUPED_MARKER}' group (documented, but no such hook is configured)")
        phantom.sort()

    print(f"pre-commit hooks configured: {len(hooks)}")
    print(f"tools named in {DOC.name}: {len(named)}")

    if not undocumented and not phantom:
        print("\nThe documentation and the configuration agree.")
        return 0

    if undocumented:
        print(
            "\nRUNS BUT UNDOCUMENTED — a contributor reading CLAUDE.md would not "
            "know these fire on their commit:",
            file=sys.stderr,
        )
        for hook in sorted(set(undocumented)):
            print(f"  - {hook}", file=sys.stderr)
    if phantom:
        print(
            "\nDOCUMENTED BUT NOT CONFIGURED — this sends people to a tool the "
            "estate does not run, and its output will be undone:",
            file=sys.stderr,
        )
        for name in phantom:
            print(f"  - {name}", file=sys.stderr)
    print(
        f"\nUpdate the '{SECTION}' section of {DOC.name} to match "
        f"{CONFIG.name}, or change the config.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Every `${VAR:?...}` in the production compose file must be produced by the generator.

Compose refuses to interpolate `docker-compose.production.yml` at all if a single
`${VAR:?required}` is unset, so a generated `.env.production` that omits one makes
`docker compose up` fail before any container starts. 47 of 53 were missing at one
point and nothing caught it: `citadel_compose_validate.py` parses the YAML as text and
never interpolates, and the deploy script's own `docker compose` calls only fail on the
Citadel host, which has not been stood up yet.

This closes that loop from a plain checkout — no docker, no secrets, no host required.

Exit status: 0 when every required variable is covered, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"
GENERATOR = ROOT / "scripts" / "generate_production_env.sh"

# ${VAR:?anything} — the `:?` form is the one compose treats as mandatory.
REQUIRED_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):\?")

# Assignment inside the generator's heredoc body: `VAR=${VAR}` or `VAR=literal`.
EMITTED_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=", re.MULTILINE)

# The heredoc the generator redirects into $OUT — i.e. the literal body of
# .env.production. Only assignments in here actually reach the file.
HEREDOC_RE = re.compile(r'cat > "\$OUT" <<EOF\n(.*?)\nEOF', re.DOTALL)


def required_variables() -> set[str]:
    return set(REQUIRED_RE.findall(COMPOSE.read_text(encoding="utf-8")))


def emitted_variables() -> set[str]:
    """Variables the generator actually writes into .env.production.

    Scoped to the heredoc body rather than the whole script. The generator assigns
    each secret twice — once as a shell variable, then again inside the heredoc — and
    matching the whole file would count a variable that was generated in shell scope
    but never interpolated into the output. That is precisely the bug this check
    exists to catch, so it must not be able to pass on one.
    """
    text = GENERATOR.read_text(encoding="utf-8")
    match = HEREDOC_RE.search(text)
    if not match:
        raise ValueError(
            f'Could not locate the `cat > "$OUT" <<EOF` heredoc in '
            f"{GENERATOR.name}. If the generator's output mechanism changed, update "
            f"HEREDOC_RE — silently matching nothing would make this check vacuous."
        )
    return set(EMITTED_RE.findall(match.group(1)))


def main() -> int:
    for path in (COMPOSE, GENERATOR):
        if not path.is_file():
            print(f"ERROR: {path.relative_to(ROOT)} not found", file=sys.stderr)
            return 1

    required = required_variables()
    emitted = emitted_variables()
    missing = sorted(required - emitted)

    if missing:
        print(
            f"ERROR: {len(missing)} compose-required variable(s) are not produced by "
            f"{GENERATOR.relative_to(ROOT)}.\n"
            "`docker compose` will refuse to render the stack until each is generated:\n",
            file=sys.stderr,
        )
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    print(
        f"check_env_covers_compose OK ({len(required)} compose-required variables, all generated)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

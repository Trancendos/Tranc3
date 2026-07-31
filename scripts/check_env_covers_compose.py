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


def required_variables() -> set[str]:
    return set(REQUIRED_RE.findall(COMPOSE.read_text(encoding="utf-8")))


def emitted_variables() -> set[str]:
    """Variables the generator writes into .env.production.

    Both the shell assignments above the heredoc and the `VAR=${VAR}` lines inside it
    match the same pattern, which is fine: a name has to appear in the heredoc to reach
    the file, and anything only assigned in shell scope is a superset we'd rather not
    flag. The end-to-end check is `docker compose config`, which CI runs when docker is
    available; this is the cheap always-on guard.
    """
    return set(EMITTED_RE.findall(GENERATOR.read_text(encoding="utf-8")))


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

"""One ratchet, used by every checker that holds a backlog at a ceiling.

WHY THIS EXISTS
---------------
This estate had arrived at the same mechanism three times. `nosec_ceiling.txt`
holds bandit suppressions that name a rule but give no reason.
`noqa_ceiling.txt` holds suppressions that silence nothing. Extending bandit's
targets to `scripts/` and `workers/` needed a third. Each is the same four
rules -- an unrecorded ceiling is UNKNOWN, a rise fails, a fall fails until the
ceiling is lowered in the same commit, equality passes -- and writing them a
third time by hand is how three controls come to disagree about what "holding"
means.

The rule the ceiling encodes, in one place:

**A fall fails too.** That looks wrong at first and is the point. If falling
quietly passed, the gap between the real count and the recorded ceiling would
be room for a new suppression nobody sees -- a backlog item removed and
replaced reads as "holding". So the ceiling must be lowered in the same commit
that does the work, and the diff then carries the evidence.

**An unrecorded ceiling is UNKNOWN, never zero.** Zero would read as "nothing
is wrong" and fail every pull request at once; absent means nothing has been
established, which is the truth, and is `grade.py`'s distinction between "did
not look" and "looked and it was fine" applied to a backlog.

NOT YET MIGRATED
----------------
`scripts/check_nosec_specificity.py` keeps its own copy. It is a working guard
with its own tested semantics around bare-suppression refusal, and moving it is
a separate change that should stand or fall on its own tests rather than riding
along with a bandit-coverage commit. Recorded here rather than left implicit,
because an unstated intention to unify is how a fourth copy gets written.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

#: Returned when nothing usable is recorded. Deliberately a distinct value
#: from "all zeros": see the module docstring.
UNRECORDED: dict[str, int] = {}


def read_ceiling(path: Path, *, require: Sequence[str]) -> dict[str, int]:
    """The recorded counts, or `UNRECORDED` when the file cannot be used.

    Accepts `key=value` lines (with `#` comments) and JSON objects, because the
    two existing ceiling files use the former and a per-rule breakdown is
    clearer as the latter. A file missing any key in `require` is UNRECORDED: a
    half-written ceiling is not a ceiling, and treating it as one would compare
    today's count against nothing.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return dict(UNRECORDED)

    found: dict[str, int] = {}
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return dict(UNRECORDED)
        if not isinstance(loaded, dict):
            return dict(UNRECORDED)
        for key, value in loaded.items():
            if isinstance(value, bool) or not isinstance(value, int):
                return dict(UNRECORDED)
            found[str(key)] = value
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            try:
                found[key.strip()] = int(value.strip())
            except ValueError:
                return dict(UNRECORDED)

    if not set(require) <= found.keys():
        return dict(UNRECORDED)
    return found


def write_ceiling(path: Path, counts: dict[str, int], *, header: str) -> None:
    """Record `counts`, with `header` explaining what may and may not change."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {line}" if line else "#" for line in header.strip().splitlines()]
    lines += [f"{key}={counts[key]}" for key in sorted(counts)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare(now: dict[str, int], ceiling: dict[str, int], *, what: str) -> list[str]:
    """Every reason the current counts do not hold at the ceiling.

    Empty means holding. A rise and a fall both produce a failure, with
    different wording, because they need different actions from the reader.
    """
    problems: list[str] = []
    for key in sorted(now):
        limit = ceiling.get(key)
        if limit is None:
            problems.append(f"{key}: no ceiling recorded for this count")
        elif now[key] > limit:
            problems.append(
                f"{key} ROSE to {now[key]} (ceiling {limit}). A new {what} is a claim "
                f"nobody adjudicated. Remove it, or argue for it and raise the ceiling "
                f"deliberately in a commit that says why."
            )
        elif now[key] < limit:
            problems.append(
                f"{key} FELL to {now[key]} (ceiling {limit}). Lower the ceiling in this "
                f"same commit so the diff carries the work: --set-ceiling. Leaving the "
                f"gap open is room for one to be added back unseen."
            )
    return problems


def describe(now: dict[str, int], ceiling: dict[str, int]) -> str:
    """A one-line-per-count summary for a checker's output."""
    rows = []
    for key in sorted(now):
        limit = ceiling.get(key)
        mark = (
            "=" if limit == now[key] else ("^" if limit is not None and now[key] > limit else "v")
        )
        rows.append(
            f"  {key:28s} {now[key]:6d}  ceiling {limit if limit is not None else '—'} {mark}"
        )
    return "\n".join(rows)

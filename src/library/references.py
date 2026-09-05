"""Reference numbering for The Library's knowledge bases and wikis.

The distinction the owner drew
------------------------------
A **Wiki** is the administrative view — orientation, navigation, narrative,
architecture, design specification. A **Knowledge Base** is the user view —
how to do the thing. They had been indistinguishable: a citation of
"the Library page on The Void" told a reader nothing about which of the two
they were being sent to, or whether they were cleared to read it.

Three scopes, because visibility differs
----------------------------------------
Set by the owner on 2026-09-05:

  * **Platform-wide** — `TKB000001`, `TWIX000001`. Trancendos Knowledge Base
    and Trancendos Wiki. Anything that is true of the estate rather than of
    one Location.
  * **Location-scoped** — `Infi-KB-0001`, `Tran-WIX-0001`. Owned by one of the
    43 Locations, prefixed with that Location's own short code, so the
    reference names its owner before anything is looked up.
  * **Personal** — `#One:KB-0001`. Infinity-One's per-user knowledge base:
    individual, user-centric, and private to that user unless they choose to
    share it. The `#One:` sigil is deliberately unlike the other two — a
    personal reference should never be mistaken for an estate one in a
    citation, a log line, or a paste into a shared channel.

Why this is code and not a convention
-------------------------------------
A numbering scheme written down in a document is a numbering scheme people
diverge from, and this estate has measured that outcome repeatedly. Parsing
here means a malformed reference is an error at the point of use, the scope
of any reference is decidable without asking anyone, and a Location code that
does not correspond to a real Location fails rather than being invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from src.entities.platform import PLATFORM_ENTITIES


class Kind(str, Enum):
    """Which of the two collections a reference belongs to."""

    KB = "kb"  #: Knowledge Base — the user view: how to do the thing.
    WIKI = "wiki"  #: Wiki — the administrative view: orientation and design.


class Scope(str, Enum):
    """Who a reference is addressed to, which is also who may read it."""

    PLATFORM = "platform"  #: True of the estate, not of one Location.
    LOCATION = "location"  #: Owned by one of the 43 Locations.
    PERSONAL = "personal"  #: One user's own, private unless they share it.


#: Platform-wide: `TKB000001` / `TWIX000001`.
_PLATFORM = re.compile(r"^T(KB|WIX|Wix|kb|wix)(\d{6})$")

#: Location-scoped: `Infi-KB-0001` / `Tran-WIX-0001`.
_LOCATION = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,9})-(KB|WIX|Wix|kb|wix)-(\d{4})$")

#: Personal: `#One:KB-0001`. The sigil keeps a private reference visibly
#: unlike an estate one wherever it is pasted.
_PERSONAL = re.compile(r"^#One:(KB|WIX|Wix|kb|wix)-(\d{4})$")


@dataclass(frozen=True)
class Reference:
    """One parsed reference.

    `location` is set only for `Scope.LOCATION`; it is the canonical Location
    name, resolved from the short code rather than echoed back, so a
    reference cannot name a Location the register does not have.
    """

    raw: str
    kind: Kind
    scope: Scope
    number: int
    location: Optional[str] = None

    @property
    def is_private(self) -> bool:
        """Personal references are not the estate's to publish.

        Exposed as a property rather than left to callers comparing scopes,
        because the check that gets skipped is the one nobody had to name.
        """
        return self.scope is Scope.PERSONAL


#: The shortest code any Location gets. Four was the owner's example
#: (`Infi-KB`), and it is long enough for 40 of the 43.
_MIN_CODE = 4


def _letters(name: str) -> str:
    """A Location name reduced to the letters a code is cut from."""
    return re.sub(r"[^A-Za-z]", "", name.removeprefix("The ").removeprefix("the "))


#: Codes already issued to Locations, allocated once and never recomputed.
#: See `location_code` for why this file exists.
ALLOCATIONS = Path(__file__).resolve().parents[2] / "config" / "estate" / "location_codes.yaml"


@lru_cache(maxsize=1)
def allocated() -> dict[str, str]:
    """Location name -> the code already issued to it.

    Empty when the file is absent, so a fresh checkout derives rather than
    failing; the alignment test is what makes the file's presence mandatory.
    """
    import yaml  # noqa: PLC0415

    if not ALLOCATIONS.is_file():
        return {}
    payload = yaml.safe_load(ALLOCATIONS.read_text(encoding="utf-8")) or {}
    return dict(payload.get("codes", {}))


def location_code(name: str) -> str:
    """A Location's reference code — allocated once, then never recomputed.

    An allocated code is returned verbatim. Only a Location with no
    allocation is derived, and its derivation must avoid every allocated
    code as well as its unallocated peers.

    **Why an allocation file rather than pure derivation.** Derivation alone
    is not stable: it extends a code only as far as the *current* register
    requires, so adding a Location beginning "Tran" would push `Tranc` to
    `Trance` and `Tranq` to `Tranqu` — and every `Tranc-KB-0001` already
    issued, cited and printed would stop resolving. A reference that stops
    resolving because an unrelated Location was added is not a reference.
    The file is append-only; `tests/test_library_references.py` fails if an
    existing code changes or disappears.

    Four letters is the base, from the owner's own example (`Infi-KB` for
    Infinity). It is not enough for three pairs, and the collisions are real:

      * `Arca` — Arcadia and Arcadian Exchange
      * `Tran` — TranceFlow and Tranquility
      * `Warp` — The Warp Tunnel and Warp Radio

    A code that names two Locations names neither, so a colliding code is
    extended — for both sides, not just the newcomer — to the shortest length
    that separates them. Tranquility therefore becomes `Tranq` and TranceFlow
    `Tranc`; the owner's example of `Tran-Wix` for Tranquility cannot be
    honoured as written without TranceFlow answering to the same prefix.

    Extending both sides matters: leaving one at four would make the shorter
    code look canonical and the longer look like an exception, and the next
    person to add a Location beginning "Tran" would collide again silently.
    """
    issued = allocated()
    if name in issued:
        return issued[name]

    letters = _letters(name)
    taken = {code.lower() for other, code in issued.items() if other != name}
    others = [
        _letters(other) for other in PLATFORM_ENTITIES if other != name and other not in issued
    ]
    length = _MIN_CODE
    while (
        length < len(letters)
        and (
            # An exact clash: two Locations answering to one code.
            letters[:length].lower() in taken
            # A *prefix* of an allocated code. Distinctness alone would allow it
            # — `Tran-KB-0001` and `Tranq-KB-0001` parse to different Locations —
            # but `Tran` is the code the owner wrote for Tranquility, and handing
            # it to a later Location would make their own example resolve to
            # somewhere else. The shorter code is the one that reads as canonical,
            # so a newcomer never takes it.
            or any(code.startswith(letters[:length].lower()) for code in taken)
            or any(other[:length].lower() == letters[:length].lower() for other in others)
        )
    ):
        length += 1
    return letters[:length].capitalize()


def _by_code() -> dict[str, str]:
    """Reference code to canonical Location name.

    Codes are unique by construction — `location_code` extends until they
    are — so this mapping cannot silently lose a Location to a collision.
    `collisions()` asserts that property rather than trusting it.
    """
    return {location_code(name): name for name in PLATFORM_ENTITIES}


def collisions() -> dict[str, list[str]]:
    """Codes claimed by more than one Location. Expected to be empty.

    `location_code` extends a code until it is unique, so this should always
    return nothing — it exists so that "codes are unique" is a checked claim
    rather than an assumed one. Two Locations whose full letter-sequences are
    identical would still collide, and that is a naming problem no derivation
    can solve; it would surface here instead of silently mapping one onto the
    other.
    """
    seen: dict[str, list[str]] = {}
    for name in PLATFORM_ENTITIES:
        seen.setdefault(location_code(name), []).append(name)
    return {code: names for code, names in seen.items() if len(names) > 1}


class InvalidReference(ValueError):
    """A reference that does not parse, with the reason it did not."""


def _number(text: str, digits: str) -> int:
    """The reference's number, refusing zero.

    `format_reference` refuses a number below 1, but the shape regexes match
    all-zero digits, so `TKB000000` parsed cleanly to number 0 — a reference
    the platform will never issue, accepted as valid on the read side. A
    document citing it would pass review and resolve to nothing.
    """
    number = int(digits)
    if number < 1:
        raise InvalidReference(f"{text!r}: reference numbers start at 1")
    return number


def parse(raw: str) -> Reference:
    """Parse a reference, or raise `InvalidReference` saying why.

    Raises rather than returning `None` so a malformed reference cannot be
    quietly treated as "no reference" — the failure mode that lets a citation
    to nothing survive review.
    """
    text = raw.strip()

    match = _PLATFORM.match(text)
    if match:
        kind = Kind.KB if match.group(1).upper() == "KB" else Kind.WIKI
        return Reference(text, kind, Scope.PLATFORM, _number(text, match.group(2)))

    match = _PERSONAL.match(text)
    if match:
        kind = Kind.KB if match.group(1).upper() == "KB" else Kind.WIKI
        return Reference(text, kind, Scope.PERSONAL, _number(text, match.group(2)))

    match = _LOCATION.match(text)
    if match:
        code, kind_text, number = match.groups()
        resolved = _by_code().get(code.capitalize())
        if resolved is None:
            raise InvalidReference(
                f"{text!r}: no Location has the code {code.capitalize()!r}. "
                "A reference may not name a Location the register does not hold."
            )
        kind = Kind.KB if kind_text.upper() == "KB" else Kind.WIKI
        return Reference(text, kind, Scope.LOCATION, _number(text, number), resolved)

    raise InvalidReference(
        f"{text!r} matches no reference form. Expected one of: "
        "TKB000001 / TWIX000001 (platform), Infi-KB-0001 / Tran-WIX-0001 "
        "(Location), #One:KB-0001 (personal)."
    )


#: The widest number each scope's fixed-width field can hold. A number past
#: this formats to a wider field than `parse` will read back, so issuing one
#: would mint an identifier the platform cannot resolve — a reference that
#: only looks like a reference.
_CEILING = {Scope.PLATFORM: 999_999, Scope.PERSONAL: 9_999, Scope.LOCATION: 9_999}


def format_reference(kind: Kind, scope: Scope, number: int, location: str | None = None) -> str:
    """Build a reference, refusing the combinations that have no meaning."""
    if number < 1:
        raise InvalidReference("reference numbers start at 1")
    if number > _CEILING[scope]:
        raise InvalidReference(
            f"{number} exceeds the {scope.value} scope's range (1–{_CEILING[scope]}). "
            "A wider number formats to a field `parse` cannot read back."
        )
    marker = "KB" if kind is Kind.KB else "WIX"

    if scope is Scope.PLATFORM:
        return f"T{marker}{number:06d}"
    if scope is Scope.PERSONAL:
        return f"#One:{marker}-{number:04d}"

    if not location:
        raise InvalidReference("a Location-scoped reference must name its Location")
    if location not in PLATFORM_ENTITIES:
        raise InvalidReference(f"{location!r} is not one of the 43 Locations")
    code = location_code(location)
    if code in collisions():
        raise InvalidReference(
            f"{location!r} shares the code {code!r} with "
            f"{', '.join(n for n in collisions()[code] if n != location)}. "
            "Disambiguate the code before issuing references for either."
        )
    return f"{code}-{marker}-{number:04d}"

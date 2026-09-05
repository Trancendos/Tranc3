"""The Wiki/KB reference scheme, and the collisions deriving it exposed.

The owner set the scheme on 2026-09-05: platform-wide `TKB`/`TWIX`,
Location-scoped `Infi-KB` / `Tran-Wix`, and personal `#One:KB` for
Infinity-One's per-user knowledge base. Before it, a citation to "the Library
page on The Void" said nothing about whether the reader was being sent to the
administrative view or the user view, or whether they were cleared to read it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.entities.platform import PLATFORM_ENTITIES
from src.library.references import (
    ALLOCATIONS,
    InvalidReference,
    Kind,
    Reference,
    Scope,
    allocated,
    collisions,
    format_reference,
    location_code,
    parse,
)


class TestTheThreeScopes:
    """Each scope is visibly different, because visibility differs."""

    def test_a_platform_reference_names_no_location(self):
        """`TKB`/`TWIX` are true of the estate, not of one Location."""
        assert parse("TKB000001") == Reference("TKB000001", Kind.KB, Scope.PLATFORM, 1)
        assert parse("TWIX000042").kind is Kind.WIKI

    def test_a_location_reference_resolves_its_owner(self):
        """The code is resolved to the canonical name, never echoed back.

        A reference cannot therefore name a Location the entity register does
        not hold — the failure that let 22 CMDB records point at the wrong
        service.
        """
        reference = parse("Infi-KB-0001")
        assert reference.scope is Scope.LOCATION
        assert reference.location == "Infinity"

    def test_a_personal_reference_is_marked_private(self):
        """`#One:` is deliberately unlike the other two.

        A personal reference pasted into a shared channel has to be
        recognisable as personal at a glance, and `is_private` exists so the
        check is not left to callers comparing scope values.
        """
        reference = parse("#One:KB-0001")
        assert reference.scope is Scope.PERSONAL
        assert reference.is_private
        assert not parse("TKB000001").is_private
        assert not parse("Infi-KB-0001").is_private


class TestCodesAreDerivedAndUnique:
    """A hand-kept code table is one more register to drift."""

    def test_no_two_locations_share_a_code(self):
        """The property the derivation exists to guarantee."""
        assert collisions() == {}

    def test_the_three_real_collisions_are_separated(self):
        """Four letters is not enough for these, and the pairs are real.

        Arcadia/Arcadian Exchange, TranceFlow/Tranquility and The Warp
        Tunnel/Warp Radio all collide at four. Both sides extend, not just
        one — leaving the shorter at four would make it look canonical and
        the longer look like an exception.
        """
        assert location_code("TranceFlow") != location_code("Tranquility")
        assert location_code("Arcadia") != location_code("Arcadian Exchange")
        assert location_code("The Warp Tunnel") != location_code("Warp Radio")

    def test_the_owners_example_still_holds_where_it_can(self):
        """`Infi-KB` was the owner's example and survives unchanged."""
        assert location_code("Infinity") == "Infi"

    def test_the_definite_article_is_not_part_of_the_code(self):
        """`The Void` is coded `Void`, not `Thev` — 20 Locations start "The"."""
        assert location_code("The Void") == "Void"


class TestItRefusesRatherThanGuesses:
    """A malformed reference must not be readable as "no reference"."""

    def test_an_unknown_location_code_is_rejected(self):
        with pytest.raises(InvalidReference, match="no Location has the code"):
            parse("Zzzz-KB-0001")

    def test_a_shape_that_matches_nothing_says_what_was_expected(self):
        with pytest.raises(InvalidReference, match="matches no reference form"):
            parse("KB-1")

    def test_formatting_refuses_a_location_scope_with_no_location(self):
        with pytest.raises(InvalidReference, match="must name its Location"):
            format_reference(Kind.KB, Scope.LOCATION, 1)

    def test_formatting_refuses_a_location_outside_the_register(self):
        with pytest.raises(InvalidReference, match="not one of the 43"):
            format_reference(Kind.KB, Scope.LOCATION, 1, "Atlantis")

    def test_numbers_start_at_one(self):
        with pytest.raises(InvalidReference, match="start at 1"):
            format_reference(Kind.KB, Scope.PLATFORM, 0)


class TestRoundTrip:
    def test_every_formatted_reference_parses_back(self):
        """Formatting and parsing are the same scheme or one of them is wrong."""
        cases = [
            (Kind.KB, Scope.PLATFORM, 1, None),
            (Kind.WIKI, Scope.PLATFORM, 999999, None),
            (Kind.KB, Scope.LOCATION, 1, "Infinity"),
            (Kind.WIKI, Scope.LOCATION, 42, "Tranquility"),
            (Kind.KB, Scope.PERSONAL, 7, None),
        ]
        for kind, scope, number, location in cases:
            text = format_reference(kind, scope, number, location)
            back = parse(text)
            assert back.kind is kind
            assert back.scope is scope
            assert back.number == number
            if location:
                assert back.location == location

    def test_the_owners_lowercase_wix_spelling_is_accepted(self):
        """They wrote `Tran-Wix`; the canonical emission is `WIX`.

        Rejecting the spelling the scheme was defined in would be a scheme
        nobody could use from memory.
        """
        assert parse("Tranq-Wix-0007").kind is Kind.WIKI
        assert parse("Tranq-WIX-0007").kind is Kind.WIKI


class TestAllocatedCodesAreImmutable:
    """A code that has been issued must never be recomputed.

    Derivation alone extends a code only as far as the current register
    requires. Adding a Location beginning "Tran" would push `Tranc` to
    `Trance`, and every `Tranc-KB-0001` already cited would stop resolving —
    a reference that breaks because an unrelated Location was added is not a
    reference. The allocation file is what makes issued codes permanent.
    """

    def test_every_location_has_an_allocation(self):
        missing = sorted(set(PLATFORM_ENTITIES) - set(allocated()))
        assert missing == [], (
            f"Locations with no allocated code: {missing}. "
            f"Append their derived codes to {ALLOCATIONS.name}."
        )

    def test_allocated_codes_are_unique(self):
        issued = allocated()
        assert len(set(issued.values())) == len(issued)

    def test_the_allocation_wins_over_what_derivation_would_say(self, monkeypatch):
        """Calibrated: making `location_code` re-derive fails this.

        Asserting `location_code(name) == allocated()[name]` for the real
        file proves nothing — the allocation IS what it returns, so it reads
        `code == code` and would pass a change that ignored the file
        entirely. Pinning a code the derivation could not produce is what
        makes the assertion about precedence rather than about equality.
        """
        import src.library.references as references

        monkeypatch.setattr(references, "allocated", lambda: {**allocated(), "Cryptex": "Zzzz"})
        assert references.location_code("Cryptex") == "Zzzz"
        assert references.location_code("Cryptex") != "Cryp"

    def test_the_owners_three_collisions_keep_their_extended_codes(self):
        """The pairs that forced extension, pinned by name.

        Calibrated: shortening any of these to four letters fails this, and
        would reintroduce a code naming two Locations.
        """
        issued = allocated()
        assert issued["Arcadia"] != issued["Arcadian Exchange"]
        assert issued["TranceFlow"] == "Tranc"
        assert issued["Tranquility"] == "Tranq"
        assert issued["The Warp Tunnel"] != issued["Warp Radio"]

    def test_a_new_same_prefix_location_does_not_move_existing_codes(self, monkeypatch):
        """Calibrated: with allocations ignored this returns `Tranquili`.

        This is the whole reason the allocation file exists. "Tranquil
        Waters" shares seven letters with Tranquility, so pure derivation
        pushes Tranquility from `Tranq` to `Tranquili` — and every
        `Tranq-KB-0001` already cited stops resolving, because an unrelated
        Location was added.
        """
        import src.library.references as references

        extended = dict(PLATFORM_ENTITIES)
        extended["Tranquil Waters"] = extended["Tranquility"]
        monkeypatch.setattr(references, "PLATFORM_ENTITIES", extended)

        assert references.location_code("TranceFlow") == "Tranc"
        assert references.location_code("Tranquility") == "Tranq"
        # The newcomer moves, being the one with no references in the world
        # yet — and it does not take `Tran` either, which is a prefix of two
        # allocated codes and the spelling the owner used for Tranquility.
        assert references.location_code("Tranquil Waters") == "Tranqu"


class TestNumbersOutsideTheScopesRange:
    def test_a_platform_number_wider_than_the_field_is_refused(self):
        """Calibrated: dropping the ceiling check fails this.

        `format_reference` would emit `TKB1000000`, which `parse` cannot read
        back — an identifier that looks like a reference and resolves to
        nothing.
        """
        with pytest.raises(InvalidReference, match="exceeds"):
            format_reference(Kind.KB, Scope.PLATFORM, 1_000_000)
        assert format_reference(Kind.KB, Scope.PLATFORM, 999_999) == "TKB999999"

    def test_a_location_number_wider_than_the_field_is_refused(self):
        with pytest.raises(InvalidReference, match="exceeds"):
            format_reference(Kind.KB, Scope.LOCATION, 10_000, "Infinity")
        assert format_reference(Kind.KB, Scope.LOCATION, 9_999, "Infinity") == "Infi-KB-9999"

    def test_a_personal_number_wider_than_the_field_is_refused(self):
        with pytest.raises(InvalidReference, match="exceeds"):
            format_reference(Kind.KB, Scope.PERSONAL, 10_000)


class TestZeroIsNotAReference:
    """Calibrated: removing `_number`'s check passes all three of these.

    `format_reference` refuses a number below 1, but the shape regexes match
    all-zero digits — so a citation to `TKB000000` parsed cleanly, on the
    read side, to a reference the platform will never issue.
    """

    @pytest.mark.parametrize("text", ["TKB000000", "TWIX000000", "Infi-KB-0000", "#One:KB-0000"])
    def test_a_zero_numbered_reference_is_refused(self, text):
        with pytest.raises(InvalidReference, match="start at 1"):
            parse(text)


class TestTheDocumentedCountsAreMeasured:
    """A number written in prose is a claim, and claims drift silently.

    `docs/governance/REFERENCE-NUMBERING.md` said "twenty of the forty-three"
    Locations begin with "The". Nineteen do. Nothing was wrong with the code
    — the derivation drops a leading "The" whatever the count — but the
    governance document that explains the scheme was stating a measurement
    it had never taken, in a file whose whole purpose is to be the reference
    other documents cite. These assertions make the register the source and
    the sentence the thing that has to keep up.
    """

    DOC = Path(__file__).resolve().parents[1] / "docs/governance/REFERENCE-NUMBERING.md"

    #: English for the two counts the document states in words.
    WORDS = {
        19: "nineteen",
        43: "forty-three",
    }

    def test_the_stated_counts_match_the_register(self):
        leading_the = sum(1 for name in PLATFORM_ENTITIES if name.startswith("The "))
        assert leading_the in self.WORDS, (
            f"{leading_the} Locations now begin with 'The'; add the English word for it "
            "here and update docs/governance/REFERENCE-NUMBERING.md to match"
        )
        assert len(PLATFORM_ENTITIES) in self.WORDS

        text = self.DOC.read_text(encoding="utf-8")
        expected = (
            f"{self.WORDS[leading_the]} of the {self.WORDS[len(PLATFORM_ENTITIES)]} begin with it"
        )
        assert expected in text, f"REFERENCE-NUMBERING.md does not say {expected!r}"

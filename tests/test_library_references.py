"""The Wiki/KB reference scheme, and the collisions deriving it exposed.

The owner set the scheme on 2026-09-05: platform-wide `TKB`/`TWIX`,
Location-scoped `Infi-KB` / `Tran-Wix`, and personal `#One:KB` for
Infinity-One's per-user knowledge base. Before it, a citation to "the Library
page on The Void" said nothing about whether the reader was being sent to the
administrative view or the user view, or whether they were cleared to read it.
"""

from __future__ import annotations

import pytest

from src.library.references import (
    InvalidReference,
    Kind,
    Reference,
    Scope,
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

"""Calibration for `src/validation/primitives.py`.

These functions are the ones every other validator is built on, and until now
none of them had a test. `validate_port` is covered hardest because it carries
the trap the others do not: `bool` is a subclass of `int`, so `True` satisfies
both `isinstance(x, int)` and `1 <= x <= 65535`, and a port check that misses
that accepts a flag as a port number.

Every test below was calibrated by mutating the behaviour it protects and
confirming it fails, then restoring.
"""

from __future__ import annotations

import pytest

from src.validation.primitives import (
    validate_email,
    validate_non_empty,
    validate_port,
    validate_safe_string,
    validate_username,
)


class TestValidatePort:
    @pytest.mark.parametrize("port", [1, 80, 8000, 8079, 65535])
    def test_a_port_in_range_is_returned_unchanged(self, port):
        assert validate_port(port) == port

    @pytest.mark.parametrize("port", [0, -1, 65536, 100000])
    def test_a_port_out_of_range_is_refused(self, port):
        with pytest.raises(ValueError, match="out of valid range"):
            validate_port(port)

    @pytest.mark.parametrize("port", [8080.5, "8080", None, [8080]])
    def test_a_non_integer_is_refused_before_the_range_check(self, port):
        """`1 <= 8080.5 <= 65535` is true, so the range check alone passes it."""
        with pytest.raises(ValueError, match="must be an integer"):
            validate_port(port)

    @pytest.mark.parametrize("port", [True, False])
    def test_a_boolean_is_refused_even_though_it_is_an_int(self, port):
        """`bool` subclasses `int`, and `True` is in range. Excluding it is
        the whole reason the type test is written the way it is."""
        with pytest.raises(ValueError, match="must be an integer"):
            validate_port(port)


class TestTheStringPrimitives:
    def test_non_empty_refuses_whitespace_only(self):
        with pytest.raises(ValueError):
            validate_non_empty("   ", "title")

    def test_non_empty_returns_the_trimmed_value(self):
        assert validate_non_empty("  ok  ", "title") == "ok"

    def test_safe_string_refuses_past_its_length_bound(self):
        with pytest.raises(ValueError):
            validate_safe_string("x" * 11, "note", max_length=10)

    def test_safe_string_accepts_exactly_the_bound(self):
        """Off-by-one in the other direction: a limit that rejects the legal
        maximum costs a validator its credibility as fast as one that misses."""
        assert validate_safe_string("x" * 10, "note", max_length=10) == "x" * 10

    @pytest.mark.parametrize("bad", ["", "a", "has space", "sym#bol"])
    def test_username_refuses_what_it_says_it_refuses(self, bad):
        with pytest.raises(ValueError):
            validate_username(bad)

    def test_a_plausible_username_is_accepted(self):
        assert validate_username("norman_hawkins") == "norman_hawkins"

    @pytest.mark.parametrize("bad", ["", "nope", "a@b", "a@b.", "@b.com"])
    def test_email_refuses_what_is_not_an_address(self, bad):
        with pytest.raises(ValueError):
            validate_email(bad)

    def test_a_plausible_address_is_accepted(self):
        assert validate_email("ops@trancendos.com") == "ops@trancendos.com"

"""The collated backlog, and the two ways a collation can lie.

The estate records outstanding work in 44 registers. Each is correct about
its own domain and blind to the rest, so nobody can answer "what is
outstanding across the platform" without reading 320 documents — and an
action in a register nobody sweeps is an action nobody does.

A sweep that reports the wrong text, or that goes stale, is worse than none:
it looks like an answer.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BACKLOG = REPO / "docs" / "governance" / "ACTION-BACKLOG.md"


@pytest.fixture(scope="module")
def builder():
    path = REPO / "scripts" / "build_action_backlog.py"
    spec = importlib.util.spec_from_file_location("build_action_backlog", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_action_backlog"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestItReadsTheAction:
    def test_the_header_names_the_action_column(self, builder):
        """Calibrated: taking the longest cell fails this.

        The first version reported a register's notes as its action —
        "Fabulousa is reachable but unauthenticated" instead of "Issue
        PENPOT_TOKEN into The Void". A backlog that says the wrong thing
        about work it correctly found is worse than one that misses it.
        """
        header = ["#", "Action", "Status", "Notes"]
        assert builder._action_column(header) == 1

    def test_a_status_column_is_never_the_action(self, builder):
        header = ["ID", "Status", "Owner"]
        assert builder._action_column(header) is None

    def test_the_penpot_row_reads_as_its_action(self, builder):
        """The specific row the heuristic got wrong, asserted by name.

        Rendered fresh rather than read from the committed file: reading the
        file would pass under the mutation until somebody regenerated, which
        makes the test a check on the artefact instead of on the rule.
        """
        text = builder.render(builder.harvest())
        assert "| Issue `PENPOT_TOKEN` into The Void |" in text
        assert "| Fabulousa is reachable but unauthenticated |" not in text


class TestSizingIsDerived:
    def test_an_impeded_item_costs_more_than_an_open_one(self, builder):
        locations = builder._locations()
        open_item = {"status": "Open", "location": "Fabulousa", "source": "docs/x.md"}
        blocked = {"status": "Funding-gated", "location": "Fabulousa", "source": "docs/x.md"}
        assert builder.size(blocked, locations)[0] > builder.size(open_item, locations)[0]

    def test_an_unrouted_item_costs_more_than_a_routed_one(self, builder):
        locations = builder._locations()
        routed = {"status": "Open", "location": "Fabulousa", "source": "docs/x.md"}
        unrouted = {"status": "Open", "location": "", "source": "docs/x.md"}
        assert builder.size(unrouted, locations)[0] > builder.size(routed, locations)[0]

    def test_every_point_carries_its_reason(self, builder):
        """Calibrated: returning the number alone fails this.

        A number nobody can interrogate is a number nobody trusts, and an
        unarguable estimate is how a backlog stops being used.
        """
        _, why = builder.size(
            {"status": "Blocked", "location": "", "source": "docs/compliance/x.md"},
            builder._locations(),
        )
        assert len(why) == 4

    def test_points_land_on_the_fibonacci_scale(self, builder):
        locations = builder._locations()
        for status in ("Open", "Blocked", "Needs owner", "Partial"):
            for source in ("docs/x.md", "docs/compliance/x.md"):
                for location in ("", "Fabulousa"):
                    points, _ = builder.size(
                        {"status": status, "location": location, "source": source}, locations
                    )
                    assert points in builder._FIBONACCI


class TestTheSweepDoesNotReadItself:
    def test_the_generated_backlog_is_not_a_register(self, builder):
        """It is a markdown document full of tables, so it reads as one.

        Every generation re-ingested the previous one: 163 items became 326,
        then 489, compounding by the same 163 each run. `--check` could never
        pass, because regenerating produced a different file from the one it
        had just written — a gate that fails on correct input, which is how a
        gate gets switched off.
        """
        swept = {path.relative_to(builder.REPO).as_posix() for path in builder._documents()}
        assert "docs/governance/ACTION-BACKLOG.md" not in swept

    def test_generating_twice_produces_the_same_document(self, builder):
        """The property the exclusion exists to give, asserted directly.

        Reading `_documents()` proves the output is skipped; this proves the
        sweep as a whole is a function of the registers, which is what
        `--check` relies on.
        """
        first = builder.render(builder.harvest())
        second = builder.render(builder.harvest())
        assert first == second


class TestTheCommittedCopy:
    def test_it_matches_the_registers(self, builder):
        assert builder.main(["--check"]) == 0

    def test_it_actually_found_the_estate(self, builder):
        """A sweep over nothing passes vacuously."""
        items = builder.harvest()
        assert len(items) > 100
        assert len({item["source"] for item in items}) > 30

    def test_it_states_a_definition_of_ready_and_done(self):
        text = BACKLOG.read_text(encoding="utf-8")
        assert "## Definition of Ready" in text
        assert "## Definition of Done" in text

    def test_it_does_not_invent_a_velocity(self):
        """A sprint count from an invented velocity is a confident fiction."""
        text = BACKLOG.read_text(encoding="utf-8")
        assert "Velocity is not asserted here" in text

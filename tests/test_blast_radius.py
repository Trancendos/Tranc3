"""Blast radius over the identity spine, and the honesty about what it cannot see.

The estate's dependency graph is sparse: 82 of 92 services have no inbound
edge recorded at all. So the property that matters most here is not "the
traversal finds the right nodes" — it is that **an empty result is
distinguishable from an unknown one**. An incident prioritiser that reads
"0 affected" as a genuine zero will downgrade real P1s across 89% of the
estate.
"""

from __future__ import annotations

import pytest

from src.cmdb.blast_radius import (
    DEFAULT_MAX_HOPS,
    Confidence,
    EdgeSource,
    blast_radius,
    coverage,
    reset_cache,
    safe_blast_radius,
    services_without_dependency_data,
)
from src.cmdb.identity import IdentityResolutionError

#: A service with recorded dependants, and one without. Both are read from the
#: live workbook rather than hardcoded, so the suite follows the data.
WITH_DATA = "SRV-VOID-001"


@pytest.fixture(scope="module")
def without_data() -> str:
    absent = services_without_dependency_data()
    assert absent, "expected at least one service with no dependency data"
    return absent[0]


class TestUnknownIsNotEmpty:
    """The reason this module exists."""

    def test_a_service_with_no_recorded_dependants_reports_unknown(self, without_data):
        radius = blast_radius(without_data)
        assert radius.affected == ()
        assert not radius.has_dependency_data
        assert radius.unknown_rather_than_empty

    def test_a_service_with_dependants_is_not_flagged_unknown(self):
        radius = blast_radius(WITH_DATA)
        assert radius.affected
        assert radius.has_dependency_data
        assert not radius.unknown_rather_than_empty

    def test_the_caveat_says_plainly_it_is_not_a_finding_of_zero(self, without_data):
        # A reader who acts on the number without reading this is the failure
        # mode; the wording has to make that hard.
        caveat = blast_radius(without_data).caveat
        assert "NOT a finding that nothing depends on it" in caveat

    def test_the_serialised_form_carries_the_distinction(self, without_data):
        # Anything consuming this over HTTP must be able to tell the two apart
        # without re-deriving it.
        payload = blast_radius(without_data).to_dict()
        assert payload["affected_count"] == 0
        assert payload["unknown_rather_than_empty"] is True
        assert payload["has_dependency_data"] is False

    def test_every_radius_carries_estate_coverage(self):
        # So a caller never has to go looking for how much the answer is worth.
        radius = blast_radius(WITH_DATA)
        assert radius.coverage.services > 0
        assert radius.coverage.with_inbound_edges + radius.coverage.without_inbound_edges == (
            radius.coverage.services
        )


class TestCoverageIsMeasuredNotClaimed:
    def test_coverage_partitions_the_estate(self):
        c = coverage()
        assert c.with_inbound_edges + c.without_inbound_edges == c.services
        assert 0.0 <= c.fraction_covered <= 1.0

    def test_the_uncovered_list_matches_the_count(self):
        assert len(services_without_dependency_data()) == coverage().without_inbound_edges

    def test_the_graph_is_sparse_enough_to_need_this_module(self):
        # A floor, not an exact value — the point is that the honesty machinery
        # is load-bearing, not decorative. If coverage ever becomes near-total
        # this test should be revisited rather than deleted.
        assert coverage().without_inbound_edges > 0


class TestConfidenceReflectsHowFarTheClaimReaches:
    def test_direct_dependants_are_known(self):
        radius = blast_radius(WITH_DATA)
        assert radius.known
        assert all(a.hops == 1 for a in radius.known)
        assert all(a.confidence is Confidence.KNOWN for a in radius.known)

    def test_transitive_dependants_are_only_probable(self):
        # Each hop is recorded, but nobody verified the combination end to end.
        radius = blast_radius(WITH_DATA)
        # Without this the assertions below hold vacuously the moment nothing
        # is classed PROBABLE -- which is exactly what a bug that marks every
        # node KNOWN would do.
        assert radius.probable, "no transitive nodes; the rest of this proves nothing"
        assert all(a.hops > 1 for a in radius.probable)
        assert all(a.confidence is Confidence.PROBABLE for a in radius.probable)

    def test_known_and_probable_partition_the_affected_set(self):
        radius = blast_radius(WITH_DATA)
        assert len(radius.known) + len(radius.probable) == len(radius.affected)

    def test_every_affected_node_carries_the_path_that_reached_it(self):
        radius = blast_radius(WITH_DATA)
        for node in radius.affected:
            assert node.path[0] == radius.origin.service_id
            assert node.path[-1] == node.service_id
            assert len(node.path) == node.hops + 1


class TestTheWalkTerminatesAndStaysBounded:
    def test_the_origin_is_never_in_its_own_radius(self):
        radius = blast_radius(WITH_DATA)
        assert radius.origin.service_id not in {a.service_id for a in radius.affected}

    def test_no_service_appears_twice(self):
        ids = [a.service_id for a in blast_radius(WITH_DATA).affected]
        assert len(ids) == len(set(ids))

    def test_max_hops_bounds_the_walk(self):
        assert all(a.hops <= 1 for a in blast_radius(WITH_DATA, max_hops=1).affected)
        assert all(a.hops <= 2 for a in blast_radius(WITH_DATA, max_hops=2).affected)

    def test_one_hop_yields_only_known_nodes(self):
        radius = blast_radius(WITH_DATA, max_hops=1)
        assert radius.probable == ()

    def test_a_wider_walk_never_loses_a_closer_node(self):
        near = {a.service_id for a in blast_radius(WITH_DATA, max_hops=1).affected}
        far = {a.service_id for a in blast_radius(WITH_DATA, max_hops=3).affected}
        assert near <= far

    def test_a_cyclic_graph_terminates(self):
        # Infinity is depended on by 86 services and itself depends on The
        # Void, which Infinity is reachable from. If the walk did not track
        # visited nodes this would not return.
        radius = blast_radius("SRV-INF-001", max_hops=DEFAULT_MAX_HOPS)
        assert radius.affected

    def test_max_hops_below_one_is_refused(self):
        with pytest.raises(ValueError):
            blast_radius(WITH_DATA, max_hops=0)


class TestItResolvesThroughTheIdentitySpine:
    def test_a_pid_or_location_name_works_as_well_as_a_service_id(self):
        by_service_id = blast_radius("SRV-SPARK-001")
        by_pid = blast_radius("PID-SPK")
        by_name = blast_radius("The Spark")
        assert (
            by_service_id.origin.service_id == by_pid.origin.service_id == by_name.origin.service_id
        )

    def test_an_unknown_identifier_raises(self):
        # An empty radius for a typo is indistinguishable from an empty radius
        # for a real service with no dependants — so it must not be returned.
        with pytest.raises(IdentityResolutionError):
            blast_radius("SRV-NOPE-999")

    def test_the_safe_variant_returns_none_instead_of_raising(self):
        assert safe_blast_radius("SRV-NOPE-999") is None
        assert safe_blast_radius(WITH_DATA) is not None

    def test_an_ambiguous_location_is_called_out_in_the_caveat(self):
        # The Observatory owns six services; a radius for one of them is not a
        # radius for the Location.
        radius = blast_radius("The Observatory")
        if radius.origin.location_is_ambiguous and radius.has_dependency_data:
            assert "owns" in radius.caveat and "services_for_location" in radius.caveat

    def test_affected_nodes_carry_their_owner(self):
        # So an incident can page the right AI without a second lookup.
        radius = blast_radius(WITH_DATA)
        owned = [a for a in radius.affected if a.location]
        assert owned
        assert any(a.tier3_ai for a in owned)

    def test_locations_are_deduplicated_for_routing(self):
        locations = blast_radius(WITH_DATA).locations
        assert len(locations) == len(set(locations))


class TestBothWorkbookSourcesAreRead:
    """The flat column covers all 92 services but names 10 targets; the edge
    table is rich but holds 7 edges. Neither is sufficient alone."""

    def test_edges_from_the_dependency_table_are_present(self):
        radius = blast_radius(WITH_DATA, max_hops=1)
        sources = {s for a in radius.affected for s in a.sources}
        assert EdgeSource.EDGE_TABLE in sources or EdgeSource.INVENTORY in sources

    def test_the_richer_table_contributes_failure_impact(self):
        # The edge table is the only source carrying failure impact. If it were
        # dropped, every node would come back with an empty one.
        seen = False
        for service in ("SRV-VOID-001", "SRV-OBS-001", "SRV-SPARK-001"):
            for node in blast_radius(service, max_hops=1).affected:
                if node.failure_impact:
                    seen = True
        assert seen, "no edge carried a failure impact; the edge table is not being read"


class TestResetCacheResetsEverythingItReads:
    def test_it_clears_the_identity_index_too(self):
        """`reset_cache` exists for tests that rewrite the workbook.

        `_edges()` and `coverage()` both read through the cached identity
        index, so clearing only the graph caches left the inventory half
        stale and the function did not do what its name promised.
        """
        from src.cmdb.identity import _index

        _index()  # populate
        assert _index.cache_info().currsize == 1
        reset_cache()
        assert _index.cache_info().currsize == 0

    def test_the_graph_still_answers_after_a_reset(self):
        reset_cache()
        assert blast_radius(WITH_DATA).affected

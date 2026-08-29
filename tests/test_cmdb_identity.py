"""Tests for the service identity spine (src/cmdb/identity.py).

Each test states one property of the join and fails if that property is
removed. The point of the module is that a cross-domain question gets the
same answer whichever namespace asked it, so most of these compare answers
rather than assert a hardcoded value that would just restate the CSV.
"""

from __future__ import annotations

import pytest

from src.cmdb.identity import (
    IdentityResolutionError,
    coverage,
    resolve,
    services_for_location,
    unmapped_services,
)


class TestTheJoinAgreesAcrossNamespaces:
    """The same service, asked for four ways, is one service."""

    def test_service_id_pid_and_location_resolve_to_the_same_record(self):
        by_service_id = resolve("SRV-SPARK-001")
        by_pid = resolve("PID-SPK")
        by_location = resolve("The Spark")

        assert by_service_id.service_id == by_pid.service_id == by_location.service_id
        assert by_service_id.location == "The Spark"
        assert by_service_id.pid == "PID-SPK"

    def test_a_port_resolves_to_the_location_that_binds_it(self):
        # tAimra binds 8074 in docker-compose.production.yml.
        assert resolve(8074).location == "tAimra"

    def test_resolution_is_deterministic(self):
        # Two callers reading the same CMDB must not disagree about who owns
        # an incident. A dict-ordering-dependent pick would pass once and
        # fail under a different insertion order.
        answers = {resolve("The Observatory").service_id for _ in range(25)}
        assert len(answers) == 1


class TestUnknownIdentifiersRaiseRatherThanReturnNothing:
    """A silent None becomes a wrong answer one call downstream."""

    @pytest.mark.parametrize("bad", ["SRV-NOPE-999", "Not A Location", "PID-ZZZ", ""])
    def test_unknown_identifier_raises(self, bad):
        with pytest.raises(IdentityResolutionError):
            resolve(bad)

    def test_unbound_port_raises(self):
        with pytest.raises(IdentityResolutionError):
            resolve(65000)


class TestAmbiguityIsVisibleRatherThanSilentlyResolved:
    """The Observatory owns six services. Returning one of six quietly is
    how a blast radius ends up five services short."""

    def test_a_multi_service_location_is_flagged_ambiguous(self):
        identity = resolve("The Observatory")
        assert identity.location_is_ambiguous
        assert identity.location_service_count > 1

    def test_a_single_service_location_is_not_flagged(self):
        identity = resolve("SRV-SPARK-001")
        assert not identity.location_is_ambiguous
        assert identity.location_service_count == 1

    def test_the_flagged_count_matches_what_services_for_location_returns(self):
        # If these two disagree, the flag is lying about how much was hidden.
        identity = resolve("The Observatory")
        assert identity.location_service_count == len(services_for_location("The Observatory"))


class TestUnmappedServicesAreExplainedNotHidden:
    """A service with no Location is expected for cross-cutting
    infrastructure and a defect for a dangling PID. The two must be
    distinguishable, or the second hides inside the first."""

    def test_every_unmapped_service_carries_a_reason(self):
        for service in unmapped_services():
            assert service.unmapped_reason, service.service_id

    def test_no_service_references_a_pid_the_entity_registry_does_not_know(self):
        # This is a consistency check between two committed sources —
        # 02_service_inventory.csv and src/entities/platform.py. It fails if
        # either drifts, which is the point.
        broken = [
            s
            for s in unmapped_services()
            if s.unmapped_reason and s.unmapped_reason.startswith("PID ")
        ]
        assert broken == [], f"dangling PID references: {[s.service_id for s in broken]}"

    def test_mapped_and_unmapped_partition_the_estate(self):
        c = coverage()
        assert (
            c["mapped_to_location"] + c["cross_cutting"] + c["broken_pid_reference"]
            == c["services"]
        )


class TestTheSpineActuallyCoversTheEstate:
    """A join that resolves three services is not a spine. These are floors,
    not exact values, so adding services to the CSV does not fail the suite —
    but silently losing the PID column would."""

    def test_most_of_the_estate_maps_to_a_location(self):
        c = coverage()
        assert c["services"] >= 90
        assert c["mapped_to_location"] >= 70

    def test_the_spine_reaches_most_of_the_43_locations(self):
        assert coverage()["distinct_locations"] >= 35


class TestOwnershipQuestionsTheArchitectureNeedsToAnswer:
    """The ITIL4 architecture asks these of every incident and change. Before
    the spine existed they had no programmatic answer at all."""

    def test_a_service_id_yields_the_ai_accountable_for_it(self):
        identity = resolve("SRV-SPARK-001")
        assert identity.tier3_ai == "Imfy"
        assert identity.tier2_prime == "Cornelius MacIntyre"

    def test_a_service_id_yields_its_declared_dependencies(self):
        # The raw CSV stores these semicolon-separated; the spine splits them
        # so a blast-radius walk does not have to re-parse the format.
        deps = resolve("SRV-SPARK-001").depends_on_services
        assert isinstance(deps, tuple)
        assert all(d and ";" not in d for d in deps)

    def test_a_location_yields_every_service_it_owns(self):
        owned = services_for_location("The Observatory")
        assert len(owned) > 1
        assert all(s.location == "The Observatory" for s in owned)

    def test_services_for_location_accepts_a_pid_as_well_as_a_name(self):
        assert [s.service_id for s in services_for_location("PID-AEX")] == [
            s.service_id for s in services_for_location("Arcadian Exchange")
        ]

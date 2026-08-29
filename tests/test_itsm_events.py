"""The ITSM event vocabulary, and the routing that has to accept it.

The six ITIL4-AILP domains had no verbs on the platform event bus, so every
arrow in the closed-loop architecture diagram was drawn and not built. These
tests hold the vocabulary in place and, more importantly, hold the *routing*
in place — because the way this fails is silent.
"""

from __future__ import annotations

import pytest

from src.event_bus.types import PlatformEventType
from src.event_bus.wiring import _event_type_to_sentinel_channel

#: The channels Sentinel Station will accept. Mirrors SentinelChannel in
#: workers/dimensional-nexus-service/Dimensional/infinity/nomenclature.py.
#:
#: Duplicated here on purpose rather than imported: that module lives inside a
#: worker's vendored tree, is copied into several workers, and is not on this
#: package's import path. The duplication is the thing under test — if the
#: worker's enum changes and this list does not, the test below that walks
#: every event type will start passing against a stale set, so
#: `test_the_mirrored_channel_list_matches_the_worker` reads the worker's
#: actual source and fails when they diverge.
SENTINEL_CHANNELS = frozenset(
    {
        "platform",
        "agents",
        "models",
        "workflows",
        "security",
        "hive",
        "nexus",
        "bridge",
        "pillars",
        "infrastructure",
        "events",
    }
)

ITSM_PREFIXES = ("request", "incident", "problem", "change", "config", "improvement")


def itsm_event_types() -> list[PlatformEventType]:
    return [m for m in PlatformEventType if m.value.split(".")[0] in ITSM_PREFIXES]


class TestTheSixDomainsHaveVerbs:
    """Before this, zero of the platform's event types were ITSM verbs."""

    @pytest.mark.parametrize(
        "prefix", ["request", "incident", "problem", "change", "config", "improvement"]
    )
    def test_each_domain_can_say_something(self, prefix):
        assert [m for m in PlatformEventType if m.value.startswith(f"{prefix}.")], prefix

    def test_the_lifecycle_transitions_a_closed_loop_needs_are_present(self):
        # Not an exhaustive list — the specific ones the architecture's own
        # cross-practice walk depends on. An incident that cannot say it was
        # resolved cannot trigger a problem; a change that cannot say it rolled
        # back cannot raise one.
        required = {
            "incident.raised",
            "incident.resolved",
            "problem.opened",
            "problem.known_error.published",
            "change.deployed",
            "change.rolled_back",
            "config.drift.unauthorised",
            "improvement.raised",
        }
        assert required <= {m.value for m in PlatformEventType}

    def test_event_values_are_unique(self):
        values = [m.value for m in PlatformEventType]
        assert len(values) == len(set(values))

    def test_itsm_verbs_do_not_collide_with_the_existing_vocabulary(self):
        # `config.*` is new; nothing else in the bus used that root. If a later
        # change introduces one, this catches the ambiguity before two
        # subsystems start routing on the same prefix for different reasons.
        roots = [m.value.split(".")[0] for m in PlatformEventType]
        for prefix in ITSM_PREFIXES:
            owned = [m for m in PlatformEventType if m.value.startswith(f"{prefix}.")]
            assert len(owned) == roots.count(prefix), prefix


class TestEveryITSMEventRoutesToAChannelSentinelAccepts:
    """This is the test that matters.

    Sentinel Station validates `channel` against a closed enum and rejects
    anything else — and `_sentinel_forward` catches the failure into
    `logger.debug`. So a channel name that Sentinel does not know does not
    error, it silently drops every event routed to it. A mapping bug here
    looks exactly like a quiet system.
    """

    @pytest.mark.parametrize("event", itsm_event_types(), ids=lambda e: e.value)
    def test_the_channel_is_one_sentinel_would_accept(self, event):
        assert _event_type_to_sentinel_channel(event.value) in SENTINEL_CHANNELS

    def test_every_event_type_on_the_bus_routes_somewhere_valid(self):
        # Not just the ITSM ones — the fallback has to hold for the whole
        # vocabulary, or adding any future event silently breaks forwarding.
        for member in PlatformEventType:
            channel = _event_type_to_sentinel_channel(member.value)
            assert channel in SENTINEL_CHANNELS, f"{member.value} -> {channel}"

    def test_an_unknown_event_type_still_routes_somewhere_valid(self):
        assert _event_type_to_sentinel_channel("something.nobody.defined") in SENTINEL_CHANNELS

    def test_the_mirrored_channel_list_matches_the_worker(self):
        """Guard the duplication above against drift.

        SENTINEL_CHANNELS is a hand copy of the worker's enum. If the worker
        gains or loses a channel and this copy does not follow, every other
        test in this class starts checking against a set that no longer
        reflects what Sentinel accepts — passing while the routing is wrong.
        """
        import pathlib
        import re

        # Anchored to this file, not the pytest working directory. A relative
        # path meant that running the suite from anywhere but the repo root
        # made source.exists() False and skipped -- so the mirror every other
        # assertion in this class trusts would have been verified by nothing.
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "workers/dimensional-nexus-service/Dimensional/infinity/nomenclature.py"
        )
        if not source.exists():  # pragma: no cover - worker tree not checked out
            pytest.skip("dimensional-nexus worker tree not present")

        body = source.read_text(encoding="utf-8")
        block = re.search(r"class SentinelChannel\(str, Enum\):(.*?)(?=\n\S)", body, re.DOTALL)
        assert block, "SentinelChannel enum not found in the worker source"
        actual = set(re.findall(r'^\s+[A-Z_]+ = "([a-z_]+)"', block.group(1), re.M))
        assert actual == set(SENTINEL_CHANNELS), (
            f"mirrored list drifted from the worker: "
            f"only in worker {sorted(actual - set(SENTINEL_CHANNELS))}, "
            f"only here {sorted(set(SENTINEL_CHANNELS) - actual)}"
        )


class TestRoutingPutsEventsWhereSomeoneWouldLook:
    """A valid channel is not automatically the right one."""

    def test_unauthorised_drift_goes_to_security_not_infrastructure(self):
        # Production state changing with no authorising change record is a
        # security event first. Filed with routine deployment chatter, it gets
        # missed — which is the whole failure mode drift detection exists for.
        assert _event_type_to_sentinel_channel("config.drift.unauthorised") == "security"

    def test_ordinary_drift_and_baselines_go_to_infrastructure(self):
        assert _event_type_to_sentinel_channel("config.drift.detected") == "infrastructure"
        assert _event_type_to_sentinel_channel("config.drift.authorised") == "infrastructure"
        assert _event_type_to_sentinel_channel("config.baseline.captured") == "infrastructure"

    def test_changes_go_to_infrastructure(self):
        for value in ("change.requested", "change.deployed", "change.rolled_back"):
            assert _event_type_to_sentinel_channel(value) == "infrastructure"

    def test_the_service_desk_domains_stay_on_platform(self):
        for value in (
            "incident.raised",
            "problem.opened",
            "request.submitted",
            "improvement.raised",
        ):
            assert _event_type_to_sentinel_channel(value) == "platform"

    def test_the_families_that_used_to_route_nowhere_now_route_somewhere(self):
        """Four families named channels Sentinel does not have.

        "ai", "auth", "users" and "financial" are not SentinelChannel members,
        so 17 of the platform's 60 event types would have been answered 422 and
        dropped into logger.debug. These pin the corrected destinations.
        """
        assert _event_type_to_sentinel_channel("ai.inference.complete") == "models"
        assert _event_type_to_sentinel_channel("auth.token.issued") == "security"
        assert _event_type_to_sentinel_channel("user.created") == "platform"
        assert _event_type_to_sentinel_channel("payment.received") == "platform"
        assert _event_type_to_sentinel_channel("order.created") == "platform"

    def test_the_routing_that_was_already_correct_is_unchanged(self):
        assert _event_type_to_sentinel_channel("workflow.started") == "workflows"
        assert _event_type_to_sentinel_channel("service.registered") == "platform"
        assert _event_type_to_sentinel_channel("secret.stored") == "security"
        assert _event_type_to_sentinel_channel("security.cve.ingested") == "security"

    def test_no_family_named_after_a_channel_lands_on_the_generic_default(self):
        """The gap the per-member validity sweep could not see.

        `security.*` routed to "platform". That is a *valid* channel, so the
        422 test passed, nothing was rejected and nothing was logged -- threat
        detections were delivered to everyone except the people subscribed to
        security. Validity is not correctness.

        So: if an event family is named after a channel, it must route to that
        channel and not fall through to the default. Singular and plural both
        count (`workflow.*` -> "workflows").
        """
        from src.event_bus.types import PlatformEventType

        misrouted = []
        for member in PlatformEventType:
            prefix = member.value.split(".", 1)[0]
            destination = _event_type_to_sentinel_channel(member.value)
            for channel in SENTINEL_CHANNELS:
                if channel == "platform":
                    continue  # the default; nothing can "fall through" to it wrongly
                if prefix in (channel, channel.rstrip("s")) and destination != channel:
                    misrouted.append((member.value, destination, channel))
        assert not misrouted, f"families named after a channel but routed elsewhere: {misrouted}"

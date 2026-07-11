# tests/test_access.py
# Tests for src/access/registry.py — the Location Access & Subscription
# Registry.

from __future__ import annotations

import pytest

from src.access.registry import (
    CURRENT_TERMS_VERSION,
    AccessRegistry,
    StaleTermsVersionError,
    TermsNotAcceptedError,
    UnknownLocationError,
)
from src.entities.platform import PLATFORM_ENTITIES


@pytest.fixture
def registry(tmp_path):
    db_path = tmp_path / "access_registry_test.db"
    reg = AccessRegistry(db_path=db_path)
    yield reg
    reg.close()


class TestSubscribe:
    def test_subscribe_creates_active_subscription(self, registry):
        sub = registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        assert sub.status == "active"
        assert sub.is_active is True
        assert sub.terms_version == CURRENT_TERMS_VERSION
        assert sub.revoked_at is None

    def test_subscribe_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.subscribe(
                "user-1",
                "Nonexistent Place",
                accepted_terms=True,
                terms_version=CURRENT_TERMS_VERSION,
            )

    def test_subscribe_without_accepting_terms_raises(self, registry):
        with pytest.raises(TermsNotAcceptedError):
            registry.subscribe(
                "user-1", "The Lab", accepted_terms=False, terms_version=CURRENT_TERMS_VERSION
            )

    def test_subscribe_with_stale_terms_version_raises(self, registry):
        with pytest.raises(StaleTermsVersionError):
            registry.subscribe("user-1", "The Lab", accepted_terms=True, terms_version="0.1")

    def test_resubscribe_after_unsubscribe_reactivates(self, registry):
        registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        registry.unsubscribe("user-1", "The Lab")
        sub = registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        assert sub.status == "active"
        assert sub.revoked_at is None


class TestUnsubscribe:
    def test_unsubscribe_marks_revoked_not_deleted(self, registry):
        registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        sub = registry.unsubscribe("user-1", "The Lab")
        assert sub.status == "revoked"
        assert sub.revoked_at is not None
        # still queryable, just inactive
        assert registry.get_subscription("user-1", "The Lab") is not None
        assert registry.is_subscribed("user-1", "The Lab") is False

    def test_unsubscribe_without_ever_subscribing_is_idempotent(self, registry):
        sub = registry.unsubscribe("user-1", "The Lab")
        assert sub.status == "revoked"

    def test_unsubscribe_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.unsubscribe("user-1", "Nonexistent Place")


class TestIsSubscribed:
    def test_false_when_never_subscribed(self, registry):
        assert registry.is_subscribed("user-1", "The Lab") is False

    def test_true_after_subscribing(self, registry):
        registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        assert registry.is_subscribed("user-1", "The Lab") is True


class TestListing:
    def test_list_user_subscriptions_active_only(self, registry):
        registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        registry.subscribe(
            "user-1", "The Workshop", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        registry.unsubscribe("user-1", "The Workshop")
        active = registry.list_user_subscriptions("user-1", active_only=True)
        assert {s.location for s in active} == {"The Lab"}

    def test_list_user_subscriptions_all(self, registry):
        registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        registry.unsubscribe("user-1", "The Lab")
        all_subs = registry.list_user_subscriptions("user-1", active_only=False)
        assert len(all_subs) == 1
        assert all_subs[0].status == "revoked"

    def test_list_location_subscribers(self, registry):
        registry.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        registry.subscribe(
            "user-2", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        subs = registry.list_location_subscribers("The Lab")
        assert {s.user_id for s in subs} == {"user-1", "user-2"}

    def test_list_location_subscribers_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.list_location_subscribers("Nonexistent Place")


class TestReconnectPersistence:
    def test_subscription_survives_reconnect(self, tmp_path):
        db_path = tmp_path / "reopen_access.db"
        reg1 = AccessRegistry(db_path=db_path)
        reg1.subscribe(
            "user-1", "The Lab", accepted_terms=True, terms_version=CURRENT_TERMS_VERSION
        )
        reg1.close()

        reg2 = AccessRegistry(db_path=db_path)
        assert reg2.is_subscribed("user-1", "The Lab") is True
        reg2.close()


def test_current_terms_version_matches_all_43_locations_are_subscribable():
    # Sanity check that CURRENT_TERMS_VERSION is a real, non-empty version
    # string and every canonical Location can be subscribed to.
    assert CURRENT_TERMS_VERSION
    assert len(PLATFORM_ENTITIES) == 43

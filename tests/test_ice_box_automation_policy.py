"""No-network acceptance tests for the IceBox automation seam."""

import pytest

from src.security.ice_box.automation_policy import plan_scan
from integrations.icebox_ycloud.alerts import (
    AlertNotAuthorised,
    YCloudAlertConfig,
    prepare_queued_template,
)


@pytest.mark.parametrize("verdict, quarantined, disposition, priority", [
    ("clean", False, "allow_static", "none"),
    ("suspicious", False, "hold_for_review", "review"),
    ("malicious", False, "isolate_and_review", "urgent"),
    ("quarantined", True, "isolate_and_review", "urgent"),
    ("CLEAN", True, "hold_for_review", "review"),
    ("novel", False, "hold_for_review", "review"),
])
def test_policy_is_conservative(verdict, quarantined, disposition, priority):
    actual = plan_scan(verdict, quarantined=quarantined)
    assert actual.disposition == disposition
    assert actual.priority == priority
    assert not actual.allow_automatic_release
    assert not actual.dynamic_execution_enabled


def test_verdict_rejects_non_strings():
    with pytest.raises(TypeError):
        plan_scan(None, quarantined=False)


def _config(**override):
    data = dict(enabled=True, recipient_opted_in=True, template_approved=True,
                sender_e164="+447911123456", recipient_e164="+447911654321",
                template_name="icebox_static_alert", language_code="en_GB")
    return YCloudAlertConfig(**(data | override))


def test_ycloud_builder_is_disabled_by_default():
    with pytest.raises(AlertNotAuthorised):
        prepare_queued_template(plan_scan("malicious", quarantined=True), YCloudAlertConfig(), "event-1")


def test_only_urgent_opted_in_event_gets_prepared():
    with pytest.raises(AlertNotAuthorised):
        prepare_queued_template(plan_scan("suspicious", quarantined=True), _config(), "event-2")


def test_denies_unapproved_template_or_unsubscribed_recipient():
    for overrides in [dict(template_approved=False), dict(recipient_opted_in=False), dict(enabled=False)]:
        with pytest.raises(AlertNotAuthorised):
            prepare_queued_template(plan_scan("malicious", quarantined=True), _config(**overrides), "event-3")


def test_queued_template_contains_no_case_or_evidence_details():
    body = prepare_queued_template(plan_scan("malicious", quarantined=True), _config(), "opaque-123")
    assert body["type"] == "template"
    assert body["filterBlocked"] and body["filterUnsubscribed"]
    assert body["externalId"] == "opaque-123"
    assert "components" not in body["template"]
    assert not any(key in body for key in ("text", "image", "document", "case_id", "content"))


def test_blocks_untrusted_identifiers_and_address_values():
    for config, event_id in [
        (_config(template_name="../private"), "event-4"),
        (_config(sender_e164="admin@example.com"), "event-5"),
        (_config(), "CASE RAW PATH /etc/shadow"),
    ]:
        with pytest.raises(AlertNotAuthorised):
            prepare_queued_template(plan_scan("malicious", quarantined=True), config, event_id)


def test_automation_is_advisory_not_live_execution():
    plan = plan_scan("malicious", quarantined=False)
    assert plan.review_required
    assert plan.as_dict() == {
        "disposition": "isolate_and_review", "review_required": True,
        "priority": "urgent", "allow_automatic_release": False,
        "dynamic_execution_enabled": False,
    }

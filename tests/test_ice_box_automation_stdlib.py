"""Isolated no-network checks for IceBox, runnable without PyPI dependencies."""

from __future__ import annotations

import unittest

from integrations.icebox_ycloud.alerts import (
    AlertNotAuthorised,
    YCloudAlertConfig,
    prepare_queued_template,
)
from src.security.ice_box.automation_policy import plan_scan


class IceBoxAutomationTests(unittest.TestCase):
    def test_clean_non_quarantined_is_only_static_allow(self):
        plan = plan_scan("clean", quarantined=False)
        self.assertEqual(plan.disposition, "allow_static")
        self.assertFalse(plan.review_required)
        self.assertFalse(plan.dynamic_execution_enabled)

    def test_malicious_requires_urgent_review_not_release(self):
        plan = plan_scan("malicious", quarantined=False)
        self.assertEqual(plan.priority, "urgent")
        self.assertFalse(plan.allow_automatic_release)
        self.assertTrue(plan.review_required)

    def test_unknown_verdict_is_never_automatically_cleared(self):
        self.assertEqual(
            plan_scan("unknown-next-version", quarantined=False).disposition,
            "hold_for_review",
        )

    def test_clean_when_already_quarantined_stays_on_hold(self):
        self.assertEqual(plan_scan("clean", quarantined=True).disposition, "hold_for_review")

    def test_malformed_state_is_rejected(self):
        with self.assertRaises(TypeError):
            plan_scan("clean", quarantined=None)

    def test_external_notification_is_off_by_default(self):
        with self.assertRaises(AlertNotAuthorised):
            prepare_queued_template(
                plan_scan("malicious", quarantined=True), YCloudAlertConfig(), "opaque1"
            )

    def test_approved_mock_template_is_static_and_non_sending(self):
        config = YCloudAlertConfig(
            enabled=True,
            recipient_opted_in=True,
            template_approved=True,
            sender_e164="+447911123456",
            recipient_e164="+447911654321",
            template_name="icebox_static_alert",
            language_code="en_GB",
        )
        request = prepare_queued_template(
            plan_scan("malicious", quarantined=True), config, "opaque1"
        )
        self.assertEqual(request["type"], "template")
        self.assertTrue(request["filterBlocked"])
        self.assertTrue(request["filterUnsubscribed"])
        self.assertNotIn("components", request["template"])
        self.assertNotIn("text", request)
        self.assertNotIn("content", request)


if __name__ == "__main__":
    unittest.main()

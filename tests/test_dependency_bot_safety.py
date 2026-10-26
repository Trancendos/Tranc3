"""Regression tests for fail-closed dependency bot governance."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.check_dependency_bot_safety import issues

ROOT = Path(__file__).resolve().parents[1]


class DependencyBotSafetyTests(unittest.TestCase):
    def setUp(self):
        self.good = {
            "vulnerabilityAlerts": {"enabled": True, "automerge": False},
            "packageRules": [
                {"automerge": True, "matchPackageNames": ["other"]},
                {
                    "matchPackageNames": ["/^opentelemetry-/"],
                    "matchDatasources": ["pypi"],
                    "groupName": "OpenTelemetry coordinated upgrades",
                    "automerge": False,
                },
            ],
        }

    def test_safe_configuration(self):
        self.assertEqual(issues(self.good), [])

    def test_vulnerability_auto_merge_is_rejected(self):
        config = copy.deepcopy(self.good)
        config["vulnerabilityAlerts"]["automerge"] = True
        self.assertTrue(issues(config))

    def test_disabled_security_alerts_are_rejected(self):
        config = copy.deepcopy(self.good)
        config["vulnerabilityAlerts"]["enabled"] = False
        self.assertTrue(issues(config))

    def test_later_override_is_rejected(self):
        config = copy.deepcopy(self.good)
        config["packageRules"].append(
            {"matchPackageNames": ["/^opentelemetry-/"], "automerge": True}
        )
        self.assertTrue(issues(config))

    def test_unrelated_or_unscoped_last_rule_is_rejected(self):
        config = copy.deepcopy(self.good)
        config["packageRules"][-1]["matchDatasources"] = ["docker"]
        self.assertTrue(issues(config))

    def test_malformed_config_fails_closed(self):
        self.assertTrue(issues([]))
        self.assertTrue(issues({}))
        bad = copy.deepcopy(self.good)
        bad["packageRules"][-1]["matchPackageNames"] = None
        self.assertTrue(issues(bad))

    def test_security_manifest_has_independent_fail_closed_preflight(self):
        workflow = (ROOT / ".github/workflows/dependency-preflight.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("  security-resolver:", workflow)
        self.assertIn("name: Security toolchain resolution", workflow)
        self.assertIn(
            "if ! python -m pip install --dry-run --ignore-installed "
            "--disable-pip-version-check -r requirements-security.txt",
            workflow,
        )
        self.assertIn("Security toolchain requirements resolved", workflow)

    def test_repository_config_is_safe(self):
        config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
        self.assertEqual(issues(config), [])


if __name__ == "__main__":
    unittest.main()

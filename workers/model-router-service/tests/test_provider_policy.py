"""Regression tests for Luminous admission policy."""

import importlib.util
import unittest
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "provider_policy.py"
spec = importlib.util.spec_from_file_location("provider_policy", module_path)
import sys

module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
PolicyDenied, RouteCandidate, RoutePolicy, admit = (
    module.PolicyDenied,
    module.RouteCandidate,
    module.RoutePolicy,
    module.admit,
)


class ProviderPolicyTests(unittest.TestCase):
    def setUp(self):
        self.local = RouteCandidate("ollama", "llama3.1:8b", False, True, True)
        self.policy = RoutePolicy(frozenset({"ollama"}), frozenset({"llama3.1:8b"}))

    def test_local_allowed(self):
        self.assertIsNone(admit(self.local, self.policy, classification="public"))

    def test_unknown_provider_denied(self):
        with self.assertRaises(PolicyDenied):
            admit(
                RouteCandidate("unknown", self.local.model, False, True, True),
                self.policy,
                classification="public",
            )

    def test_external_denied_default(self):
        p = RoutePolicy(frozenset({"openrouter"}), frozenset({"a:free"}))
        with self.assertRaises(PolicyDenied):
            admit(
                RouteCandidate("openrouter", "a:free", True, True, True), p, classification="public"
            )

    def test_unverified_free_price_denied(self):
        with self.assertRaises(PolicyDenied):
            admit(
                RouteCandidate("ollama", self.local.model, False, True, False),
                self.policy,
                classification="public",
            )

    def test_paid_denied_default(self):
        with self.assertRaises(PolicyDenied):
            admit(
                RouteCandidate("ollama", self.local.model, False, False, True),
                self.policy,
                classification="public",
            )

    def test_classification_denied(self):
        with self.assertRaises(PolicyDenied):
            admit(self.local, self.policy, classification="restricted")

    def test_paid_external_requires_explicit_permission(self):
        p = RoutePolicy(frozenset({"openrouter"}), frozenset({"paid/model"}), True, True)
        self.assertIsNone(
            admit(
                RouteCandidate("openrouter", "paid/model", True, False, True),
                p,
                classification="public",
            )
        )

    def test_unknown_model_denied(self):
        with self.assertRaises(PolicyDenied):
            admit(
                RouteCandidate("ollama", "not-registered", False, True, True),
                self.policy,
                classification="public",
            )


if __name__ == "__main__":
    unittest.main()

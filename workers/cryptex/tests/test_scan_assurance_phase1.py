"""Offline regression tests for Cryptex scan assurance and adaptive routing.

No network requests, credentials, target scanning, or infrastructure mutations.
Run: PYTHONPATH=workers/cryptex python -m unittest discover -s workers/cryptex/tests
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from cryptex_assurance import Assessment, assess_engine_output
from cryptex_capabilities import compatible_engines
from models import ScanRequest, ScanStatus, ScanType
from service import OpenVASEngine, SecurityEngineRouter, YARAEngine


class FakeDatabase:
    def __init__(self):
        self.results = []

    def lookup_indicator(self, target):
        return None

    def save_result(self, result):
        self.results.append(result.model_copy(deep=True))
        return result


class FakeEngine:
    def __init__(self, output):
        self.output = output

    async def scan(self, request):
        return self.output


class ScanAssuranceTest(unittest.TestCase):
    def test_offline_is_inconclusive_even_with_negative_flag(self):
        result = assess_engine_output("offline", {"threat_found": False})
        self.assertEqual(result.assessment, Assessment.INCONCLUSIVE)
        self.assertFalse(result.coverage_confirmed)

    def test_explicit_not_performed_is_inconclusive(self):
        result = assess_engine_output("openvas", {"threat_found": False, "scan_performed": False})
        self.assertEqual(result.assessment, Assessment.INCONCLUSIVE)

    def test_missing_threat_flag_is_inconclusive(self):
        self.assertEqual(assess_engine_output("clamav", {}).assessment, Assessment.INCONCLUSIVE)

    def test_actual_negative_detector_is_clean(self):
        self.assertEqual(assess_engine_output("clamav", {"threat_found": False}).assessment, Assessment.CLEAN)

    def test_incompatible_engine_does_not_make_network_scan_clean(self):
        self.assertEqual(
            compatible_engines("network", ["misp", "wazuh", "openvas", "offline"]),
            ["openvas", "offline"],
        )

    def test_sast_only_routes_to_semgrep(self):
        self.assertEqual(compatible_engines("sast", ["yara", "semgrep", "offline"]), ["semgrep", "offline"])


class ScanRouterIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_stub_does_not_report_scan_completed(self):
        db = FakeDatabase()
        router = SecurityEngineRouter(db)
        with patch.object(config, "FORCE_ENGINE", "offline"):
            result = await router.scan(ScanRequest(scan_type=ScanType.file, target="synthetic-file"))
        self.assertEqual(result.status, ScanStatus.inconclusive)
        self.assertFalse(result.threat_found)
        self.assertEqual(result.engine_used, "offline")
        self.assertEqual(db.results[-1].status, ScanStatus.inconclusive)

    async def test_working_detector_can_report_clean(self):
        db = FakeDatabase()
        router = SecurityEngineRouter(db)
        router._engines["clamav"] = FakeEngine({"threat_found": False, "severity": "info", "findings": []})
        router._available_engines = lambda preferred=None: ["clamav", "offline"]
        with patch.object(config, "FORCE_ENGINE", ""):
            result = await router.scan(ScanRequest(scan_type=ScanType.file, target="synthetic-file"))
        self.assertEqual(result.status, ScanStatus.completed)
        self.assertFalse(result.threat_found)
        self.assertEqual(result.engine_used, "clamav")

    async def test_deferred_vulnerability_scan_remains_inconclusive(self):
        db = FakeDatabase()
        router = SecurityEngineRouter(db)
        router._engines["openvas"] = FakeEngine({
            "threat_found": False, "severity": "info",
            "findings": [{"type": "vulnerability_scan_triggered"}],
            "scan_performed": False,
        })
        router._available_engines = lambda preferred=None: ["openvas", "offline"]
        with patch.object(config, "FORCE_ENGINE", ""):
            result = await router.scan(ScanRequest(scan_type=ScanType.vulnerability, target="synthetic-host"))
        self.assertEqual(result.status, ScanStatus.inconclusive)
        self.assertEqual(result.engine_used, "openvas")
        self.assertEqual(result.findings[0]["type"], "vulnerability_scan_triggered")
        self.assertTrue(router._health["openvas"], "Deferred work is not an engine health failure")

    async def test_no_yara_rules_mean_no_assurance(self):
        with tempfile.TemporaryDirectory() as rules_dir:
            with patch.object(config, "YARA_RULES_DIR", rules_dir):
                with patch.dict(sys.modules, {"yara": types.ModuleType("yara")}):
                    output = await YARAEngine().scan(
                        ScanRequest(scan_type=ScanType.file, target="synthetic-file")
                    )
        self.assertFalse(output["scan_performed"])

    async def test_openvas_target_creation_is_not_scan_completion(self):
        class FakeResponse:
            text = '<create_target_response status="201" />'
            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None
            async def post(self, *args, **kwargs):
                return FakeResponse()

        with patch("service.httpx.AsyncClient", FakeClient):
            output = await OpenVASEngine().scan(
                ScanRequest(scan_type=ScanType.vulnerability, target="synthetic-host")
            )
        self.assertFalse(output["scan_performed"])
        self.assertEqual(output["findings"][0]["type"], "vulnerability_scan_triggered")


if __name__ == "__main__":
    unittest.main()

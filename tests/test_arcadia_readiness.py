"""Contract tests for the opt-in Arcadia readiness audit (stdlib-only)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "arcadia_readiness.py"
spec = importlib.util.spec_from_file_location("arcadia_readiness", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ArcadiaReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'web').mkdir()
        (self.root / 'web/src').mkdir()
        (self.root / 'web/src/AppRouter.tsx').write_text('export function AppRouter() {}', encoding='utf-8')
        for name, port in [('orders-service', 8012), ('payments-service', 8013), ('products-service', 8011)]:
            parent = self.root / 'workers' / name
            parent.mkdir(parents=True)
            (parent / 'worker.py').write_text(
                f'''WORKER_PORT = int(os.getenv("PORT") or "{port}")\n'''
                'async def require_internal_auth(): pass\n'
                '_router = APIRouter(dependencies=[Depends(require_internal_auth)])\n'
                '@_router.get("/listings")\nasync def browse(): pass\n', encoding='utf-8'
            )

    def test_valid_source_map_has_expected_ports_and_guard(self):
        result = audit.inspect(self.root)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['services']['exchange']['configured_port'], 8012)
        self.assertEqual(result['services']['bank']['configured_port'], 8013)
        self.assertEqual(result['services']['catalogue']['configured_port'], 8011)
        self.assertTrue(result['services']['exchange']['internal_auth_router_detected'])
        self.assertTrue(result['portal']['source_present'])

    def test_missing_worker_is_reported_and_strict_mode_fails(self):
        (self.root / 'workers/orders-service/worker.py').unlink()
        result = audit.inspect(self.root)
        self.assertIn('missing_source:exchange', result['findings'])
        self.assertFalse(result['services']['exchange']['source_present'])
        self.assertEqual(audit.strict_exit_code(result), 2)

    def test_monetary_float_and_wildcard_cors_are_flagged(self):
        p = self.root / 'workers/payments-service/worker.py'
        p.write_text(p.read_text(encoding='utf-8') + '\namount: float\nbalance REAL\nCORS_ORIGINS", "*"\n', encoding='utf-8')
        result = audit.inspect(self.root)
        self.assertIn('monetary_float_detected:bank', result['findings'])
        self.assertIn('wildcard_cors_default:bank', result['findings'])

    def test_missing_auth_router_is_flagged(self):
        p = self.root / 'workers/products-service/worker.py'
        p.write_text('@app.post("/products")\nasync def create(): pass\n', encoding='utf-8')
        result = audit.inspect(self.root)
        self.assertIn('protected_router_not_detected:catalogue', result['findings'])

    def test_json_output_has_no_tokens_or_private_data(self):
        report = json.dumps(audit.inspect(self.root), sort_keys=True)
        self.assertNotIn('INTERNAL_SECRET=', report)
        self.assertNotIn(str(self.root), report)
        self.assertEqual(audit.strict_exit_code(audit.inspect(self.root)), 0)


if __name__ == '__main__':
    unittest.main()

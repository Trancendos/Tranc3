"""Regression tests for the Workshop privileged-runner CI boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_workshop_runner_guard import audit


class WorkshopRunnerGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workflows = self.root / ".forgejo/workflows"
        self.workflows.mkdir(parents=True)
        self.runner_config = self.root / "deploy/forgejo/act-runner-deploy.yml"
        self.runner_config.parent.mkdir(parents=True)
        self.runner_config.write_text('runner:\n  labels: ["deploy-host:host"]\n', encoding="utf-8")

    def write_workflow(
        self,
        guard="github.ref == 'refs/heads/main'",
        event="push",
        runner="deploy-host",
    ):
        self.workflows.joinpath("build.yml").write_text(
            f"name: build\non:\n  {event}:\n    branches: [main]\n"
            f"jobs:\n  build:\n    runs-on: {runner}\n"
            f"    if: {guard}\n    steps:\n      - run: echo ok\n",
            encoding="utf-8",
        )

    def codes(self):
        return {item["code"] for item in audit(self.root)["findings"]}

    def test_main_guarded_deploy_job_passes(self):
        self.write_workflow()
        self.assertEqual(self.codes(), set())
        self.assertEqual(audit(self.root)["privileged_jobs"], 1)

    def test_refuses_missing_guard(self):
        self.write_workflow()
        path = self.workflows / "build.yml"
        path.write_text(
            path.read_text().replace("    if: github.ref == 'refs/heads/main'\n", ""),
            encoding="utf-8",
        )
        self.assertIn("MISSING_MAIN_GUARD", self.codes())

    def test_refuses_or_true_guard_bypass(self):
        self.write_workflow(guard="github.ref == 'refs/heads/main' || true")
        self.assertIn("MISSING_MAIN_GUARD", self.codes())

    def test_refuses_pull_request_target(self):
        self.write_workflow(event="pull_request_target")
        self.assertIn("UNTRUSTED_TRIGGER", self.codes())

    def test_refuses_repository_dispatch(self):
        self.write_workflow(event="repository_dispatch")
        self.assertIn("UNTRUSTED_TRIGGER", self.codes())

    def test_refuses_missing_workflow_trigger(self):
        self.write_workflow()
        path = self.workflows / "build.yml"
        path.write_text(
            path.read_text().replace("on:\n  push:\n    branches: [main]\n", ""),
            encoding="utf-8",
        )
        self.assertIn("MISSING_TRIGGER", self.codes())

    def test_refuses_workflow_run(self):
        self.write_workflow(event="workflow_run")
        self.assertIn("UNTRUSTED_TRIGGER", self.codes())

    def test_allows_main_guard_in_regular_pull_request_workflow(self):
        self.write_workflow(event="pull_request")
        self.assertEqual(self.codes(), set())

    def test_refuses_dynamic_deploy_host_selector(self):
        expression = '"' + chr(36) + "{{ inputs.runner || 'deploy-host' }}" + '"'
        self.write_workflow(runner=expression)
        self.assertIn("DYNAMIC_RUNNER", self.codes())

    def test_refuses_missing_privileged_runner_config(self):
        self.write_workflow()
        self.runner_config.unlink()
        self.assertIn("RUNNER_CONFIG", self.codes())

    def test_refuses_malformed_workflow_yaml(self):
        (self.workflows / "bad.yml").write_text("jobs: [\n", encoding="utf-8")
        self.assertIn("INVALID_WORKFLOW", self.codes())

    def test_refuses_missing_workflow_directory(self):
        self.workflows.rmdir()
        self.assertIn("MISSING_WORKFLOWS", self.codes())
        self.assertIn("NO_WORKFLOWS", self.codes())

    def test_cli_outputs_json_and_exit_code(self):
        self.write_workflow()
        script = Path(__file__).parents[1] / "scripts/check_workshop_runner_guard.py"
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(self.root), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["privileged_jobs"], 1)


if __name__ == "__main__":
    unittest.main()

"""Regression checks for The Chaos Party's CI evidence and failure semantics."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_test_suite_fails_closed_on_install_and_pytest_errors():
    workflow_text = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["test"]["steps"]
    install = next(step for step in steps if step.get("name") == "Install dependencies")
    run = next(step for step in steps if step.get("name") == "Run full test suite")
    assert "|| true" not in install["run"]
    assert "|| true" not in run["run"]
    assert "pytest tests/" in run["run"]
    assert "continue-on-error" not in install
    assert "continue-on-error" not in run


def test_test_suite_reports_failures_even_when_pytest_fails():
    workflow = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    report = next(s for s in steps if s.get("name") == "Report test run to The Chaos Party")
    assert report.get("if") == "always()"
    assert "CHAOS_PARTY_URL" in report["env"]
    assert "INTERNAL_SECRET" in report["env"]
    coverage = next(s for s in steps if s.get("name") == "Upload coverage")
    assert coverage.get("if") == "always()"


def test_otel_api_pin_matches_sdk():
    req = (ROOT / "requirements.txt").read_text()
    pins = {}
    for line in req.splitlines():
        if line.startswith(("opentelemetry-api==", "opentelemetry-sdk==")):
            key, value = line.split("==", 1)
            pins[key] = value
    assert pins["opentelemetry-api"] == pins["opentelemetry-sdk"]


def test_chaos_contract_workflow_is_pull_request_gated():
    workflow = yaml.safe_load((ROOT / ".github/workflows/chaos-party-contract.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert "pull_request" in triggers
    job = workflow["jobs"]["chaos-party-contract"]
    command = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "tests/test_flow_wiring.py" in command
    assert "tests/test_chaos_ci_contract.py" in command
    assert "tests/test_chaos_experiment_safety.py" in command
    assert "|| true" not in command

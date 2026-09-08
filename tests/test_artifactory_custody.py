"""Safety properties for the Artifactory three-base custody ledger."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.fixture
def worker_module(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERNAL_SECRET", "test-artifactory-internal-secret")
    monkeypatch.setenv("ARTIFACT_CUSTODY_DB", str(tmp_path / "default-custody.db"))
    module_name = f"artifactory_worker_{tmp_path.name}"
    worker_path = Path(__file__).parents[1] / "workers" / "artifactory-service" / "worker.py"
    spec = importlib.util.spec_from_file_location(module_name, worker_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)


def external_request(worker_module):
    return worker_module.ExternalArtifactIntake(
        name="example-package.whl",
        sha256="a" * 64,
        artifact_type="python-wheel",
        submitted_by="external-supplier",
        source_reference="supplier-release-2026-09",
    )


def test_external_artifact_requires_clean_ice_box_evidence_before_store(worker_module, tmp_path):
    ledger = worker_module.ArtifactCustodyLedger(tmp_path / "custody.db")
    record = ledger.register_external(external_request(worker_module))
    assert (record["base"], record["hold"], record["status"]) == (
        "external",
        "incomer",
        "received",
    )

    with pytest.raises(ValueError):
        ledger.store_external(record["id"])

    record = ledger.move_to_ice_box(record["id"])
    assert (record["hold"], record["status"]) == ("ice-box", "awaiting_scan")

    record = ledger.record_scan(
        record["id"],
        worker_module.ScanEvidence(
            scanner="cryptex",
            scan_reference="scan-001",
            disposition="suspicious",
        ),
    )
    assert (record["hold"], record["status"]) == ("ice-box", "quarantined")
    with pytest.raises(ValueError):
        ledger.store_external(record["id"])


def test_clean_external_artifact_can_reach_hold_three(worker_module, tmp_path):
    ledger = worker_module.ArtifactCustodyLedger(tmp_path / "custody.db")
    record = ledger.move_to_ice_box(ledger.register_external(external_request(worker_module))["id"])
    record = ledger.record_scan(
        record["id"],
        worker_module.ScanEvidence(
            scanner="ice-box-adapter",
            scan_reference="scan-002",
            disposition="clean",
        ),
    )
    record = ledger.store_external(record["id"])
    assert (record["base"], record["hold"], record["status"]) == (
        "external",
        "store",
        "admitted",
    )


def test_internal_user_promotion_requires_evidence_and_think_tank_review(worker_module, tmp_path):
    ledger = worker_module.ArtifactCustodyLedger(tmp_path / "custody.db")
    record = ledger.register_internal_user(
        worker_module.InternalUserArtifact(
            name="user-component",
            sha256="b" * 64,
            artifact_type="node-package",
            owner_id="user-123",
        )
    )
    with pytest.raises(ValueError):
        ledger.record_think_tank_review(
            record["id"],
            worker_module.ThinkTankReview(
                reviewer="think-tank", decision="approved", notes="ready"
            ),
        )

    record = ledger.promote_to_internal_admin(
        record["id"],
        worker_module.InternalPromotionEvidence(
            assessor="value-assessor",
            assessment_reference="assessment-001",
            rationale="The component has a reusable interface and clear test evidence.",
        ),
    )
    assert (record["base"], record["status"]) == ("internal-admin", "think-tank-review")

    record = ledger.record_think_tank_review(
        record["id"],
        worker_module.ThinkTankReview(reviewer="think-tank", decision="approved", notes="approved"),
    )
    assert record["status"] == "available"


def test_custody_api_rejects_artifact_bytes(worker_module):
    client = TestClient(worker_module.app)
    response = client.post(
        "/artifactory/custody/external",
        headers={"X-Internal-Secret": "test-artifactory-internal-secret"},
        json={
            "name": "untrusted.zip",
            "sha256": "c" * 64,
            "artifact_type": "zip",
            "submitted_by": "supplier",
            "source_reference": "supplier-release",
            "content": "raw bytes do not belong in the custody ledger",
        },
    )
    assert response.status_code == 422


def test_custody_models_require_a_sha256_digest(worker_module):
    with pytest.raises(ValidationError):
        worker_module.ExternalArtifactIntake(
            name="artifact",
            sha256="not-a-digest",
            submitted_by="supplier",
            source_reference="source",
        )

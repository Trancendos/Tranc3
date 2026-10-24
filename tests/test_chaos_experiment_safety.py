"""PID-TCP: opt-in, bounded, isolated chaos simulations only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._worker_import_utils import import_worker

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "workers" / "chaos-party" / "worker.py"
SECRET = "unit-test-chaos-internal-secret-not-a-production-key"
APPROVAL = "independent-approval-token-for-ci-only"


@pytest.fixture
def party(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", SECRET)
    monkeypatch.setenv("CHAOS_ENVIRONMENT", "staging")
    monkeypatch.setenv("CHAOS_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("CHAOS_APPROVAL_TOKEN", APPROVAL)
    worker = import_worker("chaos_party_safety_contract_worker", WORKER)
    monkeypatch.setattr(worker, "DB_PATH", tmp_path / "chaos.db")
    worker.init_db()
    return worker


async def create(party, *, target="local-sandbox", kind="latency_injection", config=None):
    return await party.create_chaos_experiment(
        party.ChaosExperimentIn(
            name="bounded-probe",
            target_service=target,
            experiment_type=kind,
            config=config if config is not None else {"delay_ms": 1, "ttl_seconds": 1},
        ),
        x_internal_secret=SECRET,
    )


@pytest.mark.asyncio
async def test_disabled_experiment_never_enters_running(party, monkeypatch):
    experiment = await create(party)
    monkeypatch.setenv("CHAOS_EXECUTION_ENABLED", "false")
    with pytest.raises(party.HTTPException) as exc:
        await party.run_chaos(experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL)
    assert exc.value.status_code == 403
    with party.get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM chaos_experiments WHERE id=?", (experiment["id"],)
        ).fetchone()
    assert row["status"] == "idle"


@pytest.mark.asyncio
async def test_live_or_unknown_targets_are_denied(party):
    for target in ("api-service", "http://127.0.0.1", "production", ""):
        experiment = await create(party, target=target)
        with pytest.raises(party.HTTPException) as exc:
            await party.run_chaos(
                experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_requires_independent_approval_and_staging(party, monkeypatch):
    experiment = await create(party)
    with pytest.raises(party.HTTPException) as exc:
        await party.run_chaos(experiment["id"], x_internal_secret=SECRET, x_chaos_approval="wrong")
    assert exc.value.status_code == 403
    monkeypatch.setenv("CHAOS_ENVIRONMENT", "production")
    with pytest.raises(party.HTTPException) as exc:
        await party.run_chaos(experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_bounded_latency_simulation_completes_with_audit_evidence(party):
    experiment = await create(party, config={"delay_ms": 1, "ttl_seconds": 1})
    result = await party.run_chaos(
        experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL
    )
    assert result["status"] == "completed"
    assert result["results"]["mode"] == "isolated_simulation"
    assert result["results"]["target"] == "local-sandbox"
    assert result["results"]["injected_latency_ms"] == 1
    with party.get_conn() as conn:
        row = conn.execute(
            "SELECT status, ended_at, results FROM chaos_experiments WHERE id=?",
            (experiment["id"],),
        ).fetchone()
    assert row["status"] == "completed"
    assert row["ended_at"] is not None
    assert json.loads(row["results"])["mode"] == "isolated_simulation"
    with pytest.raises(party.HTTPException) as exc:
        await party.run_chaos(experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_error_injection_is_synthetic_and_never_contacts_a_target(party):
    experiment = await create(party, kind="error_injection", config={"ttl_seconds": 1})
    result = await party.run_chaos(
        experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL
    )
    assert result["status"] == "completed"
    assert result["results"]["synthetic_http_status"] == 500
    assert result["results"]["target"] == "local-sandbox"


@pytest.mark.asyncio
async def test_unsupported_or_unbounded_injection_is_rejected_before_state_change(party):
    cases = [
        ("cpu_spike", {"ttl_seconds": 1}),
        ("memory_pressure", {"ttl_seconds": 1}),
        ("latency_injection", {"delay_ms": 99999, "ttl_seconds": 1}),
        ("latency_injection", {"delay_ms": 1, "ttl_seconds": 1000}),
    ]
    for kind, config in cases:
        experiment = await create(party, kind=kind, config=config)
        with pytest.raises(party.HTTPException) as exc:
            await party.run_chaos(
                experiment["id"], x_internal_secret=SECRET, x_chaos_approval=APPROVAL
            )
        assert exc.value.status_code in (400, 403)
        with party.get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM chaos_experiments WHERE id=?", (experiment["id"],)
            ).fetchone()
        assert row["status"] == "idle"

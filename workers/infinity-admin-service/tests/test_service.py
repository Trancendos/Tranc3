"""
Infinity-Admin Service — Service Layer Tests
=============================================
Unit tests for business-logic helpers in service.py.
These tests do NOT require the Dimensional package or a running server.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# log_admin_action
# ---------------------------------------------------------------------------


def test_log_admin_action_basic(tmp_db):
    """log_admin_action should persist a row to admin_actions."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.log_admin_action(
            action_type="test_action",
            actor_id="user-123",
            actor_username="tester",
            target_type="config",
            target_id="some_key",
            details={"value": "x"},
        )
    finally:
        service.db = _orig_db

    row = tmp_db.execute("SELECT * FROM admin_actions WHERE actor_id = ?", ("user-123",)).fetchone()
    assert row is not None
    assert row["action_type"] == "test_action"
    assert row["actor_username"] == "tester"
    assert json.loads(row["details"])["value"] == "x"


def test_log_admin_action_no_details(tmp_db):
    """log_admin_action should handle None details gracefully."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.log_admin_action(
            action_type="noop",
            actor_id="system",
        )
    finally:
        service.db = _orig_db

    row = tmp_db.execute(
        "SELECT details FROM admin_actions WHERE actor_id = ?", ("system",)
    ).fetchone()
    assert row is not None
    assert row["details"] == "{}"


# ---------------------------------------------------------------------------
# upsert_override
# ---------------------------------------------------------------------------


def test_upsert_override_insert(tmp_db):
    """upsert_override should insert a new record."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.upsert_override("pid-01", "location", None, "Old Name", "New Name", "admin")
    finally:
        service.db = _orig_db

    row = tmp_db.execute(
        "SELECT override_name FROM entity_overrides WHERE location_pid = ?", ("pid-01",)
    ).fetchone()
    assert row is not None
    assert row["override_name"] == "New Name"


def test_upsert_override_update(tmp_db):
    """upsert_override should update an existing record (ON CONFLICT)."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.upsert_override("pid-02", "lead_ai", None, "Original", "First Update", "admin")
        service.upsert_override("pid-02", "lead_ai", None, "Original", "Second Update", "admin")
    finally:
        service.db = _orig_db

    rows = tmp_db.execute(
        "SELECT override_name FROM entity_overrides WHERE location_pid = ?", ("pid-02",)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["override_name"] == "Second Update"


def test_upsert_override_slot_sentinel(tmp_db):
    """upsert_override should store '' (not NULL) for no-slot rows."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.upsert_override("pid-03", "location", None, "Orig", "Override", "admin")
    finally:
        service.db = _orig_db

    row = tmp_db.execute(
        "SELECT slot FROM entity_overrides WHERE location_pid = ?", ("pid-03",)
    ).fetchone()
    assert row["slot"] == ""


# ---------------------------------------------------------------------------
# seed_default_config
# ---------------------------------------------------------------------------


def test_seed_default_config_idempotent(tmp_db):
    """seed_default_config should not duplicate rows on repeated calls."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.seed_default_config("TestEco", "TestUni")
        service.seed_default_config("TestEco", "TestUni")
    finally:
        service.db = _orig_db

    count = tmp_db.execute(
        "SELECT COUNT(*) as cnt FROM system_config WHERE key = 'ecosystem_name'"
    ).fetchone()["cnt"]
    assert count == 1


def test_seed_default_config_values(tmp_db):
    """seed_default_config should seed the expected keys."""
    import service

    _orig_db = service.db
    service.db = tmp_db

    try:
        service.seed_default_config("Infinity", "Trancendos")
    finally:
        service.db = _orig_db

    row = tmp_db.execute("SELECT value FROM system_config WHERE key = 'ecosystem_name'").fetchone()
    assert row["value"] == "Infinity"

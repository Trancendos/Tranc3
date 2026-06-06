"""The Town Hall — governance, frameworks, rooms, documents, kanban, ITSM."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("JWT_SECRET", "test-jwt-not-for-prod")


@pytest.fixture(autouse=True)
def _reset_townhall_singletons():
    import src.townhall.framework_registry as fr
    import src.townhall.governance as gov

    gov._townhall = None
    fr._registry = None
    yield
    gov._townhall = None
    fr._registry = None


def test_framework_registry_loads_domains():
    from src.townhall.framework_registry import get_framework_registry

    reg = get_framework_registry()
    domains = reg.by_domain()
    assert "governance" in domains
    assert "agile" in domains
    assert "itsm" in domains
    assert len(reg.rooms) >= 3


def test_townhall_policies_include_registry():
    from src.townhall.governance import get_townhall

    th = get_townhall()
    assert th.get("kanban") is not None
    assert th.get("foundation-framework") is not None
    st = th.status()
    assert st["registry"]["framework_count"] > 10


def test_zero_cost_check():
    from src.townhall.governance import ComplianceResult, get_townhall

    results = get_townhall().check({"monthly_cost_usd": 0}, policy_ids=["zero-cost"])
    assert results["zero-cost"] == ComplianceResult.PASS


def test_document_render_add():
    from src.townhall.documents import render_template

    text = render_template(
        "add",
        {
            "system_name": "test",
            "author": "Tristuran",
            "version": "0.1",
            "date": "2026-05-31",
            "context": "unit test",
        },
    )
    assert "Architectural Design Document" in text
    assert "test" in text


def test_kanban_move_card():
    from src.townhall.agile import KanbanColumn, get_kanban_service

    board = get_kanban_service().get_board("default")
    assert board is not None
    card = board.add_card("Ship Town Hall API", column=KanbanColumn.TODO)
    moved = board.move_card(card.id, KanbanColumn.DONE)
    assert moved is not None
    assert moved.column == KanbanColumn.DONE


def test_war_room_session():
    from src.townhall.rooms import RoomKind, get_room_manager

    rm = get_room_manager()
    session = rm.open_session(RoomKind.WAR_ROOM, "P0 deploy", chair="Tristuran")
    assert session.active
    ended = rm.end_session(session.id)
    assert ended is not None
    assert ended.ended_at is not None


@pytest.mark.asyncio
async def test_townhall_routes():
    from fastapi.testclient import TestClient

    import api

    client = TestClient(api.app)
    r = client.get("/townhall/status")
    assert r.status_code == 200
    body = r.json()
    assert "registry" in body
    assert body["kanban_boards"] >= 1

    r2 = client.get("/townhall/frameworks")
    assert r2.status_code == 200
    assert "domains" in r2.json()

    r3 = client.get("/townhall/documents/templates")
    assert r3.status_code == 200
    assert len(r3.json()["templates"]) >= 10

# tests/test_notebooks.py
# Tests for src/notebooks/registry.py — the Notebook Registry
# (personal, freeform notes for AIs and Agents).

from __future__ import annotations

import pytest

from src.notebooks.registry import VISIBILITY_VALUES, NotebookRegistry, validate_visibility


@pytest.fixture
def registry(tmp_path):
    db_path = tmp_path / "notebook_registry_test.db"
    reg = NotebookRegistry(db_path=db_path)
    yield reg
    reg.close()


class TestValidateVisibility:
    def test_accepts_known_values(self):
        for value in VISIBILITY_VALUES:
            assert validate_visibility(value) == value

    def test_rejects_unknown_value(self):
        with pytest.raises(ValueError):
            validate_visibility("private")


class TestCreateEntry:
    def test_create_returns_populated_entry(self, registry):
        entry = registry.create_entry(owner="The Nexus", content="First note")
        assert entry.id is not None
        assert entry.owner == "The Nexus"
        assert entry.content == "First note"
        assert entry.visibility == "ai_private"
        assert entry.linked_card_id is None
        assert entry.linked_location is None

    def test_create_with_explicit_visibility(self, registry):
        entry = registry.create_entry(owner="The Nexus", content="Public note", visibility="public")
        assert entry.visibility == "public"

    def test_create_with_links(self, registry):
        entry = registry.create_entry(
            owner="The Nexus",
            content="Linked note",
            linked_card_id="card-123",
            linked_location="The Nexus",
        )
        assert entry.linked_card_id == "card-123"
        assert entry.linked_location == "The Nexus"

    def test_blank_owner_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(owner="", content="Note")
        with pytest.raises(ValueError):
            registry.create_entry(owner="   ", content="Note")

    def test_blank_content_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(owner="The Nexus", content="")
        with pytest.raises(ValueError):
            registry.create_entry(owner="The Nexus", content="   ")

    def test_unsafe_owner_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(owner="<script>alert(1)</script>", content="Note")

    def test_unsafe_content_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(owner="The Nexus", content="<script>alert(1)</script>")

    def test_unsafe_linked_card_id_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(
                owner="The Nexus",
                content="Note",
                linked_card_id="<script>alert(1)</script>",
            )

    def test_unsafe_linked_location_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(
                owner="The Nexus",
                content="Note",
                linked_location="<script>alert(1)</script>",
            )

    def test_invalid_visibility_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.create_entry(owner="The Nexus", content="Note", visibility="private")


class TestGetEntry:
    def test_get_known_entry(self, registry):
        created = registry.create_entry(owner="The Nexus", content="Note")
        fetched = registry.get_entry(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.content == "Note"

    def test_get_unknown_entry_returns_none(self, registry):
        assert registry.get_entry(999999) is None


class TestListForOwner:
    def test_empty_for_unknown_owner(self, registry):
        assert registry.list_for_owner("Nobody") == []

    def test_lists_only_that_owners_entries(self, registry):
        registry.create_entry(owner="The Nexus", content="Nexus note")
        registry.create_entry(owner="Tyler Towncroft", content="Grid note")
        entries = registry.list_for_owner("The Nexus")
        assert len(entries) == 1
        assert entries[0].content == "Nexus note"

    def test_most_recent_first(self, registry):
        registry.create_entry(owner="The Nexus", content="First")
        registry.create_entry(owner="The Nexus", content="Second")
        registry.create_entry(owner="The Nexus", content="Third")
        entries = registry.list_for_owner("The Nexus")
        assert [e.content for e in entries] == ["Third", "Second", "First"]


class TestListForCard:
    def test_empty_for_unknown_card(self, registry):
        assert registry.list_for_card("card-none") == []

    def test_lists_only_entries_linked_to_that_card(self, registry):
        registry.create_entry(owner="The Nexus", content="Linked", linked_card_id="card-1")
        registry.create_entry(owner="The Nexus", content="Unlinked")
        entries = registry.list_for_card("card-1")
        assert len(entries) == 1
        assert entries[0].content == "Linked"

    def test_most_recent_first(self, registry):
        registry.create_entry(owner="A", content="First", linked_card_id="card-1")
        registry.create_entry(owner="B", content="Second", linked_card_id="card-1")
        entries = registry.list_for_card("card-1")
        assert [e.content for e in entries] == ["Second", "First"]


class TestPersistence:
    def test_entries_survive_reconnect(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        reg1 = NotebookRegistry(db_path=db_path)
        reg1.create_entry(owner="The Nexus", content="Persisted note")
        reg1.close()

        reg2 = NotebookRegistry(db_path=db_path)
        try:
            entries = reg2.list_for_owner("The Nexus")
            assert len(entries) == 1
            assert entries[0].content == "Persisted note"
        finally:
            reg2.close()

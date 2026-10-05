"""A rename is only free when nothing has persisted the old name.

The DIMENSIONALS rename changed a key in `PLATFORM_ROLES`, and that key is
stored: `role_assignments.location` and `role_assignment_history.location` hold
it in every deployment's SQLite file. Without a migration the row keyed to the
old id simply stops matching, `_seed_defaults()` inserts a fresh one at the
canonical default holder, and the operator's actual assignment survives only as
an orphan with no `PLATFORM_ROLES` metadata to render it.

The visible result is the worst kind: the listing shows a plausible answer --
the default holder -- and nothing anywhere says that a reassignment was made and
is being ignored. A registry that reports the seeded default as though it were
the current holder is exactly the class of defect this estate keeps finding.

Found by `chatgpt-codex-connector` on PR #1244, in a diff that contains no
behaviour change at all. That is the point: the rename is inert in the code and
not inert in the data.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.roles.registry import RoleRegistry

OLD_ID = "Dimension" + "al"
NEW_ID = OLD_ID + "s"
OPERATOR_CHOICE = "An Operator's Deliberate Pick"


def _legacy_schema(db) -> None:
    """The two tables as they stand on a deployment that predates the rename."""
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE role_assignments (
            location TEXT NOT NULL,
            seat_id TEXT NOT NULL DEFAULT 'primary',
            job_description TEXT NOT NULL,
            assigned_ai TEXT,
            assigned_at REAL NOT NULL,
            assigned_by TEXT NOT NULL DEFAULT 'system',
            PRIMARY KEY (location, seat_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE role_assignment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            seat_id TEXT NOT NULL DEFAULT 'primary',
            previous_ai TEXT,
            new_ai TEXT,
            changed_at REAL NOT NULL,
            changed_by TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()
    conn.close()


def _registry_with_legacy_row(tmp_path, *, with_history: bool = True) -> RoleRegistry:
    """A database holding an operator's assignment under the retired id."""
    db = tmp_path / "roles.db"
    _legacy_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO role_assignments "
        "(location, seat_id, job_description, assigned_ai, assigned_at, assigned_by) "
        "VALUES (?, 'primary', 'Shared Functional Services Core', ?, 1000.0, 'an-operator')",
        (OLD_ID, OPERATOR_CHOICE),
    )
    if with_history:
        conn.execute(
            "INSERT INTO role_assignment_history "
            "(location, seat_id, previous_ai, new_ai, changed_at, changed_by, reason) "
            "VALUES (?, 'primary', 'someone-else', ?, 1000.0, 'an-operator', 'deliberate')",
            (OLD_ID, OPERATOR_CHOICE),
        )
    conn.commit()
    conn.close()
    return RoleRegistry(db)


class TestTheAssignmentSurvivesTheRename:
    def test_the_operators_choice_is_not_replaced_by_the_seeded_default(self, tmp_path) -> None:
        registry = _registry_with_legacy_row(tmp_path)
        role = registry.get_role(NEW_ID)
        assert role is not None, f"no role under {NEW_ID!r} after the migration"
        assert role.assigned_ai == OPERATOR_CHOICE, (
            "the seeded default replaced the operator's assignment -- which is "
            "the failure mode, because the listing then looks correct"
        )
        assert role.assigned_by == "an-operator"

    def test_no_orphan_is_left_behind(self, tmp_path) -> None:
        registry = _registry_with_legacy_row(tmp_path)
        rows = registry._conn.execute(
            "SELECT COUNT(*) FROM role_assignments WHERE location = ?", (OLD_ID,)
        ).fetchone()[0]
        assert rows == 0, "the retired role id still has a row, with no metadata to render it"
        assert all(r.location != OLD_ID for r in registry.list_roles())

    def test_the_history_travels_with_it(self, tmp_path) -> None:
        registry = _registry_with_legacy_row(tmp_path)
        carried = registry._conn.execute(
            "SELECT changed_by, reason FROM role_assignment_history WHERE location = ?",
            (NEW_ID,),
        ).fetchall()
        assert len(carried) == 1, "the audit history did not follow the role"
        assert carried[0]["changed_by"] == "an-operator"
        stranded = registry._conn.execute(
            "SELECT COUNT(*) FROM role_assignment_history WHERE location = ?", (OLD_ID,)
        ).fetchone()[0]
        assert stranded == 0


class TestItDoesNotMisfire:
    def test_a_fresh_database_is_untouched(self, tmp_path) -> None:
        """Nothing to migrate must not mean something gets invented."""
        registry = RoleRegistry(tmp_path / "fresh.db")
        assert (
            registry._conn.execute(
                "SELECT COUNT(*) FROM role_assignments WHERE location = ?", (OLD_ID,)
            ).fetchone()[0]
            == 0
        )
        assert registry.get_role(NEW_ID) is not None, "the renamed role should still seed"

    def test_running_twice_is_idempotent(self, tmp_path) -> None:
        db = (_registry_with_legacy_row(tmp_path)).db_path
        again = RoleRegistry(db)
        role = again.get_role(NEW_ID)
        assert role is not None and role.assigned_ai == OPERATOR_CHOICE
        assert (
            again._conn.execute(
                "SELECT COUNT(*) FROM role_assignment_history WHERE location = ?", (NEW_ID,)
            ).fetchone()[0]
            == 1
        ), "a second startup duplicated the history"

    def test_an_existing_new_row_wins_over_the_retired_one(self, tmp_path) -> None:
        """If both ids somehow exist, the current one is authoritative."""
        db = tmp_path / "both.db"
        _legacy_schema(db)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO role_assignments "
            "(location, seat_id, job_description, assigned_ai, assigned_at, assigned_by) "
            "VALUES (?, 'primary', 'Shared Functional Services Core', 'newer', 2000.0, 'newer')",
            (NEW_ID,),
        )
        conn.execute(
            "INSERT INTO role_assignments "
            "(location, seat_id, job_description, assigned_ai, assigned_at, assigned_by) "
            "VALUES (?, 'primary', 'Shared Functional Services Core', ?, 1000.0, 'an-operator')",
            (OLD_ID, OPERATOR_CHOICE),
        )
        conn.commit()
        conn.close()

        reopened = RoleRegistry(db)
        role = reopened.get_role(NEW_ID)
        assert role is not None and role.assigned_ai == "newer"
        assert (
            reopened._conn.execute(
                "SELECT COUNT(*) FROM role_assignments WHERE location = ?", (OLD_ID,)
            ).fetchone()[0]
            == 0
        ), "the retired row survived alongside the current one"


def test_the_retired_id_is_not_a_bare_literal_in_the_registry() -> None:
    """The migration table must survive the rename script that created the need.

    `RENAMED_ROLE_IDS` names the pre-rename id. Written plainly it is exactly
    what `scripts/migrate_to_dimensionals.py` rewrites, which would leave the
    migration mapping the new id to itself -- present, running, and moving
    nothing. Same defence as the naming test: build it at runtime.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "roles" / "registry.py"
    text = source.read_text(encoding="utf-8")
    bare = '"' + "Dimension" + 'al"'
    assert bare not in text, (
        f"a bare {bare} literal in the registry is rewritable by the migration "
        'script; build it at runtime, as `"Dimension" + "al"`'
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

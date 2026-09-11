"""Path containment for the backup engine — SEC-017.

Two defects, one of which CodeQL reported:

* **Reported.** ``list_backups(worker)`` did ``self.backup_root / worker`` and
  then ``rglob("*.meta.json")``. ``Path.__truediv__`` neither normalises ``..``
  nor refuses an absolute right operand — it *replaces* the left one — so
  ``?worker=/`` walked the whole filesystem and returned the contents of every
  ``*.meta.json`` it found.

* **Not reported.** ``restore(backup_path=..., target_path=...)`` honoured both
  verbatim. After the SQLite integrity check it did
  ``live.parent.mkdir(parents=True)`` then ``shutil.move``, which is an
  arbitrary file write of caller-supplied content. That is the more serious of
  the two and no alert named it — which is why the alert list is a place to
  start reading rather than a list of what is wrong.

Both are behind ``workers/backup-service/worker.py``'s ``x-internal-secret``
middleware, which gates everything but ``/health`` and fails closed. These are
post-authentication defects. ``INTERNAL_SECRET`` is one shared value across the
estate's workers, so the primitive is reachable from any single compromised
worker.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from Dimensional.path_validation import PathTraversalError
from src.backup.engine import BackupEngine
from src.backup.registry import WORKER_DATABASE_REGISTRY, BackupTier, WorkerDB


@pytest.fixture()
def engine(tmp_path) -> BackupEngine:
    return BackupEngine(backup_root=tmp_path / "backups", encrypt=False)


@pytest.fixture()
def live_db(tmp_path) -> Path:
    db = tmp_path / "live" / "test_worker.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def worker_db(live_db) -> WorkerDB:
    return WorkerDB(
        worker="test-worker",
        env_var="SEC017_TEST_WORKER_DB",
        default_path=str(live_db),
        tier=BackupTier.CRITICAL,
        description="SEC-017 fixture",
    )


class TestWorkerNameIsAName:
    """A worker name indexes a directory under the root. It is not a path."""

    @pytest.mark.parametrize(
        "worker",
        ["../../etc", "..", "a/../../b", "/", "/etc", "//etc", "", "a/b", "x\x00y"],
    )
    def test_refused(self, engine: BackupEngine, worker: str) -> None:
        with pytest.raises((PathTraversalError, ValueError)):
            engine._worker_backup_dir(worker)

    @pytest.mark.parametrize("worker", ["infinity-auth", "the-lab", "warp-radio", "a", "x_1.db"])
    def test_real_registry_shapes_accepted(self, engine: BackupEngine, worker: str) -> None:
        assert engine._worker_backup_dir(worker).is_relative_to(Path(engine.backup_root).resolve())

    def test_every_registered_worker_name_is_accepted(self, engine: BackupEngine) -> None:
        """A guard that refused a real worker name would break every backup.

        This is the half that matters as much as the refusals: an over-tight
        name check is a self-inflicted outage dressed as a security fix.
        """
        for db in WORKER_DATABASE_REGISTRY:
            assert engine._worker_backup_dir(db.worker).is_relative_to(
                Path(engine.backup_root).resolve()
            ), db.worker


class TestListBackupsDoesNotEscape:
    @pytest.mark.parametrize("worker", ["../outside", "/", "..", "a/b"])
    def test_traversal_worker_is_refused_and_walks_nothing(
        self, engine: BackupEngine, tmp_path: Path, worker: str
    ) -> None:
        """Before the fix this returned the planted file's contents.

        It raises rather than returning ``[]``: an empty list is what a real
        worker with no backups yet looks like, and a name the service will never
        accept should not be indistinguishable from that. The HTTP route turns
        the refusal into a 400.
        """
        planted = tmp_path / "outside" / "nested"
        planted.mkdir(parents=True, exist_ok=True)
        (planted / "secret.meta.json").write_text('{"leaked": true}')

        with pytest.raises((PathTraversalError, ValueError)):
            engine.list_backups(worker)

    def test_absolute_outside_path_is_refused(self, engine: BackupEngine, tmp_path: Path) -> None:
        with pytest.raises((PathTraversalError, ValueError)):
            engine.list_backups(str(tmp_path / "outside"))

    def test_no_worker_still_lists_the_root(self, engine: BackupEngine, worker_db) -> None:
        engine.backup(worker_db)
        assert engine.list_backups() != []

    def test_named_worker_still_lists_its_own(self, engine: BackupEngine, worker_db) -> None:
        engine.backup(worker_db)
        assert engine.list_backups(worker_db.worker) != []


class TestRestoreTargetIsPermitted:
    def test_arbitrary_target_is_refused(self, engine: BackupEngine, worker_db, tmp_path) -> None:
        engine.backup(worker_db)
        result = engine.restore(
            worker_db.worker, target_path=str(tmp_path / "anywhere.db"), dry_run=False
        )
        assert result.success is False
        assert "BACKUP_RESTORE_ROOT" in (result.error or "")

    def test_refusal_happens_before_any_write(
        self, engine: BackupEngine, worker_db, tmp_path
    ) -> None:
        """The destination must not be created on the way to being refused."""
        engine.backup(worker_db)
        target = tmp_path / "must-not-exist" / "x.db"
        engine.restore(worker_db.worker, target_path=str(target), dry_run=False)
        assert not target.exists()
        assert not target.parent.exists()

    def test_target_under_configured_root_is_allowed(
        self, engine: BackupEngine, worker_db, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("BACKUP_RESTORE_ROOT", str(tmp_path / "restores"))
        (tmp_path / "restores").mkdir()
        engine.backup(worker_db)
        result = engine.restore(
            worker_db.worker, target_path=str(tmp_path / "restores" / "out.db"), dry_run=False
        )
        assert result.success is True, result.error

    def test_traversal_out_of_the_configured_root_is_refused(
        self, engine: BackupEngine, worker_db, tmp_path, monkeypatch
    ) -> None:
        """A configured escape hatch is still a containment boundary."""
        monkeypatch.setenv("BACKUP_RESTORE_ROOT", str(tmp_path / "restores"))
        (tmp_path / "restores").mkdir()
        engine.backup(worker_db)
        result = engine.restore(
            worker_db.worker,
            target_path=str(tmp_path / "restores" / ".." / "escaped.db"),
            dry_run=False,
        )
        assert result.success is False
        assert not (tmp_path / "escaped.db").exists()

    def test_registry_declared_path_needs_no_env(self, engine: BackupEngine) -> None:
        """The normal case: restoring a registered worker to its own live path."""
        declared = WORKER_DATABASE_REGISTRY[0]
        assert engine._permitted_restore_target(declared.resolved_path) == Path(
            declared.resolved_path
        )


class TestRestoreSourceIsContained:
    def test_backup_path_outside_the_root_is_refused(
        self, engine: BackupEngine, worker_db, tmp_path, monkeypatch
    ) -> None:
        """A backup is a file this service wrote. Nothing else qualifies."""
        monkeypatch.setenv("BACKUP_RESTORE_ROOT", str(tmp_path / "restores"))
        (tmp_path / "restores").mkdir()
        outside = tmp_path / "planted.gz"
        outside.write_bytes(b"\x1f\x8b" + b"\x00" * 32)

        result = engine.restore(
            worker_db.worker,
            backup_path=str(outside),
            target_path=str(tmp_path / "restores" / "out.db"),
            dry_run=True,
        )
        assert result.success is False
        assert "backup" in (result.error or "").lower()

    def test_backup_path_inside_the_root_still_works(
        self, engine: BackupEngine, worker_db, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("BACKUP_RESTORE_ROOT", str(tmp_path / "restores"))
        (tmp_path / "restores").mkdir()
        engine.backup(worker_db)
        latest = engine._latest_backup(worker_db.worker)
        assert latest is not None
        result = engine.restore(
            worker_db.worker,
            backup_path=latest,
            target_path=str(tmp_path / "restores" / "out.db"),
            dry_run=True,
        )
        assert result.success is True, result.error


class TestLatestBackupDoesNotEscape:
    @pytest.mark.parametrize("worker", ["../..", "/", "../outside"])
    def test_traversal_worker_finds_nothing(self, engine: BackupEngine, worker: str) -> None:
        assert engine._latest_backup(worker) is None

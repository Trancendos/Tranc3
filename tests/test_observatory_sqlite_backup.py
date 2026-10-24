"""Offline tests for the consistent Observatory backup utility."""
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'observatory_sqlite_backup.py'
spec = importlib.util.spec_from_file_location('observatory_sqlite_backup', SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def _make_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE audit_log (id INTEGER PRIMARY KEY, event_id TEXT)')
        conn.execute('INSERT INTO audit_log (event_id) VALUES (?)', ('first',))


def test_backup_contains_wal_commits_and_manifest_digest(tmp_path):
    src = tmp_path / 'audit.db'
    _make_db(src)
    dst = tmp_path / 'backup.sqlite'
    info = backup.backup_database(src, dst)
    assert info['audit_event_count'] == 1
    assert info['sqlite_integrity_check'] == 'ok'
    assert info['sha256'] == hashlib.sha256(dst.read_bytes()).hexdigest()
    assert json.loads((tmp_path / 'backup.sqlite.json').read_text()) == info
    with sqlite3.connect(dst) as conn:
        assert conn.execute('SELECT event_id FROM audit_log').fetchone()[0] == 'first'


def test_backup_refuses_to_overwrite_existing_destination(tmp_path):
    src = tmp_path / 'audit.db'
    _make_db(src)
    dst = tmp_path / 'backup.sqlite'
    dst.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        backup.backup_database(src, dst)
    assert dst.read_bytes() == b'preserve'


def test_backup_refuses_missing_source_without_creating_database(tmp_path):
    src = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        backup.backup_database(src, tmp_path / 'backup.sqlite')
    assert not src.exists()


def test_backup_refuses_non_audit_database(tmp_path):
    src = tmp_path / 'not_audit.db'
    with sqlite3.connect(src) as conn:
        conn.execute('CREATE TABLE example (x INTEGER)')
    with pytest.raises(sqlite3.OperationalError):
        backup.backup_database(src, tmp_path / 'backup.sqlite')
    assert not (tmp_path / 'backup.sqlite').exists()

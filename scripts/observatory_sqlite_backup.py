#!/usr/bin/env python3
"""Create a consistent, independently verifiable Observatory SQLite backup.

Uses SQLite's online backup API so active WAL transactions are included.
Never modifies the source or overwrites an existing destination. Backup
integrity is checked before the backup is accepted. Requires Python stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(source: Path, destination: Path) -> dict:
    """Backup a live database; refuse collisions and invalid source/backup."""
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if not source.is_file():
        raise ValueError('Source is not a regular file')
    if destination.exists() or destination.with_suffix(destination.suffix + '.json').exists():
        raise FileExistsError('Backup or manifest already exists')
    if source == destination.resolve():
        raise ValueError('Source and destination must differ')
    if not destination.parent.is_dir():
        raise FileNotFoundError('Backup directory must already exist')

    fd, temp_name = tempfile.mkstemp(prefix='.observatory-backup-', suffix='.sqlite', dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    manifest = destination.with_suffix(destination.suffix + '.json')
    try:
        # Read-only connection prevents creating a missing source database.
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as src:
            with closing(sqlite3.connect(str(temp), timeout=30)) as dst:
                src.backup(dst)
                integrity = dst.execute('PRAGMA integrity_check').fetchone()[0]
                if integrity != 'ok':
                    raise ValueError(f'Backup integrity check failed: {integrity}')
                events = dst.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
        # The hash and count describe the snapshot, not the live source after it advances.
        metadata = {
            'format': 'observatory-sqlite-backup-v1',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'file': destination.name,
            'sha256': _sha256(temp),
            'bytes': temp.stat().st_size,
            'audit_event_count': events,
            'sqlite_integrity_check': 'ok',
            'note': 'Verify audit hash chain with the v2-aware worker before restore.',
        }
        # Refuse races with another backup process: exclusive creation.
        with destination.open('xb') as output, temp.open('rb') as input_stream:
            for chunk in iter(lambda: input_stream.read(1024 * 1024), b''):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        try:
            with manifest.open('x', encoding='utf-8') as stream:
                json.dump(metadata, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return metadata
    finally:
        temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path, help='Existing audit.db file')
    parser.add_argument('--output', required=True, type=Path, help='New backup .sqlite path')
    args = parser.parse_args(argv)
    try:
        result = backup_database(args.db, args.output)
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(2, f'Backup failed: {exc}\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

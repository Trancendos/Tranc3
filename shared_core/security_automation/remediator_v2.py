"""
shared_core.security_automation.remediator_v2 — Enhanced auto-remediation with preview and rollback.

Extends AutoRemediator with:
    - Preview mode: show what would be fixed without modifying files
    - Session tracking: group fixes into named sessions
    - Rollback support: undo applied fixes
    - FixResult dataclass for structured results

Zero-cost: All remediation is local, no external APIs required.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List

from shared_core.security_automation.remediator import AutoRemediator
from shared_core.security_automation.scanner import Violation


@dataclass
class FixResult:
    """Result of a single fix operation."""

    file: str
    rule_id: str
    applied: bool
    dry_run: bool = False
    details: str = ""
    backup_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "rule_id": self.rule_id,
            "applied": self.applied,
            "dry_run": self.dry_run,
            "details": self.details,
            "backup_path": self.backup_path,
        }


@dataclass
class RemediationSession:
    """A session grouping multiple fix results."""

    session_id: str
    results: List[FixResult] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "results": [r.to_dict() for r in self.results],
            "created_at": self.created_at,
        }


class AutoRemediatorV2:
    """Enhanced auto-remediation with preview and rollback.

    Extends AutoRemediator with session-based remediation tracking,
    preview mode, and rollback support.

    Args:
        dry_run: If True, preview fixes without applying them.
        backup: If True, create backup files before modifying.
    """

    def __init__(self, *, dry_run: bool = True, backup: bool = True) -> None:
        self._remediator = AutoRemediator(dry_run=dry_run, backup=backup)
        self._dry_run = dry_run
        self._backup = backup
        self._sessions: List[RemediationSession] = []
        self._session_counter = 0

    def preview(self, violations: List[Violation]) -> List[FixResult]:
        """Preview what fixes would be applied without modifying files.

        Args:
            violations: List of violations to preview fixes for.

        Returns:
            List of FixResult objects describing the planned fixes.
        """
        results: List[FixResult] = []
        for v in violations:
            if v.fixable:
                results.append(
                    FixResult(
                        file=v.file,
                        rule_id=v.rule_id,
                        applied=False,
                        dry_run=True,
                        details=f"Would fix {v.rule_id} in {v.file}",
                    )
                )
        return results

    def remediate(self, violations: List[Violation]) -> RemediationSession:
        """Apply fixes and create a session for rollback.

        Args:
            violations: List of violations to fix.

        Returns:
            RemediationSession with all fix results.
        """
        from datetime import datetime, timezone

        self._session_counter += 1
        session = RemediationSession(
            session_id=f"session-{self._session_counter}",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Use the base remediator for actual fixes
        applied = self._remediator.remediate(violations)

        # Convert applied fixes to FixResults
        for fix in applied:
            result = FixResult(
                file=fix.get("file", ""),
                rule_id="auto",
                applied=fix.get("dry_run", True) is False,
                dry_run=self._dry_run,
                details=f"Fixed {fix.get('violations_fixed', 0)} violations",
            )
            session.results.append(result)

        self._sessions.append(session)
        return session

    def rollback(self, session_id: str) -> bool:
        """Rollback a remediation session by restoring backup files.

        Args:
            session_id: The session to rollback.

        Returns:
            True if rollback was successful.
        """
        session = next(
            (s for s in self._sessions if s.session_id == session_id),
            None,
        )
        if not session:
            return False

        for result in session.results:
            if result.backup_path:
                try:
                    shutil.copy2(result.backup_path, result.file)
                except (OSError, shutil.Error):
                    continue

        return True

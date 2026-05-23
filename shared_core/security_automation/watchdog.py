"""
shared_core.security_automation.watchdog — Real-time file watcher with proactive security scanning.

Monitors the codebase for file changes and automatically triggers security
scans on modified files. Provides immediate feedback when new violations
are introduced, catching security regressions at the point of authorship
rather than waiting for CI.

Features:
    - Real-time file system monitoring using watchdog (or polling fallback)
    - Debounced scanning — batches rapid changes to avoid thrashing
    - Smart change detection — only scans .py files that actually changed
    - Incremental scanning — scans only modified files, not the entire tree
    - Notification support — callbacks for integration with IDEs, CI, or chat
    - Graceful degradation — falls back to polling if watchdog is unavailable

Usage:
    from shared_core.security_automation.watchdog import SecurityWatchdog

    watchdog = SecurityWatchdog(
        watch_paths=["src/", "shared_core/"],
        on_violation=lambda v: print(f"New violation: {v}"),
    )
    watchdog.start()  # Blocks, or pass background=True

    # Or as a context manager:
    with SecurityWatchdog(watch_paths=["src/"]) as wd:
        # Files are being watched...
        pass  # Stops automatically
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Set

from shared_core.security_automation.adaptive_scanner import AdaptiveScanner, AdaptiveViolation
from shared_core.security_automation.scanner import Severity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DEBOUNCE_SECONDS = 2.0
_DEFAULT_SCAN_INTERVAL = 5.0
_PYTHON_EXTENSIONS = {".py", ".pyi"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class WatchEvent:
    """A single file change event."""

    filepath: str
    event_type: str  # "created", "modified", "deleted", "moved"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class ScanAlert:
    """Alert generated when a scan finds new violations."""

    timestamp: str
    trigger_file: str
    new_violations: List[AdaptiveViolation]
    total_violations: int
    scan_duration: float = 0.0


# ---------------------------------------------------------------------------
# Callback types
# ---------------------------------------------------------------------------

ViolationCallback = Callable[[ScanAlert], None]
ChangeCallback = Callable[[WatchEvent], None]


# ---------------------------------------------------------------------------
# SecurityWatchdog
# ---------------------------------------------------------------------------


class SecurityWatchdog:
    """Real-time file watcher that proactively scans for security violations.

    Monitors specified directories for Python file changes and triggers
    incremental security scans when files are modified. Designed for use
    during development to catch violations immediately.

    Architecture:
        File Change → Debounce → Incremental Scan → Alert Callback

    The watchdog uses a debounce mechanism to batch rapid file changes
    (e.g., saving a file multiple times in quick succession) into a
    single scan operation.
    """

    def __init__(
        self,
        *,
        watch_paths: List[str],
        on_violation: Optional[ViolationCallback] = None,
        on_change: Optional[ChangeCallback] = None,
        debounce_seconds: float = _DEFAULT_DEBOUNCE_SECONDS,
        min_severity: Severity = Severity.LOW,
        adaptive_scanner: Optional[AdaptiveScanner] = None,
        exclude_patterns: Optional[List[str]] = None,
    ):
        """Initialize the security watchdog.

        Args:
            watch_paths: List of directory paths to monitor.
            on_violation: Callback when new violations are found.
            on_change: Callback when a file change is detected.
            debounce_seconds: Seconds to wait after last change before scanning.
            min_severity: Minimum severity to trigger violation callback.
            adaptive_scanner: Custom adaptive scanner instance.
            exclude_patterns: Glob patterns for files to exclude.
        """
        self._watch_paths = watch_paths
        self._on_violation = on_violation
        self._on_change = on_change
        self._debounce_seconds = debounce_seconds
        self._min_severity = min_severity
        self._scanner = adaptive_scanner or AdaptiveScanner()
        self._exclude_patterns = exclude_patterns or [
            "*/__pycache__/*",
            "*/.git/*",
            "*/node_modules/*",
            "*/.venv/*",
            "*/venv/*",
            "*/.security_learning/*",
        ]

        # Internal state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._pending_files: Dict[str, float] = {}  # filepath → last_change_time
        self._lock = threading.Lock()
        self._scan_history: List[ScanAlert] = []
        self._baseline_violations: Dict[str, Set[str]] = {}  # filepath → set of violation keys

        # Observer (watchdog library or polling fallback)
        self._observer = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, *, background: bool = False) -> None:
        """Start monitoring for file changes.

        Args:
            background: If True, run in a background thread. Otherwise blocks.
        """
        if self._running:
            return

        self._running = True

        # Build baseline — scan all files first
        self._build_baseline()

        # Try to use watchdog library for efficient file monitoring
        try:
            self._start_watchdog_observer()
        except ImportError:
            logger.info("watchdog library not available, falling back to polling")
            self._start_polling_fallback()

        if not background:
            try:
                while self._running:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        """Stop monitoring for file changes."""
        self._running = False

        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5.0)
            except Exception:
                pass
            self._observer = None

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def get_scan_history(self, limit: int = 50) -> List[ScanAlert]:
        """Return recent scan alerts."""
        return list(self._scan_history[-limit:])

    def get_stats(self) -> Dict:
        """Return watchdog statistics."""
        return {
            "running": self._running,
            "watch_paths": self._watch_paths,
            "total_scans": len(self._scan_history),
            "baseline_files": len(self._baseline_violations),
            "pending_files": len(self._pending_files),
            "using_watchdog_lib": self._observer is not None,
        }

    # ------------------------------------------------------------------
    # Internal: baseline
    # ------------------------------------------------------------------

    def _build_baseline(self) -> None:
        """Scan all watched paths to establish a baseline of known violations."""
        logger.info("Building security baseline for %s", self._watch_paths)
        for path in self._watch_paths:
            if not os.path.isdir(path):
                continue
            for root, dirs, files in os.walk(path):
                # Skip excluded directories
                dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d))]
                for fname in files:
                    if fname.endswith((".py", ".pyi")):
                        filepath = os.path.join(root, fname)
                        violations = self._scanner.scan_file(filepath)
                        keys = set()
                        for v in violations:
                            key = f"{v.rule_id}:{v.line}"
                            keys.add(key)
                        self._baseline_violations[filepath] = keys

        total_baseline = sum(len(v) for v in self._baseline_violations.values())
        logger.info(
            "Baseline established: %d files, %d known violations",
            len(self._baseline_violations),
            total_baseline,
        )

    # ------------------------------------------------------------------
    # Internal: watchdog library integration
    # ------------------------------------------------------------------

    def _start_watchdog_observer(self) -> None:
        """Start the watchdog library file observer."""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        parent = self

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory and event.src_path.endswith((".py", ".pyi")):
                    parent._on_file_change(event.src_path, "modified")

            def on_created(self, event):
                if not event.is_directory and event.src_path.endswith((".py", ".pyi")):
                    parent._on_file_change(event.src_path, "created")

            def on_moved(self, event):
                if not event.is_directory and event.src_path.endswith((".py", ".pyi")):
                    parent._on_file_change(event.src_path, "moved")

        observer = Observer()
        handler = _Handler()

        for path in self._watch_paths:
            if os.path.isdir(path):
                observer.schedule(handler, path, recursive=True)

        observer.start()
        self._observer = observer

        # Start debounce processor thread
        self._thread = threading.Thread(target=self._debounce_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Internal: polling fallback
    # ------------------------------------------------------------------

    def _start_polling_fallback(self) -> None:
        """Start a polling-based file watcher as fallback."""
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()

    def _polling_loop(self) -> None:
        """Poll for file changes at regular intervals."""
        # Record initial modification times
        mtimes: Dict[str, float] = {}

        while self._running:
            try:
                for path in self._watch_paths:
                    if not os.path.isdir(path):
                        continue
                    for root, dirs, files in os.walk(path):
                        dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d))]
                        for fname in files:
                            if fname.endswith((".py", ".pyi")):
                                filepath = os.path.join(root, fname)
                                try:
                                    mtime = os.path.getmtime(filepath)
                                except OSError:
                                    continue
                                if filepath in mtimes and mtime > mtimes[filepath]:
                                    self._on_file_change(filepath, "modified")
                                mtimes[filepath] = mtime
            except Exception as e:
                logger.error("Polling error: %s", e)

            time.sleep(_DEFAULT_SCAN_INTERVAL)

    # ------------------------------------------------------------------
    # Internal: debounce and scan
    # ------------------------------------------------------------------

    def _debounce_loop(self) -> None:
        """Process debounced file changes — scans files after debounce period."""
        while self._running:
            try:
                self._process_pending()
            except Exception as e:
                logger.error("Debounce processing error: %s", e)
            time.sleep(0.5)

    def _on_file_change(self, filepath: str, event_type: str) -> None:
        """Handle a file change event."""
        if self._is_excluded(filepath):
            return

        # Record the change
        with self._lock:
            self._pending_files[filepath] = time.time()

        # Fire change callback
        if self._on_change:
            try:
                self._on_change(WatchEvent(filepath=filepath, event_type=event_type))
            except Exception as e:
                logger.error("Change callback error: %s", e)

    def _process_pending(self) -> None:
        """Process pending file changes that have settled after debounce."""
        now = time.time()
        files_to_scan: List[str] = []

        with self._lock:
            settled = []
            for filepath, change_time in list(self._pending_files.items()):
                if now - change_time >= self._debounce_seconds:
                    settled.append(filepath)

            for filepath in settled:
                del self._pending_files[filepath]
                files_to_scan.append(filepath)

        for filepath in files_to_scan:
            self._scan_file_incremental(filepath)

    def _scan_file_incremental(self, filepath: str) -> None:
        """Scan a single file and alert on new violations.

        Compares against baseline to identify NEW violations only.
        """
        if not os.path.exists(filepath):
            return

        start_time = time.time()
        violations = self._scanner.scan_file(filepath)

        # Filter by severity
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        min_idx = severity_order.get(self._min_severity, 4)
        filtered = [v for v in violations if severity_order.get(v.severity, 4) <= min_idx]

        # Compare against baseline
        baseline_keys = self._baseline_violations.get(filepath, set())
        current_keys = set()
        new_violations = []

        for v in filtered:
            key = f"{v.rule_id}:{v.line}"
            current_keys.add(key)
            if key not in baseline_keys:
                new_violations.append(v)

        # Update baseline
        self._baseline_violations[filepath] = current_keys

        # Create alert if new violations found
        if new_violations:
            alert = ScanAlert(
                timestamp=datetime.now(timezone.utc).isoformat(),
                trigger_file=filepath,
                new_violations=new_violations,
                total_violations=len(filtered),
                scan_duration=time.time() - start_time,
            )
            self._scan_history.append(alert)

            # Fire callback
            if self._on_violation:
                try:
                    self._on_violation(alert)
                except Exception as e:
                    logger.error("Violation callback error: %s", e)

    # ------------------------------------------------------------------
    # Internal: utilities
    # ------------------------------------------------------------------

    def _is_excluded(self, filepath: str) -> bool:
        """Check if a filepath matches any exclusion pattern."""
        from fnmatch import fnmatch

        for pattern in self._exclude_patterns:
            if fnmatch(filepath, pattern):
                return True
        return False

    def __enter__(self):
        self.start(background=True)
        return self

    def __exit__(self, *args):
        self.stop()

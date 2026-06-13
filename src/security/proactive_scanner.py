"""
Linux /proc-based proactive security scanner — stdlib only.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class ProcessSnapshot:
    pid: int
    name: str
    cmdline: str
    cpu_percent: float
    mem_rss_kb: int
    open_fds: int
    net_connections: List[int]  # list of local ports


@dataclass
class AnomalyFinding:
    pid: int
    name: str
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    reason: str


def _read_proc_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(errors="replace")
    except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
        return None


def _parse_status(pid: int) -> Optional[dict]:
    content = _read_proc_file(Path(f"/proc/{pid}/status"))
    if content is None:
        return None
    result: dict = {}
    for line in content.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def _parse_cmdline(pid: int) -> str:
    content = _read_proc_file(Path(f"/proc/{pid}/cmdline"))
    if content is None:
        return ""
    return content.replace("\x00", " ").strip()


def _count_fds(pid: int) -> int:
    try:
        fd_dir = Path(f"/proc/{pid}/fd")
        return sum(1 for _ in fd_dir.iterdir())
    except (PermissionError, FileNotFoundError, OSError):
        return 0


def _get_net_connections(pid: int) -> List[int]:
    """Parse /proc/{pid}/net/tcp for local listening ports."""
    content = _read_proc_file(Path(f"/proc/{pid}/net/tcp"))
    ports: List[int] = []
    if content is None:
        return ports
    for line in content.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            local_addr = parts[1]
            state = parts[3]
            _, hex_port = local_addr.split(":")
            port = int(hex_port, 16)
            # state 0A = LISTEN
            if state == "0A" and port not in ports:
                ports.append(port)
        except (ValueError, IndexError):
            continue
    return ports


def _get_cpu_approx(pid: int) -> float:
    """Two-sample /proc/{pid}/stat approximation of CPU%."""
    stat_path = Path(f"/proc/{pid}/stat")

    def _read_utime_stime() -> Optional[tuple]:
        content = _read_proc_file(stat_path)
        if content is None:
            return None
        parts = content.split()
        if len(parts) < 15:
            return None
        try:
            return int(parts[13]), int(parts[14])
        except (ValueError, IndexError):
            return None

    s1 = _read_utime_stime()
    if s1 is None:
        return 0.0
    time.sleep(0.1)
    s2 = _read_utime_stime()
    if s2 is None:
        return 0.0
    delta = (s2[0] + s2[1]) - (s1[0] + s1[1])
    # delta is in clock ticks; 100 ticks/s is standard
    return min(delta * 10.0, 100.0)  # approximate %


def scan_processes() -> List[ProcessSnapshot]:
    """Read /proc and return a snapshot of all visible processes."""
    snapshots: List[ProcessSnapshot] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        status = _parse_status(pid)
        if status is None:
            continue
        name = status.get("Name", "")
        rss_line = status.get("VmRSS", "0 kB")
        try:
            mem_rss_kb = int(rss_line.split()[0])
        except (ValueError, IndexError):
            mem_rss_kb = 0

        cmdline = _parse_cmdline(pid)
        fds = _count_fds(pid)
        ports = _get_net_connections(pid)
        # Skip expensive CPU sample for now (too slow for full sweep)
        snapshots.append(
            ProcessSnapshot(
                pid=pid,
                name=name,
                cmdline=cmdline,
                cpu_percent=0.0,
                mem_rss_kb=mem_rss_kb,
                open_fds=fds,
                net_connections=ports,
            )
        )
    return snapshots


class ProactiveScanner:
    def __init__(self) -> None:
        self._bg_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latest_findings: List[AnomalyFinding] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_cpu_anomaly(
        self,
        snapshots: Optional[List[ProcessSnapshot]] = None,
        threshold_percent: float = 80.0,
    ) -> List[AnomalyFinding]:
        procs = snapshots if snapshots is not None else scan_processes()
        findings: List[AnomalyFinding] = []
        for p in procs:
            if p.cpu_percent >= threshold_percent:
                findings.append(
                    AnomalyFinding(
                        pid=p.pid,
                        name=p.name,
                        severity="HIGH",
                        reason=f"CPU usage {p.cpu_percent:.1f}% exceeds threshold {threshold_percent}%",
                    )
                )
        return findings

    def check_memory_anomaly(
        self,
        snapshots: Optional[List[ProcessSnapshot]] = None,
        threshold_mb: float = 500.0,
    ) -> List[AnomalyFinding]:
        procs = snapshots if snapshots is not None else scan_processes()
        threshold_kb = threshold_mb * 1024
        findings: List[AnomalyFinding] = []
        for p in procs:
            if p.mem_rss_kb >= threshold_kb:
                findings.append(
                    AnomalyFinding(
                        pid=p.pid,
                        name=p.name,
                        severity="MEDIUM",
                        reason=(
                            f"RSS memory {p.mem_rss_kb / 1024:.1f} MB "
                            f"exceeds threshold {threshold_mb} MB"
                        ),
                    )
                )
        return findings

    def check_suspicious_cmdline(
        self,
        patterns: List[str],
        snapshots: Optional[List[ProcessSnapshot]] = None,
    ) -> List[AnomalyFinding]:
        procs = snapshots if snapshots is not None else scan_processes()
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        findings: List[AnomalyFinding] = []
        for proc in procs:
            for pat, raw in zip(compiled, patterns, strict=False):
                if pat.search(proc.cmdline):
                    findings.append(
                        AnomalyFinding(
                            pid=proc.pid,
                            name=proc.name,
                            severity="HIGH",
                            reason=f"Suspicious cmdline pattern '{raw}' matched: {proc.cmdline[:120]}",
                        )
                    )
                    break  # one finding per process
        return findings

    def check_unexpected_listeners(
        self,
        allowed_ports: Set[int],
        snapshots: Optional[List[ProcessSnapshot]] = None,
    ) -> List[AnomalyFinding]:
        procs = snapshots if snapshots is not None else scan_processes()
        findings: List[AnomalyFinding] = []
        seen: Set[int] = set()
        for proc in procs:
            for port in proc.net_connections:
                if port not in allowed_ports and port not in seen:
                    seen.add(port)
                    findings.append(
                        AnomalyFinding(
                            pid=proc.pid,
                            name=proc.name,
                            severity="MEDIUM",
                            reason=f"Unexpected listener on port {port} (not in allowed set)",
                        )
                    )
        return findings

    # ------------------------------------------------------------------
    # Aggregate scan
    # ------------------------------------------------------------------

    def scan_all(
        self,
        cpu_threshold: float = 80.0,
        mem_threshold_mb: float = 500.0,
        suspicious_patterns: Optional[List[str]] = None,
        allowed_ports: Optional[Set[int]] = None,
    ) -> List[AnomalyFinding]:
        procs = scan_processes()
        findings: List[AnomalyFinding] = []
        findings.extend(self.check_cpu_anomaly(procs, cpu_threshold))
        findings.extend(self.check_memory_anomaly(procs, mem_threshold_mb))
        if suspicious_patterns:
            findings.extend(self.check_suspicious_cmdline(suspicious_patterns, procs))
        if allowed_ports is not None:
            findings.extend(self.check_unexpected_listeners(allowed_ports, procs))
        return findings

    # ------------------------------------------------------------------
    # Background scanning
    # ------------------------------------------------------------------

    def start_background_scan(
        self,
        interval_secs: float = 60.0,
        **scan_kwargs: object,
    ) -> None:
        if self._bg_thread and self._bg_thread.is_alive():
            return

        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.wait(timeout=interval_secs):
                findings = self.scan_all(**scan_kwargs)  # type: ignore[arg-type]
                with self._lock:
                    self._latest_findings = findings

        self._bg_thread = threading.Thread(target=_loop, daemon=True)
        self._bg_thread.start()

    def stop_background_scan(self) -> None:
        self._stop_event.set()
        if self._bg_thread:
            self._bg_thread.join(timeout=5)

    @property
    def latest_findings(self) -> List[AnomalyFinding]:
        with self._lock:
            return list(self._latest_findings)

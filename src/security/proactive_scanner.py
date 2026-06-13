"""Linux /proc-based proactive security scanner — stdlib only."""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProcessSnapshot:
    pid: int
    name: str
    cmdline: str
    cpu_percent: float  # approximation via /proc/{pid}/stat deltas
    mem_rss_kb: int
    open_fds: int
    net_connections: list[dict]  # [{local_port, remote_addr, state}]


@dataclass
class AnomalyFinding:
    pid: int
    name: str
    severity: str  # "low" | "medium" | "high" | "critical"
    reason: str


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        return ""


def _parse_proc_status(pid: int) -> dict[str, str]:
    text = _read_text(Path(f"/proc/{pid}/status"))
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def _parse_cmdline(pid: int) -> str:
    raw = _read_text(Path(f"/proc/{pid}/cmdline"))
    return raw.replace("\x00", " ").strip()


def _count_fds(pid: int) -> int:
    fd_dir = Path(f"/proc/{pid}/fd")
    try:
        return sum(1 for _ in fd_dir.iterdir())
    except (PermissionError, FileNotFoundError):
        return 0


def _parse_tcp_connections(pid: int) -> list[dict]:
    """Parse /proc/{pid}/net/tcp and /proc/{pid}/net/tcp6 for open connections."""
    connections: list[dict] = []
    for fname in ("tcp", "tcp6"):
        text = _read_text(Path(f"/proc/{pid}/net/{fname}"))
        for line in text.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) < 4:
                continue
            local_hex = parts[1]
            remote_hex = parts[2]
            state_hex = parts[3]

            def _hex_addr(s: str) -> tuple[str, int]:
                addr, _, port_hex = s.partition(":")
                port = int(port_hex, 16) if port_hex else 0
                # IPv4: reverse byte order
                try:
                    a = int(addr, 16)
                    ip = ".".join(str((a >> (i * 8)) & 0xFF) for i in range(4))
                except ValueError:
                    ip = addr
                return ip, port

            local_ip, local_port = _hex_addr(local_hex)
            remote_ip, remote_port = _hex_addr(remote_hex)
            state_map = {
                "01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV",
                "04": "FIN_WAIT1", "05": "FIN_WAIT2", "06": "TIME_WAIT",
                "07": "CLOSE", "08": "CLOSE_WAIT", "09": "LAST_ACK",
                "0A": "LISTEN", "0B": "CLOSING",
            }
            state = state_map.get(state_hex.upper(), state_hex)
            connections.append({
                "local_ip": local_ip,
                "local_port": local_port,
                "remote_ip": remote_ip,
                "remote_port": remote_port,
                "state": state,
            })
    return connections


def _get_cpu_times(pid: int) -> Optional[tuple[int, int]]:
    """Return (utime, stime) from /proc/{pid}/stat."""
    text = _read_text(Path(f"/proc/{pid}/stat"))
    if not text:
        return None
    parts = text.split()
    if len(parts) < 15:
        return None
    try:
        return int(parts[13]), int(parts[14])
    except ValueError:
        return None


def scan_processes() -> list[ProcessSnapshot]:
    """Return a snapshot of all readable processes in /proc."""
    snapshots: list[ProcessSnapshot] = []
    proc = Path("/proc")

    # Collect CPU-time samples for approximate % (two samples ~0.1s apart)
    pids: list[int] = []
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                pids.append(int(entry.name))
            except ValueError:
                pass

    t0_samples: dict[int, tuple[int, int]] = {}
    for pid in pids:
        t = _get_cpu_times(pid)
        if t is not None:
            t0_samples[pid] = t

    start = time.monotonic()
    time.sleep(0.1)
    elapsed = time.monotonic() - start

    try:
        ticks = _ticks_per_second()
    except Exception:
        ticks = 100

    for pid in pids:
        status = _parse_proc_status(pid)
        name = status.get("Name", "unknown")
        cmdline = _parse_cmdline(pid)

        # Memory
        vm_rss = 0
        vm_rss_str = status.get("VmRSS", "0 kB")
        try:
            vm_rss = int(vm_rss_str.split()[0])
        except (ValueError, IndexError):
            pass

        # CPU approximation
        cpu_pct = 0.0
        t1 = _get_cpu_times(pid)
        if pid in t0_samples and t1 is not None:
            delta_ticks = (t1[0] + t1[1]) - (t0_samples[pid][0] + t0_samples[pid][1])
            cpu_pct = (delta_ticks / ticks / elapsed) * 100.0

        fds = _count_fds(pid)
        connections = _parse_tcp_connections(pid)

        snapshots.append(ProcessSnapshot(
            pid=pid,
            name=name,
            cmdline=cmdline,
            cpu_percent=round(cpu_pct, 2),
            mem_rss_kb=vm_rss,
            open_fds=fds,
            net_connections=connections,
        ))

    return snapshots


def _ticks_per_second() -> int:
    import os
    return os.sysconf("SC_CLK_TCK")


class ProactiveScanner:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._latest_findings: list[AnomalyFinding] = []
        self._lock = threading.Lock()

    def check_cpu_anomaly(
        self,
        snapshots: Optional[list[ProcessSnapshot]] = None,
        threshold_percent: float = 80.0,
    ) -> list[AnomalyFinding]:
        if snapshots is None:
            snapshots = scan_processes()
        findings: list[AnomalyFinding] = []
        for p in snapshots:
            if p.cpu_percent >= threshold_percent:
                findings.append(AnomalyFinding(
                    pid=p.pid,
                    name=p.name,
                    severity="high" if p.cpu_percent >= 95 else "medium",
                    reason=f"CPU usage {p.cpu_percent:.1f}% exceeds threshold {threshold_percent}%",
                ))
        return findings

    def check_memory_anomaly(
        self,
        snapshots: Optional[list[ProcessSnapshot]] = None,
        threshold_mb: float = 500.0,
    ) -> list[AnomalyFinding]:
        if snapshots is None:
            snapshots = scan_processes()
        threshold_kb = threshold_mb * 1024
        findings: list[AnomalyFinding] = []
        for p in snapshots:
            if p.mem_rss_kb >= threshold_kb:
                findings.append(AnomalyFinding(
                    pid=p.pid,
                    name=p.name,
                    severity="medium",
                    reason=f"Memory RSS {p.mem_rss_kb / 1024:.1f} MB exceeds threshold {threshold_mb} MB",
                ))
        return findings

    def check_suspicious_cmdline(
        self,
        patterns: list[str],
        snapshots: Optional[list[ProcessSnapshot]] = None,
    ) -> list[AnomalyFinding]:
        if snapshots is None:
            snapshots = scan_processes()
        compiled = [re.compile(pat, re.IGNORECASE) for pat in patterns]
        findings: list[AnomalyFinding] = []
        for p in snapshots:
            for rx in compiled:
                if rx.search(p.cmdline):
                    findings.append(AnomalyFinding(
                        pid=p.pid,
                        name=p.name,
                        severity="high",
                        reason=f"Cmdline matches suspicious pattern: {rx.pattern!r}",
                    ))
                    break
        return findings

    def check_unexpected_listeners(
        self,
        allowed_ports: set[int],
        snapshots: Optional[list[ProcessSnapshot]] = None,
    ) -> list[AnomalyFinding]:
        if snapshots is None:
            snapshots = scan_processes()
        findings: list[AnomalyFinding] = []
        seen: set[tuple[int, int]] = set()
        for p in snapshots:
            for conn in p.net_connections:
                if conn.get("state") == "LISTEN":
                    port = conn.get("local_port", 0)
                    key = (p.pid, port)
                    if port not in allowed_ports and key not in seen:
                        seen.add(key)
                        findings.append(AnomalyFinding(
                            pid=p.pid,
                            name=p.name,
                            severity="medium",
                            reason=f"Unexpected listener on port {port} (not in allowed_ports)",
                        ))
        return findings

    def scan_all(
        self,
        cpu_threshold: float = 80.0,
        mem_threshold_mb: float = 500.0,
        suspicious_patterns: Optional[list[str]] = None,
        allowed_ports: Optional[set[int]] = None,
    ) -> list[AnomalyFinding]:
        snapshots = scan_processes()
        findings: list[AnomalyFinding] = []
        findings.extend(self.check_cpu_anomaly(snapshots, cpu_threshold))
        findings.extend(self.check_memory_anomaly(snapshots, mem_threshold_mb))
        if suspicious_patterns:
            findings.extend(self.check_suspicious_cmdline(suspicious_patterns, snapshots))
        if allowed_ports is not None:
            findings.extend(self.check_unexpected_listeners(allowed_ports, snapshots))
        return findings

    def start_background_scan(
        self,
        interval_secs: float = 60.0,
        **scan_kwargs: object,
    ) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.wait(interval_secs):
                try:
                    findings = self.scan_all(**scan_kwargs)  # type: ignore[arg-type]
                    with self._lock:
                        self._latest_findings = findings
                except Exception:
                    pass

        self._thread = threading.Thread(target=_loop, daemon=True, name="proactive-scanner")
        self._thread.start()

    def stop_background_scan(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def latest_findings(self) -> list[AnomalyFinding]:
        with self._lock:
            return list(self._latest_findings)

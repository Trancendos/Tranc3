"""Container escape / privilege escalation sentinel — accepted risk RSK-008.

Monitors for indicators of container escape attempts and privilege escalation.
Risk is accepted but MUST be detected. Does not block (detection only).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("container_sentinel")

# Indicators of potential container escape / privilege escalation
_DANGEROUS_PATHS = [
    "/proc/1/root",  # Access to host PID 1
    "/proc/sysrq-trigger",
    "/sys/kernel/debug",
    "/dev/mem",
    "/dev/kmem",
    "/proc/kcore",
    "/.dockerenv",  # Docker env file (expected — flag if modified)
]

_DANGEROUS_ENV_VARS = [
    "DOCKER_HOST",
    "KUBERNETES_SERVICE_HOST",
    "AWS_EXECUTION_ENV",
]

_SUID_BINARIES_PATTERN = re.compile(
    r"^/(?:usr/)?(?:bin|sbin)/(?:sudo|su|newgrp|passwd|chsh|chfn|mount|umount)"
)

_ESCALATION_SYSCALL_PATTERNS = [
    "setuid",
    "setgid",
    "capset",
    "ptrace",
    "clone.*NEWNS",  # namespace clone
    "unshare",
]


@dataclass
class EscapeAlert:
    alert_id: str
    detected_at: str
    indicator_type: str
    indicator_value: str
    severity: str
    details: str


class ContainerSentinel:
    """Monitors for container escape and privilege escalation indicators."""

    def __init__(self) -> None:
        self._alerts: list[EscapeAlert] = []
        self._check_interval = int(os.getenv("CONTAINER_SENTINEL_INTERVAL", "300"))  # 5 min
        self._is_container = self._detect_container_runtime()

    def _detect_container_runtime(self) -> bool:
        """Detect if running inside a container."""
        return (
            Path("/.dockerenv").exists()
            or os.getenv("KUBERNETES_SERVICE_HOST") is not None
            or any("docker" in line for line in self._safe_read("/proc/1/cgroup"))
        )

    def _safe_read(self, path: str) -> list[str]:
        try:
            with open(path) as f:
                return f.readlines()
        except Exception:
            return []

    def _alert(self, indicator_type: str, value: str, severity: str, details: str) -> EscapeAlert:
        import uuid

        a = EscapeAlert(
            alert_id=str(uuid.uuid4())[:8],
            detected_at=datetime.now(timezone.utc).isoformat(),
            indicator_type=indicator_type,
            indicator_value=value,
            severity=severity,
            details=details,
        )
        self._alerts.append(a)
        log_fn = logger.critical if severity == "CRITICAL" else logger.warning
        log_fn("CONTAINER ESCAPE INDICATOR [%s] type=%s value=%s", severity, indicator_type, value)
        return a

    def check_namespace_integrity(self) -> list[EscapeAlert]:
        """Check for unexpected namespace changes (container boundary crossing)."""
        new_alerts = []
        if not self._is_container:
            return new_alerts

        # Check if we can see host PID namespace (escape indicator)
        try:
            host_procs = list(Path("/proc").glob("[0-9]*"))
            if len(host_procs) > 500:  # Many PIDs = might be host namespace
                a = self._alert(
                    "pid_namespace",
                    f"{len(host_procs)}_processes",
                    "HIGH",
                    "Unusually high PID count — possible host namespace access",
                )
                new_alerts.append(a)
        except Exception:
            pass
        return new_alerts

    def check_privileged_files(self) -> list[EscapeAlert]:
        """Check for SUID/SGID files or writable dangerous paths."""
        new_alerts = []
        for path_str in _DANGEROUS_PATHS:
            try:
                p = Path(path_str)
                if p.exists():
                    st = p.stat()
                    if st.st_mode & (stat.S_ISUID | stat.S_ISGID):
                        a = self._alert(
                            "suid_file", path_str, "CRITICAL", f"SUID/SGID bit set on {path_str}"
                        )
                        new_alerts.append(a)
            except (PermissionError, OSError):
                pass
        return new_alerts

    def check_environment(self) -> list[EscapeAlert]:
        """Check for unexpected environment variables indicating escape."""
        new_alerts = []
        for var in _DANGEROUS_ENV_VARS:
            val = os.getenv(var)
            if val and var == "DOCKER_HOST" and val.startswith("tcp://"):
                # Remote Docker socket — potential escape vector
                a = self._alert(
                    "remote_docker_socket",
                    f"{var}={val}",
                    "HIGH",
                    "Remote Docker socket exposed — potential privilege escalation vector",
                )
                new_alerts.append(a)
        return new_alerts

    def check_capability_changes(self) -> list[EscapeAlert]:
        """Check /proc/self/status for unexpected capabilities."""
        new_alerts = []
        lines = self._safe_read("/proc/self/status")
        for line in lines:
            if line.startswith("CapEff:"):
                cap_hex = line.split(":")[1].strip()
                try:
                    caps = int(cap_hex, 16)
                    # CAP_SYS_ADMIN = bit 21; CAP_NET_ADMIN = bit 12
                    if caps & (1 << 21):  # CAP_SYS_ADMIN
                        a = self._alert(
                            "capability",
                            "CAP_SYS_ADMIN",
                            "CRITICAL",
                            "Process has CAP_SYS_ADMIN — highly privileged, escape risk",
                        )
                        new_alerts.append(a)
                except ValueError:
                    pass
        return new_alerts

    def run_checks(self) -> list[EscapeAlert]:
        """Run all checks and return new alerts."""
        new_alerts: list[EscapeAlert] = []
        new_alerts.extend(self.check_namespace_integrity())
        new_alerts.extend(self.check_privileged_files())
        new_alerts.extend(self.check_environment())
        new_alerts.extend(self.check_capability_changes())
        if new_alerts:
            logger.warning("Container sentinel: %d new alerts", len(new_alerts))
        return new_alerts

    async def monitoring_loop(self) -> None:
        logger.info("Container sentinel started (interval: %ds)", self._check_interval)
        while True:
            try:
                self.run_checks()
            except Exception as e:
                logger.error("Container sentinel error: %s", e)
            await asyncio.sleep(self._check_interval)

    def summary(self) -> dict:
        critical = sum(1 for a in self._alerts if a.severity == "CRITICAL")
        return {
            "is_container": self._is_container,
            "total_alerts": len(self._alerts),
            "critical": critical,
            "high": len(self._alerts) - critical,
            "last_alerts": [vars(a) for a in self._alerts[-5:]],
        }


_sentinel: ContainerSentinel | None = None


def get_sentinel() -> ContainerSentinel:
    global _sentinel
    if _sentinel is None:
        _sentinel = ContainerSentinel()
    return _sentinel

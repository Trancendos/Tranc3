"""Honeypot endpoints and canary token deception layer for Tranc3."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass
class CanaryToken:
    token_id: str
    token_type: str
    value: str
    created_at: float
    triggered: bool = False
    triggered_at: float | None = None
    triggered_by: str | None = None


class HoneypotManager:
    def __init__(self) -> None:
        self._canaries: dict[str, CanaryToken] = {}
        self._honeypot_paths: set[str] = set()
        self._alerts: list[dict] = []

    def create_canary_credential(self, label: str) -> CanaryToken:
        token = CanaryToken(
            token_id=secrets.token_hex(16),
            token_type="credential",
            value=f"TRANC3_CANARY_{secrets.token_hex(8).upper()}",
            created_at=time.time(),
        )
        self._canaries[token.token_id] = token
        return token

    def create_canary_url(self, label: str) -> CanaryToken:
        token = CanaryToken(
            token_id=secrets.token_hex(16),
            token_type="url",
            value=f"/api/v1/admin/canary/{secrets.token_hex(4)}",
            created_at=time.time(),
        )
        self._canaries[token.token_id] = token
        return token

    def create_canary_file_path(self, label: str) -> CanaryToken:
        token = CanaryToken(
            token_id=secrets.token_hex(16),
            token_type="file",
            value=f"/etc/tranc3/secret_{secrets.token_hex(4)}.key",
            created_at=time.time(),
        )
        self._canaries[token.token_id] = token
        return token

    def register_honeypot_path(self, path: str) -> None:
        self._honeypot_paths.add(path)

    def check_request(
        self,
        path: str,
        headers: dict,
        body: str,
        client_ip: str,
    ) -> dict | None:
        search_text = "\n".join([path, str(headers), body])
        for canary in self._canaries.values():
            if canary.value in search_text:
                now = time.time()
                canary.triggered = True
                canary.triggered_at = now
                canary.triggered_by = client_ip
                alert: dict = {
                    "token_id": canary.token_id,
                    "token_type": canary.token_type,
                    "triggered_at": now,
                    "triggered_by": client_ip,
                    "path": path,
                }
                self._alerts.append(alert)
                return alert
        return None

    def is_honeypot_path(self, path: str) -> bool:
        return path in self._honeypot_paths

    def get_alerts(self, since: float | None = None) -> list[dict]:
        if since is None:
            return list(self._alerts)
        return [a for a in self._alerts if a["triggered_at"] >= since]

    def export_tokens(self) -> list[dict]:
        result = []
        for canary in self._canaries.values():
            result.append(
                {
                    "token_id": canary.token_id,
                    "token_type": canary.token_type,
                    "value": canary.value[:8] + "...",
                    "created_at": canary.created_at,
                    "triggered": canary.triggered,
                    "triggered_at": canary.triggered_at,
                    "triggered_by": canary.triggered_by,
                }
            )
        return result

    def stats(self) -> dict:
        triggered = sum(1 for c in self._canaries.values() if c.triggered)
        return {
            "total_tokens": len(self._canaries),
            "triggered_count": triggered,
            "honeypot_paths_count": len(self._honeypot_paths),
        }

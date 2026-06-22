"""
Cryptex / The Ice Box — 8-Tier Adaptive Security Engine
=========================================================
Tier 1: Internal IOC lookup       (SQLite, always available)
Tier 2: Wazuh SIEM/EDR           REST API   (port 55000)
Tier 3: MISP threat intelligence  REST API   (port 80)
Tier 4: OpenVAS/Greenbone         REST API   (port 9390)
Tier 5: ClamAV antivirus          clamd socket/TCP
Tier 6: YARA rules engine         in-process (yara-python)
Tier 7: Semgrep SAST              subprocess (semgrep CLI)
Tier 8: Offline stub              always works

Selection uses ACO-inspired pheromone routing.
ThresholdGuard prevents exceeding per-engine rate limits.
CRYPTEX_FORCE_ENGINE env var overrides selection.

Lead AI: Renik (Cryptex) + Neonach (The Ice Box)
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

import config
from models import (
    EngineStatus,
    ScanEngine,
    ScanRequest,
    ScanResult,
    ScanStatus,
    ThreatSeverity,
)
from database import CryptexDatabase

logger = logging.getLogger("cryptex.service")

# ── Threshold Guard ────────────────────────────────────────────────────────────


class ThresholdGuard:
    """Sliding-window request counter with hard-stop enforcement."""

    def __init__(self, limit: int, window_seconds: int = 3600):
        self._limit = limit
        self._window = window_seconds
        self._timestamps: deque[float] = deque()

    def check(self) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._limit:
            return False
        self._timestamps.append(now)
        return True

    @property
    def current_count(self) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        return sum(1 for t in self._timestamps if t >= cutoff)

    @property
    def limit(self) -> int:
        return self._limit


# ── ACO Pheromone State ────────────────────────────────────────────────────────


class PheromoneState:
    _INIT = 0.8
    _MAX = 1.0
    _MIN = 0.1
    _SUCCESS_BUMP = 0.05
    _FAILURE_DROP = 0.15
    _TIMEOUT_DROP = 0.10

    def __init__(self, engines: List[str], decay: float = 0.9):
        self._decay = decay
        self._ph: Dict[str, float] = {e: self._INIT for e in engines}

    def select(self, candidates: List[str]) -> Optional[str]:
        if not candidates:
            return None
        import random
        total = sum(self._ph.get(e, self._MIN) for e in candidates)
        if total == 0:
            return candidates[0]
        r = random.uniform(0, total)
        cumulative = 0.0
        for e in candidates:
            cumulative += self._ph.get(e, self._MIN)
            if cumulative >= r:
                return e
        return candidates[-1]

    def success(self, engine: str) -> None:
        self._ph[engine] = min(self._MAX, self._ph.get(engine, self._INIT) + self._SUCCESS_BUMP)
        self._decay_others(engine)

    def failure(self, engine: str) -> None:
        self._ph[engine] = max(self._MIN, self._ph.get(engine, self._INIT) - self._FAILURE_DROP)

    def timeout(self, engine: str) -> None:
        self._ph[engine] = max(self._MIN, self._ph.get(engine, self._INIT) - self._TIMEOUT_DROP)

    def _decay_others(self, chosen: str) -> None:
        for e in self._ph:
            if e != chosen:
                self._ph[e] = max(self._MIN, self._ph[e] * self._decay)

    def get(self, engine: str) -> float:
        return self._ph.get(engine, self._INIT)

    def all(self) -> Dict[str, float]:
        return dict(self._ph)


# ── Tier 1: Internal IOC Lookup ────────────────────────────────────────────────


class InternalEngine:
    """Check target against local threat indicator database."""

    def __init__(self, db: CryptexDatabase):
        self._db = db

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        match = self._db.lookup_indicator(req.target)
        if match:
            return {
                "threat_found": True,
                "severity": match.get("severity", "unknown"),
                "findings": [{"source": "internal_db", "indicator": match}],
            }
        return {"threat_found": False, "severity": "info", "findings": []}


# ── Tier 2: Wazuh SIEM/EDR ────────────────────────────────────────────────────


class WazuhEngine:
    """Query Wazuh manager API for active alerts matching target."""

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        params = {"q": f"data.srcip={req.target}", "limit": 10, "sort": "-timestamp"}
        auth = (config.WAZUH_USER, config.WAZUH_PASS)
        async with httpx.AsyncClient(
            base_url=config.WAZUH_URL,
            auth=auth,
            verify=False,  # self-signed cert in dev
            timeout=20,
        ) as client:
            resp = await client.get("/alerts", params=params)
            resp.raise_for_status()
            data = resp.json()
            alerts = data.get("data", {}).get("affected_items", [])
            if alerts:
                max_level = max(int(a.get("rule", {}).get("level", 0)) for a in alerts)
                sev = "critical" if max_level >= 12 else "high" if max_level >= 9 else "medium"
                return {
                    "threat_found": True,
                    "severity": sev,
                    "findings": [
                        {
                            "rule_id": a.get("rule", {}).get("id"),
                            "description": a.get("rule", {}).get("description"),
                            "level": a.get("rule", {}).get("level"),
                        }
                        for a in alerts[:5]
                    ],
                }
            return {"threat_found": False, "severity": "info", "findings": []}


# ── Tier 3: MISP Threat Intelligence ──────────────────────────────────────────


class MISPEngine:
    """Search MISP for IOC matches."""

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        headers = {
            "Authorization": config.MISP_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {"returnFormat": "json", "value": req.target, "limit": 10}
        async with httpx.AsyncClient(
            base_url=config.MISP_URL,
            headers=headers,
            verify=False,
            timeout=20,
        ) as client:
            resp = await client.post("/attributes/restSearch", json=payload)
            resp.raise_for_status()
            data = resp.json()
            attrs = data.get("response", {}).get("Attribute", [])
            if attrs:
                return {
                    "threat_found": True,
                    "severity": "high",
                    "findings": [
                        {
                            "event_id": a.get("event_id"),
                            "type": a.get("type"),
                            "category": a.get("category"),
                            "comment": a.get("comment", ""),
                        }
                        for a in attrs[:5]
                    ],
                }
            return {"threat_found": False, "severity": "info", "findings": []}


# ── Tier 4: OpenVAS/Greenbone Vulnerability Scan ──────────────────────────────


class OpenVASEngine:
    """Trigger a Greenbone/OpenVAS scan via GMP XML API."""

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        auth = (config.OPENVAS_USER, config.OPENVAS_PASS)
        async with httpx.AsyncClient(
            base_url=config.OPENVAS_URL,
            auth=auth,
            verify=False,
            timeout=60,
        ) as client:
            # Create scan target
            target_resp = await client.post(
                "/gmp",
                content=f'<create_target><name>grid-{req.scan_id}</name><hosts>{req.target}</hosts></create_target>',
                headers={"Content-Type": "application/xml"},
            )
            target_resp.raise_for_status()
            # Parse target ID from XML response (simplified)
            t_xml = target_resp.text
            if 'status="201"' not in t_xml:
                raise RuntimeError(f"OpenVAS target creation failed: {t_xml[:200]}")
            findings = [{"type": "vulnerability_scan_triggered", "target": req.target}]
            return {"threat_found": False, "severity": "info", "findings": findings}


# ── Tier 5: ClamAV Antivirus ──────────────────────────────────────────────────


class ClamAVEngine:
    """Scan file content using clamd (TCP or socket)."""

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        try:
            import pyclamd  # type: ignore
        except ImportError:
            raise RuntimeError("pyclamd not installed; add pyclamd to requirements-worker.txt")

        def _do_scan() -> Dict[str, Any]:
            if config.CLAMAV_SOCKET.startswith("/"):
                cd = pyclamd.ClamdUnixSocket(config.CLAMAV_SOCKET)
            else:
                host, port = config.CLAMAV_SOCKET.split(":")
                cd = pyclamd.ClamdNetworkSocket(host, int(port))
            if not cd.ping():
                raise RuntimeError("ClamAV daemon not responding")
            result = cd.scan_file(req.target)
            if result and any(v[0] == "FOUND" for v in result.values()):
                virus_names = [v[1] for v in result.values() if v[0] == "FOUND"]
                return {
                    "threat_found": True,
                    "severity": "critical",
                    "findings": [{"virus": v} for v in virus_names],
                }
            return {"threat_found": False, "severity": "info", "findings": []}

        return await asyncio.to_thread(_do_scan)


# ── Tier 6: YARA Rules Engine ─────────────────────────────────────────────────


class YARAEngine:
    """Match file/content against YARA rules directory."""

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        def _do_scan() -> Dict[str, Any]:
            try:
                import yara  # type: ignore
            except ImportError:
                raise RuntimeError("yara-python not installed; add yara-python to requirements-worker.txt")

            import os
            rules_dir = config.YARA_RULES_DIR
            if not os.path.isdir(rules_dir):
                return {"threat_found": False, "severity": "info", "findings": [], "note": "No YARA rules dir"}
            rule_files = {
                f: os.path.join(rules_dir, f)
                for f in os.listdir(rules_dir)
                if f.endswith(".yar") or f.endswith(".yara")
            }
            if not rule_files:
                return {"threat_found": False, "severity": "info", "findings": []}
            rules = yara.compile(filepaths=rule_files)
            matches = rules.match(req.target)
            if matches:
                return {
                    "threat_found": True,
                    "severity": "high",
                    "findings": [{"rule": m.rule, "tags": m.tags, "meta": m.meta} for m in matches],
                }
            return {"threat_found": False, "severity": "info", "findings": []}

        return await asyncio.to_thread(_do_scan)


# ── Tier 7: Semgrep SAST ──────────────────────────────────────────────────────


class SemgrepEngine:
    """Run Semgrep SAST on a file or directory (subprocess, never exec())."""

    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        def _do_scan() -> Dict[str, Any]:
            cmd = [
                "semgrep",
                "--config=auto",
                "--json",
                "--no-git-ignore",
                "--quiet",
                req.target,
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except FileNotFoundError:
                raise RuntimeError("semgrep not found; install semgrep CLI")
            except subprocess.TimeoutExpired:
                raise RuntimeError("Semgrep scan timed out")

            try:
                data = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                raise RuntimeError(f"Semgrep returned non-JSON: {proc.stdout[:200]}")

            results = data.get("results", [])
            errors = data.get("errors", [])
            if errors and not results:
                raise RuntimeError(f"Semgrep errors: {errors[:2]}")

            findings = [
                {
                    "check_id": r.get("check_id"),
                    "path": r.get("path"),
                    "line": r.get("start", {}).get("line"),
                    "message": r.get("extra", {}).get("message", ""),
                    "severity": r.get("extra", {}).get("severity", "WARNING"),
                }
                for r in results
            ]
            severity_map = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
            max_sev = "info"
            for f in findings:
                s = severity_map.get(f.get("severity", "INFO"), "info")
                if s == "high":
                    max_sev = "high"
                    break
                elif s == "medium" and max_sev == "info":
                    max_sev = "medium"
            return {
                "threat_found": bool(findings),
                "severity": max_sev,
                "findings": findings[:20],
            }

        return await asyncio.to_thread(_do_scan)


# ── Tier 8: Offline Stub ───────────────────────────────────────────────────────


class OfflineEngine:
    async def scan(self, req: ScanRequest) -> Dict[str, Any]:
        return {
            "threat_found": False,
            "severity": "info",
            "findings": [],
            "note": "Offline stub — no external security engine available",
        }


# ── Router ─────────────────────────────────────────────────────────────────────

_TIER_ORDER = [
    ScanEngine.wazuh,
    ScanEngine.misp,
    ScanEngine.openvas,
    ScanEngine.clamav,
    ScanEngine.yara,
    ScanEngine.suricata,
    ScanEngine.semgrep,
    ScanEngine.offline,
]

_THRESHOLDS = {
    ScanEngine.wazuh: config.THRESHOLD_WAZUH,
    ScanEngine.misp: config.THRESHOLD_MISP,
    ScanEngine.openvas: config.THRESHOLD_OPENVAS,
    ScanEngine.clamav: config.THRESHOLD_CLAMAV,
    ScanEngine.yara: config.THRESHOLD_YARA,
    ScanEngine.suricata: config.THRESHOLD_SURICATA,
    ScanEngine.semgrep: config.THRESHOLD_SEMGREP,
    ScanEngine.offline: 999999,
}


class SecurityEngineRouter:
    """
    8-tier adaptive security scanner with ACO pheromone routing,
    per-engine ThresholdGuard, and waterfall fallback.

    Lead AIs: Renik (Cryptex cyber defense) + Neonach (The Ice Box sandbox)
    """

    def __init__(self, db: CryptexDatabase):
        self.db = db
        self._pheromone = PheromoneState(
            [e.value for e in _TIER_ORDER], decay=config.ACO_DECAY
        )
        self._guards: Dict[str, ThresholdGuard] = {
            e.value: ThresholdGuard(_THRESHOLDS[e], config.THRESHOLD_WINDOW_SECONDS)
            for e in _TIER_ORDER
        }
        self._engines: Dict[str, Any] = {
            ScanEngine.wazuh.value: WazuhEngine(),
            ScanEngine.misp.value: MISPEngine(),
            ScanEngine.openvas.value: OpenVASEngine(),
            ScanEngine.clamav.value: ClamAVEngine(),
            ScanEngine.yara.value: YARAEngine(),
            ScanEngine.suricata.value: OfflineEngine(),  # Suricata reads log files; offline until mounted
            ScanEngine.semgrep.value: SemgrepEngine(),
            ScanEngine.offline.value: OfflineEngine(),
        }
        self._internal = InternalEngine(db)
        self._health: Dict[str, bool] = {e.value: True for e in _TIER_ORDER}

    def engine_statuses(self) -> List[EngineStatus]:
        return [
            EngineStatus(
                engine=e.value,
                healthy=self._health[e.value],
                pheromone=round(self._pheromone.get(e.value), 3),
                requests_in_window=self._guards[e.value].current_count,
                threshold=self._guards[e.value].limit,
                blocked=self._guards[e.value].current_count >= self._guards[e.value].limit,
            )
            for e in _TIER_ORDER
        ]

    def _available_engines(self, preferred: Optional[str] = None) -> List[str]:
        available = []
        for e in _TIER_ORDER:
            ev = e.value
            if not self._health[ev]:
                continue
            if self._guards[ev].current_count >= self._guards[ev].limit:
                logger.warning("Engine %s at threshold, skipping", ev)
                continue
            available.append(ev)
        if preferred and preferred in available:
            available = [preferred] + [e for e in available if e != preferred]
        return available

    async def scan(self, req: ScanRequest) -> ScanResult:
        result = ScanResult(
            scan_id=req.scan_id,
            status=ScanStatus.running,
            started_at=datetime.now(timezone.utc),
        )
        self.db.save_result(result)

        # Always check internal first (no threshold cost)
        try:
            internal_hit = await self._internal.scan(req)
            if internal_hit.get("threat_found"):
                result.threat_found = True
                result.severity = ThreatSeverity(internal_hit.get("severity", "unknown"))
                result.findings = internal_hit.get("findings", [])
                result.engine_used = "internal"
                result.status = ScanStatus.completed
                result.completed_at = datetime.now(timezone.utc)
                self.db.save_result(result)
                return result
        except Exception as e:
            logger.warning("Internal engine error: %s", e)

        forced = config.FORCE_ENGINE
        preferred = forced or (req.preferred_engine.value if req.preferred_engine else None)
        candidates = (
            [forced] if forced and forced in self._engines
            else self._available_engines(preferred)
        )
        if not candidates:
            candidates = [ScanEngine.offline.value]

        top = candidates[:3]
        chosen = self._pheromone.select(top) if len(top) > 1 else top[0]
        fallback_order = [chosen] + [c for c in candidates if c != chosen]

        last_error = "no engines attempted"
        for engine_name in fallback_order:
            engine = self._engines[engine_name]
            guard = self._guards[engine_name]
            if not guard.check():
                logger.warning("Engine %s threshold hit during attempt, skipping", engine_name)
                continue

            logger.info("Attempting security engine: %s", engine_name)
            t0 = time.monotonic()
            try:
                output = await asyncio.wait_for(engine.scan(req), timeout=120)
                elapsed = time.monotonic() - t0
                self._pheromone.success(engine_name)
                self._health[engine_name] = True
                logger.info("Engine %s completed in %.2fs", engine_name, elapsed)

                result.engine_used = engine_name
                result.threat_found = output.get("threat_found", False)
                result.severity = ThreatSeverity(output.get("severity", "info"))
                result.findings = output.get("findings", [])
                result.raw_output = output
                result.status = ScanStatus.completed
                result.completed_at = datetime.now(timezone.utc)
                self.db.save_result(result)
                return result

            except asyncio.TimeoutError:
                self._pheromone.timeout(engine_name)
                self._health[engine_name] = False
                last_error = f"Engine {engine_name} timed out"
                logger.warning("%s", last_error)

            except Exception as exc:
                self._pheromone.failure(engine_name)
                self._health[engine_name] = False
                last_error = f"Engine {engine_name} failed: {exc}"
                logger.warning("%s", last_error)

        result.engine_used = ScanEngine.offline.value
        result.status = ScanStatus.failed
        result.error_message = f"All engines exhausted. Last error: {last_error}"
        result.completed_at = datetime.now(timezone.utc)
        self.db.save_result(result)
        return result

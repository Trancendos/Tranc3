"""
Unified Platform Layer Controller — database, knowledge, blob, hosting, frontend.

Rotates among configured backends with health probes and cooldowns (same pattern as
AdaptiveProviderRotator). Does not perform DNS cutover; exposes active backend and
health for operators and /adaptive/layers API.

Environment:
  PLATFORM_LAYER_ROTATION_ENABLED=true
  PLATFORM_DB_URLS=name=url,name2=url2  (comma-separated, overrides yaml)
  PLATFORM_BLOB_BACKENDS=fly_volume,local_fs,ipfs
  PLATFORM_KNOWLEDGE_BACKENDS=faiss_local,hf_embeddings
  PLATFORM_API_UPSTREAMS=https://tranc3-backend.fly.dev,...
  PLATFORM_FRONTEND_ORIGINS=arcadia_static,citadel_static
  LAYER_ROTATION_COOLDOWN_SECONDS=300
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from src.platform.infrastructure_mode import get_infrastructure_mode

logger = logging.getLogger("tranc3.platform.layer_rotator")

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_FILE = _ROOT / "config" / "platform" / "layer_rotation.yaml"


class PlatformLayer(str, Enum):
    DATABASE = "database"
    KNOWLEDGE = "knowledge"
    BLOB = "blob"
    HOSTING = "hosting"
    FRONTEND = "frontend"


@dataclass
class BackendHealth:
    name: str
    available: bool = False
    failures: int = 0
    last_check_at: float = 0.0
    cooldown_until: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "failures": self.failures,
            "cooldown_until": self.cooldown_until,
            "detail": self.detail,
        }


@dataclass
class LayerRotationState:
    layer: str
    backends: list[str]
    index: int = 0
    health: dict[str, BackendHealth] = field(default_factory=dict)
    last_rotation_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        active = self.backends[self.index] if self.backends else None
        return {
            "layer": self.layer,
            "backends": self.backends,
            "active_index": self.index,
            "active_backend": active,
            "last_rotation_at": self.last_rotation_at,
            "health": {k: v.to_dict() for k, v in self.health.items()},
        }


def _load_config() -> dict[str, Any]:
    if not _CONFIG_FILE.is_file():
        return {}
    try:
        return yaml.safe_load(_CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("layer_rotation.yaml load failed: %s", exc)
        return {}


def _parse_named_list(raw: str) -> list[tuple[str, str]]:
    """Parse 'primary=postgresql://...,replica=...' or comma URLs."""
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part and not part.startswith("http"):
            name, _, value = part.partition("=")
            out.append((name.strip(), value.strip()))
        else:
            out.append((f"backend_{len(out)}", part))
    return out


def _env_source_value(source: str) -> str | None:
    if not source.startswith("env:"):
        return None
    key = source[4:].strip()
    return os.environ.get(key) or None


class PlatformLayerRotator:
    """Health-aware rotation across platform tiers."""

    def __init__(self) -> None:
        self._cfg = _load_config()
        self._cooldown = float(
            os.environ.get(
                "LAYER_ROTATION_COOLDOWN_SECONDS",
                self._cfg.get("cooldown_seconds", 300),
            ),
        )
        self._states: dict[str, LayerRotationState] = {}
        self._rebuild_all()
        logger.info(
            "Platform layer rotator mode=%s layers=%s",
            get_infrastructure_mode().value,
            list(self._states.keys()),
        )

    def _rebuild_all(self) -> None:
        self._states = {}
        for layer in PlatformLayer:
            self._states[layer.value] = self._build_layer(layer.value)

    def _build_layer(self, layer: str) -> LayerRotationState:
        backends = self._resolve_backends(layer)
        health = {b: BackendHealth(name=b) for b in backends}
        return LayerRotationState(layer=layer, backends=backends, health=health)

    def _resolve_backends(self, layer: str) -> list[str]:
        layers_cfg = self._cfg.get("layers") or {}
        layer_cfg = layers_cfg.get(layer) or {}
        env_key = layer_cfg.get("env_urls") or layer_cfg.get("env_chain")
        if env_key:
            raw = os.environ.get(env_key, "").strip()
            if raw:
                if layer == PlatformLayer.DATABASE.value and ("://" in raw or "=" in raw):
                    return [name for name, _ in _parse_named_list(raw)]
                return [b.strip() for b in raw.split(",") if b.strip()]

        if layer == PlatformLayer.DATABASE.value:
            names: list[str] = []
            for cand in layer_cfg.get("candidates") or []:
                src = cand.get("source", "")
                val = _env_source_value(src) if isinstance(src, str) else None
                if val or not cand.get("optional"):
                    names.append(str(cand.get("name", "primary")))
            return names or ["primary"]

        candidates = layer_cfg.get("candidates") or []
        if isinstance(candidates, list) and candidates:
            if isinstance(candidates[0], dict):
                return [str(c.get("name", c)) for c in candidates]
            return [str(c) for c in candidates]

        defaults: dict[str, list[str]] = {
            PlatformLayer.KNOWLEDGE.value: ["faiss_local", "offline"],
            PlatformLayer.BLOB.value: ["local_fs"],
            PlatformLayer.HOSTING.value: ["fly_tranc3_backend"],
            PlatformLayer.FRONTEND.value: ["arcadia_static"],
        }
        return defaults.get(layer, ["default"])

    def _probe_database(self, name: str) -> BackendHealth:
        h = BackendHealth(name=name)
        url = self._database_url_for(name)
        if not url:
            h.detail = "no_url_configured"
            h.available = False
            return h
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(
                url,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 3},
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            h.available = True
            h.detail = "ok"
        except Exception as exc:
            h.available = False
            h.detail = str(exc)[:120]
        h.last_check_at = time.monotonic()
        return h

    def _database_url_for(self, name: str) -> str | None:
        raw = os.environ.get("PLATFORM_DB_URLS", "").strip()
        if raw:
            for n, url in _parse_named_list(raw):
                if n == name:
                    return url
        layers_cfg = self._cfg.get("layers") or {}
        for cand in (layers_cfg.get("database") or {}).get("candidates") or []:
            if str(cand.get("name")) == name:
                return _env_source_value(str(cand.get("source", "")))
        if name == "primary":
            return os.environ.get("DATABASE_URL")
        if name == "sqlite_fallback":
            return os.environ.get("SQLITE_FALLBACK_URL")
        return None

    def _probe_http_upstream(self, name: str, base_url: str | None) -> BackendHealth:
        h = BackendHealth(name=name)
        if not base_url:
            h.detail = "no_url"
            return h
        health_url = base_url.rstrip("/") + "/health"
        try:
            import urllib.error
            import urllib.request

            parsed = urlparse(health_url)
            if parsed.scheme not in ("http", "https"):
                h.available = False
                h.detail = f"invalid_scheme:{parsed.scheme}"
                return h
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=4) as resp:  # nosec B310 — scheme validated above
                h.available = 200 <= resp.status < 400
                h.detail = f"http_{resp.status}"
        except urllib.error.HTTPError as exc:
            h.available = exc.code < 500
            h.detail = f"http_{exc.code}"
        except Exception as exc:
            h.available = False
            h.detail = str(exc)[:80]
        h.last_check_at = time.monotonic()
        return h

    def _hosting_url_for(self, name: str) -> str | None:
        raw = os.environ.get("PLATFORM_API_UPSTREAMS", "").strip()
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("http"):
                    label = urlparse(part).netloc or f"host_{name}"
                    if name in (label, part) or name.replace("_", "-") in part:
                        return part
                    if name == "fly_tranc3_backend" and "fly.dev" in part:
                        return part
                elif "=" in part:
                    n, _, url = part.partition("=")
                    if n.strip() == name:
                        return url.strip()
        defaults = {
            "fly_tranc3_backend": os.environ.get(
                "TRANC3_BACKEND_URL",
                "https://tranc3-backend.fly.dev",
            ),
            "oci_always_free": os.environ.get("OCI_API_UPSTREAM"),
            "cloudflare_edge": os.environ.get("CF_API_UPSTREAM"),
        }
        return defaults.get(name)

    def _probe_config_backend(self, layer: str, name: str) -> BackendHealth:
        """Availability from env / local paths (no network)."""
        h = BackendHealth(name=name)
        checks: dict[str, dict[str, str]] = {
            PlatformLayer.KNOWLEDGE.value: {
                "faiss_local": "KNOWLEDGE_FAISS_PATH",
                "hf_embeddings": "HF_API_KEY",
                "pinecone": "PINECONE_API_KEY",
                "qdrant_self_hosted": "QDRANT_URL",
                "offline": "",
            },
            PlatformLayer.BLOB.value: {
                "fly_volume": "FLY_VOLUME_PATH",
                "local_fs": "BLOB_LOCAL_PATH",
                "ipfs": "IPFS_API_URL",
                "legacy_r2": "R2_ACCOUNT_ID",
            },
            PlatformLayer.FRONTEND.value: {
                "arcadia_static": "ARCADIA_STATIC_URL",
                "citadel_static": "CITADEL_STATIC_URL",
                "cf_pages": "CF_PAGES_URL",
            },
        }
        layer_checks = checks.get(layer, {})
        env_key = layer_checks.get(name)
        if name == "offline":
            h.available = True
            h.detail = "always"
        elif env_key:
            val = os.environ.get(env_key, "").strip()
            if name in ("faiss_local", "local_fs"):
                path = val or str(_ROOT / "data" / name)
                h.available = Path(path).exists() or name == "local_fs"
                h.detail = "path_ok" if h.available else "path_missing"
            else:
                h.available = bool(val)
                h.detail = "configured" if h.available else "missing_env"
        elif layer == PlatformLayer.HOSTING.value:
            url = self._hosting_url_for(name)
            if url and url.startswith("http"):
                return self._probe_http_upstream(name, url)
            h.available = name == "fly_tranc3_backend"
            h.detail = "default_fly" if h.available else "not_configured"
        else:
            h.available = True
            h.detail = "assumed"
        h.last_check_at = time.monotonic()
        return h

    def refresh_layer(self, layer: str) -> None:
        state = self._states.get(layer)
        if not state:
            return
        now = time.monotonic()
        for name in state.backends:
            h = state.health.get(name) or BackendHealth(name=name)
            if layer == PlatformLayer.DATABASE.value:
                h = self._probe_database(name)
            elif layer == PlatformLayer.HOSTING.value:
                url = self._hosting_url_for(name)
                h = (
                    self._probe_http_upstream(name, url)
                    if url and url.startswith("http")
                    else self._probe_config_backend(layer, name)
                )
            else:
                h = self._probe_config_backend(layer, name)
            if h.cooldown_until and now >= h.cooldown_until:
                h.cooldown_until = 0.0
                h.failures = 0
            state.health[name] = h

    def refresh_all(self) -> None:
        for layer in self._states:
            self.refresh_layer(layer)

    def active_backend(self, layer: str) -> str | None:
        self.refresh_layer(layer)
        state = self._states.get(layer)
        if not state or not state.backends:
            return None
        now = time.monotonic()
        for _ in range(len(state.backends)):
            name = state.backends[state.index]
            h = state.health.get(name)
            if h and h.available and now >= h.cooldown_until:
                return name
            self._rotate_layer(layer)
        return state.backends[0] if state.backends else None

    def _rotate_layer(self, layer: str) -> None:
        state = self._states.get(layer)
        if not state or not state.backends:
            return
        state.index = (state.index + 1) % len(state.backends)
        state.last_rotation_at = time.monotonic()

    def record_failure(self, layer: str, backend: str) -> None:
        state = self._states.get(layer)
        if not state:
            return
        h = state.health.get(backend)
        if not h:
            return
        h.failures += 1
        if h.failures >= 2:
            h.cooldown_until = time.monotonic() + self._cooldown
            h.available = False
            logger.warning("Layer %s backend %s on cooldown", layer, backend)
        self._rotate_layer(layer)

    def force_rotate(self, layer: str | None = None) -> None:
        if layer:
            self._rotate_layer(layer)
        else:
            for ly in self._states:
                self._rotate_layer(ly)

    def get_active_database_url(self) -> str | None:
        name = self.active_backend(PlatformLayer.DATABASE.value)
        if not name:
            return os.environ.get("DATABASE_URL")
        return self._database_url_for(name)

    def status(self) -> dict[str, Any]:
        from src.platform.infrastructure_mode import infrastructure_status

        self.refresh_all()
        mode = get_infrastructure_mode().value
        policies = (self._cfg.get("mode_policies") or {}).get(mode, {})
        return {
            "enabled": os.environ.get("PLATFORM_LAYER_ROTATION_ENABLED", "true").lower()
            in ("1", "true", "yes"),
            "cooldown_seconds": self._cooldown,
            "infrastructure": infrastructure_status(),
            "mode_policy": policies,
            "layers": {
                ly: {
                    **state.to_dict(),
                    "active": self.active_backend(ly),
                }
                for ly, state in self._states.items()
            },
        }


_layer_rotator: PlatformLayerRotator | None = None


def get_layer_rotator() -> PlatformLayerRotator:
    global _layer_rotator
    if _layer_rotator is None:
        _layer_rotator = PlatformLayerRotator()
    return _layer_rotator


def layer_rotation_enabled() -> bool:
    cfg = _load_config()
    flag = os.environ.get(
        "PLATFORM_LAYER_ROTATION_ENABLED",
        cfg.get("enabled", True),
    )
    if str(flag).lower() in ("0", "false", "no"):
        return False
    return True

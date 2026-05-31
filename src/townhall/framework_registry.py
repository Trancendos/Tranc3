"""Load Town Hall framework registry from config/townhall/frameworks.yaml."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / "config" / "townhall" / "frameworks.yaml"


@dataclass
class FrameworkEntry:
    id: str
    name: str
    standard: str
    status: str
    domain: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "standard": self.standard,
            "status": self.status,
            "domain": self.domain,
        }


@dataclass
class RoomDefinition:
    id: str
    name: str
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "purpose": self.purpose}


@dataclass
class FrameworkRegistry:
    version: str = ""
    location: str = "The Town Hall"
    lead_ai: str = "Tristuran"
    frameworks: list[FrameworkEntry] = field(default_factory=list)
    rooms: list[RoomDefinition] = field(default_factory=list)

    def by_domain(self) -> dict[str, list[FrameworkEntry]]:
        out: dict[str, list[FrameworkEntry]] = {}
        for f in self.frameworks:
            out.setdefault(f.domain, []).append(f)
        return out

    def get(self, framework_id: str) -> FrameworkEntry | None:
        for f in self.frameworks:
            if f.id == framework_id:
                return f
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "location": self.location,
            "lead_ai": self.lead_ai,
            "framework_count": len(self.frameworks),
            "domains": {k: [x.to_dict() for x in v] for k, v in self.by_domain().items()},
            "rooms": [r.to_dict() for r in self.rooms],
        }


def load_framework_registry() -> FrameworkRegistry:
    reg = FrameworkRegistry()
    if not _CONFIG.is_file():
        logger.warning("frameworks.yaml missing at %s", _CONFIG)
        return reg
    try:
        data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("frameworks.yaml load failed: %s", exc)
        return reg

    reg.version = str(data.get("version", ""))
    reg.location = str(data.get("location", reg.location))
    reg.lead_ai = str(data.get("lead_ai", reg.lead_ai))

    domains = data.get("domains") or {}
    if isinstance(domains, dict):
        for domain, entries in domains.items():
            if not isinstance(entries, list):
                continue
            for item in entries:
                if not isinstance(item, dict):
                    continue
                reg.frameworks.append(
                    FrameworkEntry(
                        id=str(item.get("id", "")),
                        name=str(item.get("name", "")),
                        standard=str(item.get("standard", "")),
                        status=str(item.get("status", "planned")),
                        domain=str(domain),
                    )
                )

    for item in data.get("rooms") or []:
        if isinstance(item, dict):
            reg.rooms.append(
                RoomDefinition(
                    id=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    purpose=str(item.get("purpose", "")),
                )
            )
    return reg


_registry: FrameworkRegistry | None = None


def get_framework_registry() -> FrameworkRegistry:
    global _registry
    if _registry is None:
        _registry = load_framework_registry()
    return _registry

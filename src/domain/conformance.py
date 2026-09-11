"""Does every entity in the estate actually have what it is supposed to have?

The owner's checklist: registered in the CMDB, correct documentation, registry
values, environment variables checked, dependency associations, and a domain
model. Six properties, each of which is either true of a Location or not.

This module answers that per Location, by looking. The answer is a matrix, and
the useful part of it is the blanks -- a Location that is in the CMDB but has no
documentation and no registry entry is a Location nobody can operate, and that
is invisible in any view that only counts what is present.

One rule applies throughout, because it decides whether the report is worth
reading: **an unchecked property is reported as unchecked, never as passing.**
If the environment-variable scan cannot find a worker's source, that Location's
env column says "not checked" -- not "no problems found".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.production.yml"
REGISTRY = REPO / "config" / "estate" / "registry.yaml"
DOCS_SERVICES = REPO / "docs" / "services"
ENV_EXAMPLE = REPO / ".env.example"

#: `os.getenv("X")` / `os.environ["X"]` / `os.environ.get("X")`
_ENV_RE = re.compile(
    r"os\.(?:getenv\(\s*|environ\.get\(\s*|environ\[\s*)[\"']([A-Z][A-Z0-9_]*)[\"']"
)

UNCHECKED = "not checked"


@dataclass
class LocationConformance:
    location: str
    in_cmdb: bool = False
    documentation: Optional[str] = None
    registry_ref: Optional[str] = None
    #: Env vars the code reads, and which of them nothing declares.
    env_consumed: List[str] = field(default_factory=list)
    env_undeclared: List[str] = field(default_factory=list)
    env_status: str = UNCHECKED
    depends_on: List[str] = field(default_factory=list)
    dependency_status: str = UNCHECKED
    in_domain_model: bool = False

    def as_row(self) -> Dict[str, object]:
        return {
            "location": self.location,
            "in_cmdb": self.in_cmdb,
            "documentation": self.documentation or "",
            "registry_ref": self.registry_ref or "",
            "env_status": self.env_status,
            "env_consumed": len(self.env_consumed),
            "env_undeclared": self.env_undeclared,
            "dependency_status": self.dependency_status,
            "depends_on": self.depends_on,
            "in_domain_model": self.in_domain_model,
        }

    @property
    def complete(self) -> bool:
        return (
            self.in_cmdb
            and bool(self.documentation)
            and bool(self.registry_ref)
            and self.env_status == "ok"
            and self.dependency_status == "ok"
        )


def _registry_refs() -> Dict[str, str]:
    """Location name -> registry ref, from config/estate/registry.yaml."""
    if not REGISTRY.is_file():
        return {}
    try:
        import yaml
    except ImportError:  # pragma: no cover
        return {}
    document = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    # The registry's list lives under `components`. An earlier pass guessed
    # `entries`/`registry`, found neither, and reported 0 of 43 Locations as
    # having a registry value -- a clean, confident, entirely wrong finding, and
    # exactly the kind a conformance report must not produce. Every key the file
    # might use is tried, and an empty result now means the file changed shape.
    entries = []
    if isinstance(document, list):
        entries = document
    elif isinstance(document, dict):
        for key in ("components", "entries", "registry", "services"):
            value = document.get(key)
            if isinstance(value, list) and value:
                entries = value
                break
    refs: Dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") and entry.get("ref"):
            refs[str(entry["name"])] = str(entry["ref"])
    return refs


def _documentation_for(location: str) -> Optional[str]:
    """A docs pack for this Location, if one exists."""
    if not DOCS_SERVICES.is_dir():
        return None
    from src.domain.model import _snake

    slug = _snake(location).replace("_", "-")
    for candidate in DOCS_SERVICES.iterdir():
        if not candidate.is_dir():
            continue
        if candidate.name.lower().replace("_", "-") == slug:
            readme = candidate / "README.md"
            if readme.is_file():
                return readme.relative_to(REPO).as_posix()
            return candidate.relative_to(REPO).as_posix()
    return None


def _declared_env() -> set[str]:
    """Every env var something declares: .env.example plus compose environment."""
    declared: set[str] = set()
    if ENV_EXAMPLE.is_file():
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                declared.add(stripped.split("=", 1)[0].strip())
    if COMPOSE.is_file():
        try:
            import yaml

            document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
            for spec in (document.get("services") or {}).values():
                if not isinstance(spec, dict):
                    continue
                environment = spec.get("environment")
                if isinstance(environment, dict):
                    declared.update(str(k) for k in environment)
                elif isinstance(environment, list):
                    for item in environment:
                        declared.add(str(item).split("=", 1)[0].strip())
        except Exception:  # pragma: no cover - defensive
            pass
    return declared


def _consumed_env(worker_path: Optional[str]) -> Optional[List[str]]:
    """Env vars this Location's code reads. None when the path is not readable."""
    if not worker_path:
        return None
    root = REPO / worker_path
    if root.is_file():
        sources = [root]
    elif root.is_dir():
        sources = [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    else:
        return None
    if not sources:
        return None
    found: set[str] = set()
    for path in sources:
        try:
            found.update(_ENV_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:  # pragma: no cover
            continue
    return sorted(found)


def _dependencies_for(location: str) -> Optional[List[str]]:
    """Declared service dependencies, via the CMDB identity layer."""
    try:
        from src.cmdb import identity
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        services = identity.services_for_location(location)
    except Exception:
        return None
    if not services:
        return None
    deps: set[str] = set()
    for service in services:
        deps.update(service.depends_on_services or ())
    return sorted(deps)


def assess() -> List[LocationConformance]:
    from src.cmdb import identity
    from src.domain.build import build_model
    from src.entities.platform import PLATFORM_ENTITIES

    refs = _registry_refs()
    declared = _declared_env()
    model = build_model()
    modelled_modules = set(model.modules())

    try:
        mapped_locations = {s.location for s in identity._index().values() if s.location}
    except Exception:  # pragma: no cover - defensive
        mapped_locations = set()

    rows: List[LocationConformance] = []
    for name, entity in sorted(PLATFORM_ENTITIES.items()):
        row = LocationConformance(location=name)
        row.in_cmdb = name in mapped_locations
        row.documentation = _documentation_for(name)
        row.registry_ref = refs.get(name)
        row.in_domain_model = name in modelled_modules

        consumed = _consumed_env(entity.worker_path)
        if consumed is None:
            row.env_status = UNCHECKED
        else:
            row.env_consumed = consumed
            row.env_undeclared = [v for v in consumed if v not in declared]
            row.env_status = "ok" if not row.env_undeclared else "undeclared"

        deps = _dependencies_for(name)
        if deps is None:
            row.dependency_status = UNCHECKED
        else:
            row.depends_on = deps
            row.dependency_status = "ok" if deps else "none declared"

        rows.append(row)
    return rows


def summary() -> Dict[str, object]:
    rows = assess()
    return {
        "locations": len(rows),
        "in_cmdb": sum(1 for r in rows if r.in_cmdb),
        "with_documentation": sum(1 for r in rows if r.documentation),
        "with_registry_ref": sum(1 for r in rows if r.registry_ref),
        "env_ok": sum(1 for r in rows if r.env_status == "ok"),
        "env_undeclared": sum(1 for r in rows if r.env_status == "undeclared"),
        "env_unchecked": sum(1 for r in rows if r.env_status == UNCHECKED),
        "dependencies_declared": sum(1 for r in rows if r.dependency_status == "ok"),
        "dependencies_unchecked": sum(1 for r in rows if r.dependency_status == UNCHECKED),
        "complete_on_all_six": sum(1 for r in rows if r.complete),
    }

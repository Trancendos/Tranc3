"""Every container in the estate, what is inside it, and who answers for it.

Three questions the owner put, and the answers this module encodes:

**"Anything within a container needs to be logged, marking it within a container
and what's inside it."** A container becomes a Configuration Item here, with its
image, its build context, its mounts and its ports. What is *inside* it is not
guessed from the Dockerfile -- it comes from an SBOM, and a container with no
SBOM is reported as having no SBOM rather than as having no contents.

**"A few AIs have said mark these as SBOMs but I'm not sure."** They are half
right, and the distinction matters enough to state plainly. An SBOM is an
inventory of components: names, versions, licences, hashes. A Configuration Item
is a managed thing: it has an owner, a lifecycle state, relationships, and
changes that have to be authorised. They answer different questions, so one
cannot replace the other -- an SBOM has no owner and no jurisdiction, and a CI
with no component list cannot tell you whether CVE-2026-x is in your estate.
The model here uses both: the container is the CI, and the SBOM is the evidence
that populates its contents. `sbom_ref` is the join.

**"All containerisations should have a shared jurisdiction."** Encoded as two
fields, not one. `jurisdiction` is the Location whose code the container runs --
accountable for what it does. `custodian` is always The Ice Box -- accountable
for that it runs safely: sandbox isolation, resource limits, stability of the
VM/container/pod. A container with no resolvable Location still has a custodian,
which is the point of splitting them: nothing is unowned in the dimension that
matters for containment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.production.yml"
SBOM_DIR = REPO / "docs" / "architecture" / "sbom"

#: The Location accountable for containment, per the owner's shared-jurisdiction
#: model. Every container has one regardless of whose code it runs.
CUSTODIAN = "The Ice Box"

_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.MULTILINE | re.IGNORECASE)
_USER_RE = re.compile(r"^\s*USER\s+(\S+)", re.MULTILINE | re.IGNORECASE)


@dataclass
class Container:
    """One containerised unit, as declared in compose."""

    service: str
    container_name: str = ""
    image: str = ""
    build_context: str = ""
    dockerfile: str = ""
    base_images: List[str] = field(default_factory=list)
    runs_as: str = ""
    ports: List[str] = field(default_factory=list)
    volumes: List[str] = field(default_factory=list)
    networks: List[str] = field(default_factory=list)
    #: "built" — we control the contents; "pulled" — a third-party image whose
    #: contents we do not choose and therefore need an SBOM for most of all.
    provenance: str = "pulled"
    jurisdiction: str = ""
    requirements: List[str] = field(default_factory=list)

    @property
    def ci_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.service.lower()).strip("-")
        return f"CI-CT-{slug}"

    @property
    def sbom_ref(self) -> str:
        """Where this container's SBOM lives, whether or not it exists yet."""
        return f"docs/architecture/sbom/{self.service}.cdx.json"

    @property
    def has_sbom(self) -> bool:
        return (REPO / self.sbom_ref).is_file()

    @property
    def runs_as_root(self) -> bool:
        """No USER directive means root. Recorded, because it is a containment fact."""
        return self.provenance == "built" and self.runs_as in ("", "root", "0")

    def as_ci(self) -> Dict[str, object]:
        return {
            "ci_id": self.ci_id,
            "ci_class": "Container",
            "name": self.service,
            "container_name": self.container_name,
            "image": self.image,
            "provenance": self.provenance,
            "base_images": self.base_images,
            "build_context": self.build_context,
            "dockerfile": self.dockerfile,
            # Shared jurisdiction, per the owner's model.
            "jurisdiction": self.jurisdiction or "_unrouted_",
            "custodian": CUSTODIAN,
            "runs_as": self.runs_as or "root (no USER directive)",
            "runs_as_root": self.runs_as_root,
            "ports": self.ports,
            "volumes": self.volumes,
            "networks": self.networks,
            "requirements": self.requirements,
            # The SBOM is referenced, never inlined: a CI that carries a few
            # hundred component rows stops being readable, and the SBOM is a
            # versioned artifact in its own right.
            "sbom_ref": self.sbom_ref,
            "sbom_present": self.has_sbom,
        }


def _location_for(path: str, ports: Optional[List[str]] = None) -> str:
    """Which Location's code this container runs.

    Two joins, because neither alone covers the estate. The build path matches a
    Location whose `worker_path` is that directory; the published port matches via
    `get_entity_for_port`, which catches the workers whose directory name and
    declared path disagree. Path first -- it is the stronger claim, since a port
    can be reassigned without moving any code.
    """
    try:
        from src.entities.platform import PLATFORM_ENTITIES, get_entity_for_port
    except Exception:  # pragma: no cover - defensive
        return ""

    if path:
        normalised = path.strip("./").rstrip("/")
        best, best_len = "", 0
        for name, entity in PLATFORM_ENTITIES.items():
            worker_path = (entity.worker_path or "").strip("./").rstrip("/")
            if worker_path and normalised.startswith(worker_path) and len(worker_path) > best_len:
                best, best_len = name, len(worker_path)
        if best:
            return best

    for mapping in ports or []:
        # compose port shapes: "8046:8046", "127.0.0.1:8046:8046", "8046"
        parts = str(mapping).split(":")
        for part in parts:
            if part.isdigit():
                entity = get_entity_for_port(int(part))
                if entity is not None:
                    return entity.location
    return ""


def _dockerfile_facts(dockerfile: str) -> tuple[List[str], str]:
    """Base images and the final USER, read from the Dockerfile."""
    path = REPO / dockerfile if dockerfile else None
    if not path or not path.is_file():
        return [], ""
    text = path.read_text(encoding="utf-8", errors="replace")
    bases = _FROM_RE.findall(text)
    users = _USER_RE.findall(text)
    return bases, (users[-1] if users else "")


def _requirements_near(build_context: str, dockerfile: str) -> List[str]:
    """Requirement manifests shipped with this container."""
    found: List[str] = []
    # The Dockerfile's own directory, not the build context. Nearly every service
    # here builds with `context: .` (the repo root), so using the context listed
    # every root-level requirements file as though it shipped inside each of the
    # 88 images -- an inventory that is wrong in the direction that matters, since
    # it would attribute the whole repo's dependencies to every container.
    candidates = [str(Path(dockerfile).parent)] if dockerfile else []
    if build_context and build_context.strip("./") not in ("", "."):
        candidates.append(build_context)
    for candidate in candidates:
        if not candidate:
            continue
        directory = REPO / candidate.strip("./")
        if not directory.is_dir():
            continue
        for manifest in sorted(directory.glob("requirements*.txt")):
            found.append(manifest.relative_to(REPO).as_posix())
        for manifest in sorted(directory.glob("package.json")):
            found.append(manifest.relative_to(REPO).as_posix())
    return sorted(set(found))


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, dict):
        return [str(k) for k in value]
    return [str(value)]


def discover() -> List[Container]:
    """Every compose service, as a container record."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - yaml is a hard dependency here
        return []
    if not COMPOSE.is_file():
        return []

    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    services = document.get("services") or {}

    containers: List[Container] = []
    for name, spec in sorted(services.items()):
        if not isinstance(spec, dict):
            continue
        build = spec.get("build")
        build_context, dockerfile = "", ""
        if isinstance(build, dict):
            build_context = str(build.get("context", "") or "")
            dockerfile = str(build.get("dockerfile", "") or "")
        elif isinstance(build, str):
            build_context = build

        bases, runs_as = _dockerfile_facts(dockerfile)
        # A build context of "." with a worker-specific Dockerfile is the estate's
        # normal shape, so the Dockerfile's directory identifies the Location far
        # more often than the context does.
        owner_path = str(Path(dockerfile).parent) if dockerfile else build_context

        containers.append(
            Container(
                service=name,
                container_name=str(spec.get("container_name", "") or ""),
                image=str(spec.get("image", "") or ""),
                build_context=build_context,
                dockerfile=dockerfile,
                base_images=bases,
                runs_as=runs_as,
                ports=_as_list(spec.get("ports")),
                volumes=_as_list(spec.get("volumes")),
                networks=_as_list(spec.get("networks")),
                provenance="built" if build else "pulled",
                jurisdiction=_location_for(owner_path, _as_list(spec.get("ports"))),
                requirements=_requirements_near(build_context, dockerfile),
            )
        )
    return containers


def summary() -> Dict[str, object]:
    containers = discover()
    built = [c for c in containers if c.provenance == "built"]
    pulled = [c for c in containers if c.provenance == "pulled"]
    return {
        "total": len(containers),
        "built": len(built),
        "pulled": len(pulled),
        "with_sbom": sum(1 for c in containers if c.has_sbom),
        "without_sbom": sum(1 for c in containers if not c.has_sbom),
        "unrouted_jurisdiction": sum(1 for c in containers if not c.jurisdiction),
        "running_as_root": sum(1 for c in built if c.runs_as_root),
        "custodian": CUSTODIAN,
    }

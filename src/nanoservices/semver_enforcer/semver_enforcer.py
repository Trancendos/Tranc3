"""Semantic Versioning Enforcer — Phase 12

Automated version management with semver compliance,
changelog generation, and compatibility verification.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    PATCH = "patch"  # Bug fix, backward compatible
    MINOR = "minor"  # New feature, backward compatible
    MAJOR = "major"  # Breaking change
    PRERELEASE = "prerelease"
    BUILD = "build"


class CompatibilityLevel(Enum):
    FULL = "full"  # No breaking changes
    PARTIAL = "partial"  # Some features deprecated
    BREAKING = "breaking"  # Breaking changes present
    UNKNOWN = "unknown"


@dataclass
class SemVer:
    major: int = 0
    minor: int = 1
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        match = re.match(
            r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$", version_str.strip()
        )
        if not match:
            raise ValueError(f"Invalid semver: {version_str}")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
            build=match.group(5) or "",
        )

    @property
    def string(self) -> str:
        v = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            v += f"-{self.prerelease}"
        if self.build:
            v += f"+{self.build}"
        return v

    def bump(self, change_type: ChangeType) -> "SemVer":
        if change_type == ChangeType.MAJOR:
            return SemVer(self.major + 1, 0, 0)
        if change_type == ChangeType.MINOR:
            return SemVer(self.major, self.minor + 1, 0)
        if change_type == ChangeType.PATCH:
            return SemVer(self.major, self.minor, self.patch + 1)
        if change_type == ChangeType.PRERELEASE:
            return SemVer(self.major, self.minor, self.patch, prerelease=f"rc.{int(time.time())}")
        return SemVer(self.major, self.minor, self.patch + 1, build=f"b.{int(time.time())}")

    def is_compatible_with(self, other: "SemVer") -> CompatibilityLevel:
        if self.major == 0:
            return CompatibilityLevel.BREAKING  # Pre-1.0: no stability guarantee
        if self.major != other.major:
            return CompatibilityLevel.BREAKING
        if self.minor >= other.minor:
            return CompatibilityLevel.FULL
        if self.minor < other.minor:
            return CompatibilityLevel.PARTIAL
        return CompatibilityLevel.UNKNOWN

    def __lt__(self, other: "SemVer") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))


@dataclass
class ChangeRecord:
    change_type: ChangeType
    description: str
    component: str = ""
    pr_number: Optional[int] = None
    author: str = ""
    timestamp: float = field(default_factory=time.time)
    breaking_details: str = ""
    migration_notes: str = ""


@dataclass
class ReleaseRecord:
    version: SemVer
    previous_version: SemVer
    changes: List[ChangeRecord] = field(default_factory=list)
    compatibility: CompatibilityLevel = CompatibilityLevel.FULL
    release_date: float = field(default_factory=time.time)
    changelog: str = ""


class ChangelogGenerator:
    """Generates changelogs from change records."""

    def generate(self, release: ReleaseRecord) -> str:
        lines = [
            f"## {release.version.string}",
            f"Released: {time.strftime('%Y-%m-%d', time.gmtime(release.release_date))}",
            f"Compatibility: {release.compatibility.value}",
            "",
        ]

        breaking = [c for c in release.changes if c.change_type == ChangeType.MAJOR]
        features = [c for c in release.changes if c.change_type == ChangeType.MINOR]
        fixes = [c for c in release.changes if c.change_type == ChangeType.PATCH]

        if breaking:
            lines.append("### ⚠️ BREAKING CHANGES")
            for c in breaking:
                lines.append(f"- **{c.component}**: {c.description}")
                if c.migration_notes:
                    lines.append(f"  - Migration: {c.migration_notes}")
            lines.append("")

        if features:
            lines.append("### ✨ Features")
            for c in features:
                lines.append(f"- **{c.component}**: {c.description}")
            lines.append("")

        if fixes:
            lines.append("### 🐛 Bug Fixes")
            for c in fixes:
                lines.append(f"- **{c.component}**: {c.description}")
            lines.append("")

        return "\n".join(lines)


class SemVerEnforcer:
    """Enforces semantic versioning rules across the codebase."""

    def __init__(self, current_version: str = "0.1.0"):
        self._current = SemVer.parse(current_version)
        self._pending_changes: List[ChangeRecord] = []
        self._releases: List[ReleaseRecord] = []
        self._changelog_gen = ChangelogGenerator()
        self._component_versions: Dict[str, SemVer] = {}

    @property
    def current_version(self) -> SemVer:
        return self._current

    def register_component(self, name: str, version: str) -> None:
        self._component_versions[name] = SemVer.parse(version)

    def record_change(self, change: ChangeRecord) -> SemVer:
        self._pending_changes.append(change)
        # Determine the next version based on the most impactful change
        max_change = ChangeType.PATCH
        for c in self._pending_changes:
            if c.change_type == ChangeType.MAJOR:
                max_change = ChangeType.MAJOR
                break
            if c.change_type == ChangeType.MINOR and max_change == ChangeType.PATCH:
                max_change = ChangeType.MINOR
        return self._current.bump(max_change)

    def propose_release(self) -> Optional[ReleaseRecord]:
        if not self._pending_changes:
            return None

        max_change = ChangeType.PATCH
        for c in self._pending_changes:
            if c.change_type == ChangeType.MAJOR:
                max_change = ChangeType.MAJOR
                break
            if c.change_type == ChangeType.MINOR and max_change == ChangeType.PATCH:
                max_change = ChangeType.MINOR

        new_version = self._current.bump(max_change)
        compat = self._current.is_compatible_with(new_version)

        release = ReleaseRecord(
            version=new_version,
            previous_version=self._current,
            changes=list(self._pending_changes),
            compatibility=compat,
            changelog="",
        )
        release.changelog = self._changelog_gen.generate(release)
        return release

    def release(self, release: ReleaseRecord) -> None:
        self._current = release.version
        self._releases.append(release)
        self._pending_changes.clear()
        logger.info(
            "Released v%s (%d changes, compatibility: %s)",
            release.version.string,
            len(release.changes),
            release.compatibility.value,
        )

    def get_releases(self, limit: int = 20) -> List[ReleaseRecord]:
        return self._releases[-limit:]

    def validate_version_range(self, min_version: str, max_version: str) -> bool:
        try:
            min_v = SemVer.parse(min_version)
            max_v = SemVer.parse(max_version)
            return min_v < max_v
        except ValueError:
            return False

    def get_component_compatibility(self, component_a: str, component_b: str) -> CompatibilityLevel:
        va = self._component_versions.get(component_a)
        vb = self._component_versions.get(component_b)
        if not va or not vb:
            return CompatibilityLevel.UNKNOWN
        return va.is_compatible_with(vb)


class SemVerEnforcerService:
    """Main service: automated version management."""

    def __init__(self, current_version: str = "0.1.0"):
        self._enforcer = SemVerEnforcer(current_version)

    def initialize(self) -> None:
        # Register all nanoservice components
        components = [
            ("nsa_broker", "1.0.0"),
            ("nsa_client", "1.0.0"),
            ("nsa_registry", "1.0.0"),
            ("dnf_orchestrator", "1.0.0"),
            ("shi_gateway", "1.0.0"),
            ("quantum_solver", "1.0.0"),
            ("genetic_optimizer", "1.0.0"),
            ("fmd_distiller", "1.0.0"),
            ("zkp_service", "1.0.0"),
            ("did_identity", "1.0.0"),
            ("he_service", "1.0.0"),
            ("mpc_service", "1.0.0"),
            ("pqc_service", "1.0.0"),
            ("wasm_edge", "1.0.0"),
            ("neural_symbolic", "1.0.0"),
            ("temporal_reasoning", "1.0.0"),
            ("neuromorphic", "1.0.0"),
            ("bio_digital_interface", "1.0.0"),
        ]
        for name, version in components:
            self._enforcer.register_component(name, version)

        logger.info(
            "SemVerEnforcerService initialized with %d components at v%s",
            len(components),
            self._enforcer.current_version.string,
        )

    def record_change(
        self,
        change_type: ChangeType,
        description: str,
        component: str = "",
        author: str = "",
        migration_notes: str = "",
    ) -> SemVer:
        change = ChangeRecord(
            change_type=change_type,
            description=description,
            component=component,
            author=author,
            migration_notes=migration_notes,
        )
        return self._enforcer.record_change(change)

    def propose_release(self) -> Optional[ReleaseRecord]:
        return self._enforcer.propose_release()

    def release(self, release: ReleaseRecord) -> None:
        self._enforcer.release(release)

    def get_current_version(self) -> str:
        return self._enforcer.current_version.string

    def get_releases(self, limit: int = 20) -> List[ReleaseRecord]:
        return self._enforcer.get_releases(limit)

    def check_compatibility(self, component_a: str, component_b: str) -> CompatibilityLevel:
        return self._enforcer.get_component_compatibility(component_a, component_b)

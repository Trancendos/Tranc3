"""API Version Negotiator — Phase 12

Backward-compatible API evolution with content negotiation,
version routing, and deprecation management.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VersionStatus(Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    RETIRED = "retired"


class NegotiationStrategy(Enum):
    EXACT = "exact"
    LATEST_COMPATIBLE = "latest_compatible"
    FALLBACK = "fallback"


@dataclass
class APIVersion:
    major: int
    minor: int
    patch: int = 0
    status: VersionStatus = VersionStatus.ACTIVE
    release_date: float = field(default_factory=time.time)
    sunset_date: Optional[float] = None
    deprecation_date: Optional[float] = None
    changelog: str = ""
    breaking_changes: List[str] = field(default_factory=list)

    @property
    def semver(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def is_compatible_with(self, other: "APIVersion") -> bool:
        if self.major != other.major:
            return False
        return self.minor >= other.minor

    def __lt__(self, other: "APIVersion") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, APIVersion):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)


@dataclass
class APIEndpoint:
    path: str
    method: str = "GET"
    version: APIVersion = field(default_factory=lambda: APIVersion(1, 0, 0))
    handler_name: str = ""
    request_schema: Dict[str, Any] = field(default_factory=dict)
    response_schema: Dict[str, Any] = field(default_factory=dict)
    deprecated: bool = False
    replacement_path: Optional[str] = None


@dataclass
class NegotiationResult:
    endpoint: Optional[APIEndpoint] = None
    selected_version: Optional[APIVersion] = None
    status: str = "ok"
    warnings: List[str] = field(default_factory=list)
    fallback_used: bool = False


@dataclass
class DeprecationNotice:
    endpoint_path: str
    method: str
    version: str
    deprecation_date: float
    sunset_date: Optional[float]
    replacement: Optional[str]
    migration_guide: str = ""


class VersionRegistry:
    """Registry of all API versions and their endpoints."""

    def __init__(self):
        self._versions: Dict[str, List[APIVersion]] = {}  # service -> versions
        self._endpoints: Dict[
            str, Dict[str, APIEndpoint],
        ] = {}  # "METHOD path" -> {semver -> endpoint}

    def register_version(self, service_name: str, version: APIVersion) -> None:
        if service_name not in self._versions:
            self._versions[service_name] = []
        self._versions[service_name].append(version)
        self._versions[service_name].sort()

    def register_endpoint(self, endpoint: APIEndpoint) -> None:
        key = f"{endpoint.method} {endpoint.path}"
        if key not in self._endpoints:
            self._endpoints[key] = {}
        self._endpoints[key][endpoint.version.semver] = endpoint

    def get_endpoint(
        self, method: str, path: str, version: Optional[APIVersion] = None,
    ) -> Optional[APIEndpoint]:
        key = f"{method} {path}"
        endpoints = self._endpoints.get(key, {})
        if not endpoints:
            return None

        if version:
            # Exact match
            exact = endpoints.get(version.semver)
            if exact:
                return exact

            # Latest compatible
            compatible = [
                e
                for v, e in endpoints.items()
                if APIVersion(*map(int, v.split("."))).is_compatible_with(version)
            ]
            if compatible:
                return max(compatible, key=lambda e: e.version)

        # Return latest active version
        active = [e for e in endpoints.values() if e.version.status == VersionStatus.ACTIVE]
        if active:
            return max(active, key=lambda e: e.version)

        # Fallback to latest
        if endpoints:
            return max(endpoints.values(), key=lambda e: e.version)
        return None

    def get_deprecations(self) -> List[DeprecationNotice]:
        notices = []
        for key, versions in self._endpoints.items():
            method, path = key.split(" ", 1)
            for semver, endpoint in versions.items():
                if endpoint.deprecated or endpoint.version.status in (
                    VersionStatus.DEPRECATED,
                    VersionStatus.SUNSET,
                ):
                    notices.append(
                        DeprecationNotice(
                            endpoint_path=path,
                            method=method,
                            version=semver,
                            deprecation_date=endpoint.version.deprecation_date or time.time(),
                            sunset_date=endpoint.version.sunset_date,
                            replacement=endpoint.replacement_path,
                        ),
                    )
        return notices

    def get_all_versions(self, service_name: str) -> List[APIVersion]:
        return self._versions.get(service_name, [])


class APIVersionNegotiator:
    """Negotiates API versions between clients and services."""

    def __init__(self, strategy: NegotiationStrategy = NegotiationStrategy.LATEST_COMPATIBLE):
        self._registry = VersionRegistry()
        self._strategy = strategy
        self._negotiation_log: List[NegotiationResult] = []

    def register_version(self, service_name: str, version: APIVersion) -> None:
        self._registry.register_version(service_name, version)

    def register_endpoint(self, endpoint: APIEndpoint) -> None:
        self._registry.register_endpoint(endpoint)

    def negotiate(
        self,
        method: str,
        path: str,
        requested_version: Optional[str] = None,
        accept_header: Optional[str] = None,
    ) -> NegotiationResult:
        version = self._parse_version(requested_version, accept_header)
        endpoint = self._registry.get_endpoint(method, path, version)
        result = NegotiationResult()

        if not endpoint:
            result.status = "not_found"
            return result

        result.endpoint = endpoint
        result.selected_version = endpoint.version

        # Check deprecation
        if endpoint.version.status == VersionStatus.DEPRECATED:
            result.warnings.append(f"API v{endpoint.version.semver} is deprecated")
            if endpoint.version.sunset_date and endpoint.version.sunset_date < time.time():
                result.status = "sunset"
                result.warnings.append("This version has been sunset and will be removed")
        elif endpoint.version.status == VersionStatus.SUNSET:
            result.status = "sunset"
            result.warnings.append("This version has been sunset")

        # Check for newer version available
        latest = self._registry.get_endpoint(method, path)
        if (
            latest
            and latest.version > endpoint.version
            and latest.version.status == VersionStatus.ACTIVE
        ):
            result.warnings.append(f"Newer version available: v{latest.version.semver}")

        # Fallback tracking
        if version and endpoint.version != version:
            result.fallback_used = True

        self._negotiation_log.append(result)
        return result

    def _parse_version(
        self, requested_version: Optional[str], accept_header: Optional[str],
    ) -> Optional[APIVersion]:
        if requested_version:
            match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", requested_version)
            if match:
                return APIVersion(
                    int(match.group(1)), int(match.group(2)), int(match.group(3) or 0),
                )

        if accept_header:
            match = re.search(r"v(\d+)\.(\d+)(?:\.(\d+))?", accept_header)
            if match:
                return APIVersion(
                    int(match.group(1)), int(match.group(2)), int(match.group(3) or 0),
                )

        return None

    def get_deprecations(self) -> List[DeprecationNotice]:
        return self._registry.get_deprecations()

    def get_negotiation_history(self, limit: int = 100) -> List[NegotiationResult]:
        return self._negotiation_log[-limit:]


class APIVersionNegotiatorService:
    """Main service: API version negotiation and evolution."""

    def __init__(self, strategy: NegotiationStrategy = NegotiationStrategy.LATEST_COMPATIBLE):
        self._negotiator = APIVersionNegotiator(strategy=strategy)

    def initialize(self) -> None:
        # Register default API versions for core services
        for svc in [
            "nsa_broker",
            "dnf_orchestrator",
            "shi_gateway",
            "quantum_solver",
            "genetic_optimizer",
        ]:
            self._negotiator.register_version(svc, APIVersion(1, 0, 0, VersionStatus.ACTIVE))
            self._negotiator.register_version(svc, APIVersion(1, 1, 0, VersionStatus.ACTIVE))

        logger.info("APIVersionNegotiatorService initialized with %d core service versions", 5)

    def negotiate(
        self,
        method: str,
        path: str,
        requested_version: Optional[str] = None,
        accept_header: Optional[str] = None,
    ) -> NegotiationResult:
        return self._negotiator.negotiate(method, path, requested_version, accept_header)

    def register_endpoint(self, endpoint: APIEndpoint) -> None:
        self._negotiator.register_endpoint(endpoint)

    def get_deprecations(self) -> List[DeprecationNotice]:
        return self._negotiator.get_deprecations()

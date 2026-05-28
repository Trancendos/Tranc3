"""
Trancendos Zero Trust IAM Middleware
======================================
Ported from @trancendos/iam-middleware/zeroTrust (infinity-adminOS, TypeScript)

Self-hosted Zero Trust device posture enforcement.
Replaces Cloudflare Zero Trust dependency — zero-cost.

Features:
- Device posture checks (healthy, unhealthy, unknown)
- MFA verification for sensitive routes
- Geographic access policies
- Risk scoring
- Network-based access control
- Just-In-Time (JIT) access grants for admin routes
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from threading import Lock
from typing import Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("tranc3.auth.zero_trust")


class DevicePostureStatus(str, enum.Enum):
    """Device health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AccessPolicy(str, enum.Enum):
    """Access decision."""

    ALLOW = "allow"
    DENY = "deny"
    MFA_REQUIRED = "mfa_required"


class ZeroTrustContext(BaseModel):
    """Zero Trust context extracted from request headers."""

    device_id: Optional[str] = None
    device_posture: DevicePostureStatus = DevicePostureStatus.UNKNOWN
    country: Optional[str] = None
    mfa_verified: bool = False
    access_policy: AccessPolicy = AccessPolicy.ALLOW
    risk_score: int = Field(default=0, ge=0, le=100)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ZeroTrustOptions(BaseModel):
    """Configuration for Zero Trust enforcement."""

    mfa_routes: list[str] = Field(default_factory=list, description="Routes requiring MFA")
    healthy_device_routes: list[str] = Field(
        default_factory=list, description="Routes requiring healthy device"
    )
    allowed_countries: list[str] = Field(
        default_factory=list, description="ISO 3166-1 alpha-2 allowed countries"
    )
    blocked_countries: list[str] = Field(
        default_factory=list, description="ISO 3166-1 alpha-2 blocked countries"
    )
    min_risk_score: int = Field(default=0, ge=0, le=100, description="Minimum risk score to allow")
    enforce_on_all_routes: bool = False
    mfa_bypass_for_healthy: bool = True


class ZeroTrustMiddleware:
    """
    Zero Trust middleware for self-hosted enforcement.

    Extracts device posture, MFA status, and geographic information
    from request headers, calculates risk scores, and enforces
    access policies.

    Replaces Cloudflare Zero Trust — self-hosted, zero-cost.

    Usage:
        middleware = ZeroTrustMiddleware(ZeroTrustOptions(
            mfa_routes=["/admin", "/api/secrets"],
            blocked_countries=["XX"],
        ))

        context = middleware.extract_context(request_headers)
        decision = middleware.evaluate(context, request_path)
    """

    def __init__(self, options: ZeroTrustOptions | None = None) -> None:
        self.options = options or ZeroTrustOptions()

    def extract_context(self, headers: dict[str, str]) -> ZeroTrustContext:
        """
        Extract Zero Trust context from request headers.

        Headers used (standardised for self-hosted setup):
        - X-Device-Posture: healthy | unhealthy | unknown
        - X-Device-ID: Device identifier
        - X-Client-Country: ISO 3166-1 alpha-2 country code
        - X-MFA-Verified: true | false
        - X-Client-IP: Client IP address
        - User-Agent: Client user agent
        """
        # Device posture
        posture_header = (
            headers.get("x-device-posture", "") or headers.get("X-Device-Posture", "") or "unknown"
        ).lower()
        device_posture = DevicePostureStatus.UNKNOWN
        if posture_header == "healthy":
            device_posture = DevicePostureStatus.HEALTHY
        elif posture_header == "unhealthy":
            device_posture = DevicePostureStatus.UNHEALTHY

        # MFA verification
        mfa_header = (
            headers.get("x-mfa-verified", "") or headers.get("X-MFA-Verified", "")
        ).lower()
        mfa_verified = mfa_header in ("true", "1", "yes")

        # Country
        country = headers.get("x-client-country", "") or headers.get("X-Client-Country", "") or None

        # Device ID
        device_id = headers.get("x-device-id", "") or headers.get("X-Device-ID", "") or None

        # IP Address
        ip_address = (
            headers.get("x-client-ip", "")
            or headers.get("X-Client-IP", "")
            or headers.get("x-forwarded-for", "")
            or headers.get("X-Forwarded-For", "")
            or None
        )

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            device_posture=device_posture,
            mfa_verified=mfa_verified,
            country=country,
        )

        # Determine access policy
        access_policy = self._determine_policy(
            device_posture=device_posture,
            mfa_verified=mfa_verified,
            risk_score=risk_score,
        )

        return ZeroTrustContext(
            device_id=device_id,
            device_posture=device_posture,
            country=country,
            mfa_verified=mfa_verified,
            access_policy=access_policy,
            risk_score=risk_score,
            ip_address=ip_address,
            user_agent=headers.get("user-agent", headers.get("User-Agent", "")),
        )

    def evaluate(self, context: ZeroTrustContext, path: str) -> ZeroTrustContext:
        """
        Evaluate Zero Trust context against the configured policies
        for a specific request path.

        Returns the context with updated access_policy.
        """
        # Check blocked countries
        if context.country and context.country in self.options.blocked_countries:
            context.access_policy = AccessPolicy.DENY
            context.risk_score = 100
            return context

        # Check allowed countries (if specified)
        if (
            self.options.allowed_countries
            and context.country
            and context.country not in self.options.allowed_countries
        ):
            context.access_policy = AccessPolicy.DENY
            context.risk_score = min(context.risk_score + 30, 100)
            return context

        # Check MFA routes
        if path in self.options.mfa_routes or self._path_matches_patterns(
            path, self.options.mfa_routes
        ):
            if not context.mfa_verified:
                if not (
                    self.options.mfa_bypass_for_healthy
                    and context.device_posture == DevicePostureStatus.HEALTHY
                ):
                    context.access_policy = AccessPolicy.MFA_REQUIRED
                    return context

        # Check healthy device routes
        if path in self.options.healthy_device_routes or self._path_matches_patterns(
            path, self.options.healthy_device_routes
        ):
            if context.device_posture != DevicePostureStatus.HEALTHY:
                context.access_policy = AccessPolicy.DENY
                return context

        # Check minimum risk score
        if context.risk_score > 0 and context.risk_score < self.options.min_risk_score:
            context.access_policy = AccessPolicy.ALLOW
        elif context.risk_score >= 80:
            context.access_policy = AccessPolicy.DENY
        elif context.risk_score >= 50:
            context.access_policy = AccessPolicy.MFA_REQUIRED

        # Unhealthy devices are denied on enforced routes
        if (
            self.options.enforce_on_all_routes
            and context.device_posture == DevicePostureStatus.UNHEALTHY
        ):
            context.access_policy = AccessPolicy.DENY

        return context

    def _calculate_risk_score(
        self,
        device_posture: DevicePostureStatus,
        mfa_verified: bool,
        country: str | None,
    ) -> int:
        """Calculate a risk score from 0 (safe) to 100 (dangerous)."""
        score = 0

        if device_posture == DevicePostureStatus.UNHEALTHY:
            score += 40
        elif device_posture == DevicePostureStatus.UNKNOWN:
            score += 20

        if not mfa_verified:
            score += 10

        # Additional risk factors can be added here
        # e.g., known malicious IPs, time-of-day, etc.

        return min(score, 100)

    def _determine_policy(
        self,
        device_posture: DevicePostureStatus,
        mfa_verified: bool,
        risk_score: int,
    ) -> AccessPolicy:
        """Determine access policy from context factors."""
        if device_posture == DevicePostureStatus.UNHEALTHY:
            return AccessPolicy.DENY
        if not mfa_verified:
            return AccessPolicy.MFA_REQUIRED
        return AccessPolicy.ALLOW

    @staticmethod
    def _path_matches_patterns(path: str, patterns: list[str]) -> bool:
        """Check if a path matches any of the given patterns (simple glob)."""
        import fnmatch

        return any(fnmatch.fnmatch(path, p) for p in patterns)


# ---------------------------------------------------------------------------
# Just-In-Time (JIT) Access Management
# ---------------------------------------------------------------------------


class JITGrant:
    """A single time-bounded JIT access grant."""

    def __init__(
        self,
        *,
        grant_id: str,
        user_id: str,
        path_pattern: str,
        granted_by: str,
        duration_seconds: int,
        reason: str = "",
    ) -> None:
        self.grant_id = grant_id
        self.user_id = user_id
        self.path_pattern = path_pattern
        self.granted_by = granted_by
        self.duration_seconds = duration_seconds
        self.reason = reason
        self.granted_at: float = time.monotonic()
        self.expires_at: float = self.granted_at + duration_seconds
        self.revoked: bool = False
        self.last_used_at: Optional[float] = None
        self.use_count: int = 0

    @property
    def is_active(self) -> bool:
        """True when the grant is valid and has not expired or been revoked."""
        return not self.revoked and time.monotonic() < self.expires_at

    @property
    def seconds_remaining(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())

    def record_use(self) -> None:
        self.last_used_at = time.monotonic()
        self.use_count += 1

    def to_dict(self) -> dict:
        return {
            "grant_id": self.grant_id,
            "user_id": self.user_id,
            "path_pattern": self.path_pattern,
            "granted_by": self.granted_by,
            "reason": self.reason,
            "duration_seconds": self.duration_seconds,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "seconds_remaining": round(self.seconds_remaining, 1),
            "revoked": self.revoked,
            "use_count": self.use_count,
            "is_active": self.is_active,
        }


class JITAccessManager:
    """
    Just-In-Time access manager for privileged admin routes.

    Grants are time-bounded, single-issuer, revocable. Expired grants are
    purged automatically on each operation (no background thread needed).

    Typical usage:
        jit = JITAccessManager(max_duration_seconds=3600)

        # Operator issues a grant (e.g. after approval workflow)
        grant_id = jit.grant(
            user_id="admin-alice",
            path_pattern="/admin/*",
            granted_by="sre-ops",
            duration_seconds=900,
            reason="incident-2025-001 investigation",
        )

        # Middleware checks on incoming request
        if jit.check(user_id="admin-alice", path="/admin/config"):
            # allow through

        # Operator revokes early if needed
        jit.revoke(grant_id)
    """

    DEFAULT_MAX_DURATION: int = 3600   # 1 hour hard cap
    DEFAULT_TTL: int = 900             # 15 minutes default

    def __init__(self, max_duration_seconds: int = DEFAULT_MAX_DURATION) -> None:
        self._max_duration = max_duration_seconds
        self._grants: Dict[str, JITGrant] = {}
        self._lock = Lock()
        self._logger = logging.getLogger("tranc3.auth.jit")

    # ------------------------------------------------------------------
    # Grant lifecycle
    # ------------------------------------------------------------------

    def grant(
        self,
        *,
        user_id: str,
        path_pattern: str,
        granted_by: str,
        duration_seconds: int = DEFAULT_TTL,
        reason: str = "",
    ) -> str:
        """Issue a new JIT grant. Returns the grant_id."""
        if duration_seconds > self._max_duration:
            raise ValueError(
                f"Requested duration {duration_seconds}s exceeds max {self._max_duration}s"
            )
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")

        grant_id = uuid.uuid4().hex
        g = JITGrant(
            grant_id=grant_id,
            user_id=user_id,
            path_pattern=path_pattern,
            granted_by=granted_by,
            duration_seconds=duration_seconds,
            reason=reason,
        )
        with self._lock:
            self._purge_expired()
            self._grants[grant_id] = g

        self._logger.info(
            "JIT grant issued: user=%s path=%s ttl=%ds by=%s reason=%r id=%s",
            user_id, path_pattern, duration_seconds, granted_by, reason, grant_id,
        )
        return grant_id

    def revoke(self, grant_id: str) -> bool:
        """Revoke an active grant. Returns True if the grant existed."""
        with self._lock:
            g = self._grants.get(grant_id)
            if g is None:
                return False
            g.revoked = True

        self._logger.info("JIT grant revoked: id=%s user=%s", grant_id, g.user_id)
        return True

    # ------------------------------------------------------------------
    # Access checks
    # ------------------------------------------------------------------

    def check(self, *, user_id: str, path: str) -> bool:
        """
        Returns True if *user_id* has an active JIT grant for *path*.

        Records usage on the matching grant.
        """
        import fnmatch

        with self._lock:
            self._purge_expired()
            for g in self._grants.values():
                if (
                    g.is_active
                    and g.user_id == user_id
                    and fnmatch.fnmatch(path, g.path_pattern)
                ):
                    g.record_use()
                    return True
        return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_grants(self, user_id: Optional[str] = None) -> list:
        """Return all active grants, optionally filtered by user."""
        with self._lock:
            self._purge_expired()
            grants = [
                g.to_dict()
                for g in self._grants.values()
                if g.is_active and (user_id is None or g.user_id == user_id)
            ]
        return grants

    def get_grant(self, grant_id: str) -> Optional[dict]:
        """Retrieve a specific grant by ID (active or expired)."""
        with self._lock:
            g = self._grants.get(grant_id)
        return g.to_dict() if g else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _purge_expired(self) -> None:
        """Remove fully expired (and revoked) grants. Must be called under lock."""
        now = time.monotonic()
        expired = [gid for gid, g in self._grants.items() if g.expires_at < now or g.revoked]
        for gid in expired:
            del self._grants[gid]


# ---------------------------------------------------------------------------
# Module-level default JIT manager (singleton for simple deployments)
# ---------------------------------------------------------------------------

_default_jit: Optional[JITAccessManager] = None


def get_jit_manager() -> JITAccessManager:
    """Return (or lazily create) the default JIT access manager."""
    global _default_jit
    if _default_jit is None:
        _default_jit = JITAccessManager()
    return _default_jit

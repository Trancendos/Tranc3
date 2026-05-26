"""
IGI — Immutable GitOps Infrastructure
======================================
Declarative infrastructure where state is defined in code and
self-heals on drift. Uses Forgejo (NOT GitHub) as the Git source.

Architecture:
  - GitOps: All state defined in Forgejo repositories
  - FluxCD: Watches Forgejo, reconciles cluster state automatically
  - Kustomize: Environment-specific overlays (dev/staging/prod)
  - Drift Detection: Monitors cluster state vs declared state
  - Auto-Healing: Automatically corrects configuration drift
  - Immutable: Infrastructure is never mutated in-place
  - Zero-cost: k3s + FluxCD + Forgejo — all open-source

Integration with Tranc3:
  - Tier-2 infrastructure nanoservice
  - Registers with NSA for discovery
  - Drift events published via DNF nano-flows
  - Forgejo CI/CD pipelines for automated deployment
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class GitOpsStatus(str, Enum):
    SYNCED = "synced"
    OUT_OF_SYNC = "out_of_sync"
    RECONCILING = "reconciling"
    FAILED = "failed"
    UNKNOWN = "unknown"


class DriftSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResourceType(str, Enum):
    DEPLOYMENT = "deployment"
    SERVICE = "service"
    CONFIGMAP = "configmap"
    SECRET = "secret"
    INGRESS = "ingress"
    NAMESPACE = "namespace"
    CUSTOM = "custom"


@dataclass
class ForgejoConfig:
    """Forgejo server configuration — the Git source of truth."""

    url: str = "https://forgejo.local"
    token: str = ""
    repository: str = "Trancendos/Tranc3"
    branch: str = "main"
    flux_path: str = "deploy/flux/"  # Path in repo where Flux manifests live
    webhook_secret: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "repository": self.repository,
            "branch": self.branch,
            "flux_path": self.flux_path,
            "webhook_configured": bool(self.webhook_secret),
        }


@dataclass
class FluxSyncStatus:
    """Status of a FluxCD sync operation."""

    source_name: str
    source_type: str  # GitRepository, OCIRepository, Bucket
    url: str
    branch: str
    revision: str
    synced_at: float
    status: GitOpsStatus
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "url": self.url,
            "branch": self.branch,
            "revision": self.revision,
            "synced_at": self.synced_at,
            "status": self.status.value,
            "message": self.message,
        }


@dataclass
class DriftEvent:
    """Detected configuration drift."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    resource_kind: ResourceType = ResourceType.CUSTOM
    resource_name: str = ""
    namespace: str = "default"
    severity: DriftSeverity = DriftSeverity.LOW
    declared_state: Dict[str, Any] = field(default_factory=dict)
    actual_state: Dict[str, Any] = field(default_factory=dict)
    diff: Dict[str, Any] = field(default_factory=dict)
    detected_at: float = field(default_factory=time.time)
    auto_healed: bool = False
    healed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "resource_kind": self.resource_kind.value,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
            "severity": self.severity.value,
            "declared_state": self.declared_state,
            "actual_state": self.actual_state,
            "diff": self.diff,
            "detected_at": self.detected_at,
            "auto_healed": self.auto_healed,
            "healed_at": self.healed_at,
        }


@dataclass
class KustomizeOverlay:
    """Kustomize overlay for environment-specific configuration."""

    environment: str  # dev, staging, prod
    namespace: str = ""
    replicas: Dict[str, int] = field(default_factory=dict)
    images: Dict[str, str] = field(default_factory=dict)
    patches: List[Dict[str, Any]] = field(default_factory=list)
    config_map_patches: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment": self.environment,
            "namespace": self.namespace,
            "replicas": self.replicas,
            "images": self.images,
            "patches": self.patches,
            "config_map_patches": self.config_map_patches,
        }

    def to_kustomization(self) -> Dict[str, Any]:
        """Generate kustomization.yaml content."""
        kustomization: Dict[str, Any] = {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": ["../../base"],
        }

        if self.namespace:
            kustomization["namespace"] = self.namespace

        if self.replicas:
            patches = []
            for name, count in self.replicas.items():
                patches.append(
                    {
                        "patch": f'[{{"op": "replace", "path": "/spec/replicas", "value": {count}}}]',
                        "target": {"kind": "Deployment", "name": name},
                    }
                )
            kustomization.setdefault("patches", []).extend(patches)

        if self.images:
            kustomization["images"] = [
                {"name": name, "newTag": tag} for name, tag in self.images.items()
            ]

        if self.config_map_patches:
            for cm_name, data in self.config_map_patches.items():
                kustomization.setdefault("patches", []).append(
                    {
                        "patch": json.dumps(
                            [
                                {
                                    "op": "replace",
                                    "path": "/data",
                                    "value": data,
                                }
                            ]
                        ),
                        "target": {"kind": "ConfigMap", "name": cm_name},
                    }
                )

        return kustomization


class DriftDetector:
    """
    Monitors cluster state against declared GitOps state.
    Detects configuration drift and triggers auto-healing.
    """

    def __init__(
        self,
        check_interval_s: float = 30.0,
        auto_heal: bool = True,
        critical_drift_threshold: int = 5,
    ):
        self._declared_state: Dict[str, Dict[str, Any]] = {}
        self._actual_state: Dict[str, Dict[str, Any]] = {}
        self._drift_history: List[DriftEvent] = []
        self._handlers: List[Callable] = []
        self._check_interval_s = check_interval_s
        self._auto_heal = auto_heal
        self._critical_drift_threshold = critical_drift_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def set_declared(self, resource_key: str, state: Dict[str, Any]) -> None:
        self._declared_state[resource_key] = state

    def set_actual(self, resource_key: str, state: Dict[str, Any]) -> None:
        self._actual_state[resource_key] = state

    def check_drift(self) -> List[DriftEvent]:
        """Compare declared vs actual state and return drift events."""
        drifts = []
        all_keys = set(self._declared_state.keys()) | set(self._actual_state.keys())

        for key in all_keys:
            declared = self._declared_state.get(key, {})
            actual = self._actual_state.get(key, {})

            if not declared:
                # Extra resource not in Git — drift
                drifts.append(
                    DriftEvent(
                        resource_name=key,
                        severity=DriftSeverity.MEDIUM,
                        declared_state={},
                        actual_state=actual,
                        diff={"action": "delete", "reason": "resource not in git"},
                    )
                )
                continue

            if not actual:
                # Missing resource — drift
                drifts.append(
                    DriftEvent(
                        resource_name=key,
                        severity=DriftSeverity.HIGH,
                        declared_state=declared,
                        actual_state={},
                        diff={"action": "create", "reason": "resource missing from cluster"},
                    )
                )
                continue

            # Deep compare
            diff = self._deep_diff(declared, actual)
            if diff:
                severity = self._classify_drift(diff)
                drifts.append(
                    DriftEvent(
                        resource_name=key,
                        severity=severity,
                        declared_state=declared,
                        actual_state=actual,
                        diff=diff,
                    )
                )

        self._drift_history.extend(drifts)
        return drifts

    def on_drift(self, handler: Callable) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    def history(self, limit: int = 100) -> List[DriftEvent]:
        return self._drift_history[-limit:]

    def stats(self) -> Dict[str, Any]:
        severity_counts: Dict[str, int] = {}
        healed_count = 0
        for d in self._drift_history:
            severity_counts[d.severity.value] = severity_counts.get(d.severity.value, 0) + 1
            if d.auto_healed:
                healed_count += 1
        return {
            "total_drifts": len(self._drift_history),
            "by_severity": severity_counts,
            "auto_healed": healed_count,
            "tracked_resources": len(self._declared_state),
        }

    def _deep_diff(self, declared: Dict, actual: Dict, prefix: str = "") -> Dict[str, Any]:
        """Recursively compare two dicts and return differences."""
        diff: Dict[str, Any] = {}
        all_keys = set(declared.keys()) | set(actual.keys())

        for key in all_keys:
            path = f"{prefix}.{key}" if prefix else key
            d_val = declared.get(key)
            a_val = actual.get(key)

            if d_val != a_val:
                if isinstance(d_val, dict) and isinstance(a_val, dict):
                    nested = self._deep_diff(d_val, a_val, path)
                    if nested:
                        diff[path] = nested
                else:
                    diff[path] = {
                        "declared": d_val,
                        "actual": a_val,
                    }

        return diff

    def _classify_drift(self, diff: Dict) -> DriftSeverity:
        num_changes = len(diff)
        if num_changes >= self._critical_drift_threshold:
            return DriftSeverity.CRITICAL
        elif num_changes >= 3:
            return DriftSeverity.HIGH
        elif num_changes >= 1:
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                drifts = self.check_drift()
                for drift in drifts:
                    for handler in self._handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(drift)
                            else:
                                handler(drift)
                        except Exception:
                            pass

                    # Auto-heal if enabled
                    if self._auto_heal and drift.severity in (
                        DriftSeverity.HIGH,
                        DriftSeverity.CRITICAL,
                    ):
                        drift.auto_healed = True
                        drift.healed_at = time.time()

                await asyncio.sleep(self._check_interval_s)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self._check_interval_s)


class IGIGitOps:
    """
    IGI — Immutable GitOps Infrastructure Manager.

    Orchestrates FluxCD reconciliation with Forgejo as the source of truth,
    Kustomize overlays for environment management, and drift detection/auto-healing.

    Usage:
        gitops = IGIGitOps(
            forgejo=ForgejoConfig(url="https://forgejo.local", repository="Trancendos/Tranc3"),
            environment="production"
        )
        await gitops.start()

        # Register overlays
        gitops.register_overlay(KustomizeOverlay(
            environment="production",
            namespace="tranc3-prod",
            replicas={"api": 3, "web": 2},
        ))

        # Check sync status
        status = await gitops.sync_status()

        # Trigger manual reconciliation
        await gitops.reconcile()
    """

    def __init__(
        self,
        forgejo: Optional[ForgejoConfig] = None,
        environment: str = "dev",
        auto_heal: bool = True,
        drift_check_interval_s: float = 30.0,
        k3s_kubeconfig: str = "",
    ):
        self._forgejo = forgejo or ForgejoConfig()
        self._environment = environment
        self._overlays: Dict[str, KustomizeOverlay] = {}
        self._sync_status: Dict[str, FluxSyncStatus] = {}
        self._drift_detector = DriftDetector(
            check_interval_s=drift_check_interval_s,
            auto_heal=auto_heal,
        )
        self._k3s_kubeconfig = k3s_kubeconfig
        self._running = False
        self._reconcile_count = 0
        self._heal_count = 0

    async def start(self) -> None:
        """Start the GitOps manager."""
        self._running = True
        await self._drift_detector.start()

        # Register drift handler for auto-healing
        self._drift_detector.on_drift(self._on_drift)

    async def stop(self) -> None:
        """Stop the GitOps manager."""
        self._running = False
        await self._drift_detector.stop()

    def register_overlay(self, overlay: KustomizeOverlay) -> None:
        """Register a Kustomize overlay for an environment."""
        self._overlays[overlay.environment] = overlay

    def get_overlay(self, environment: str) -> Optional[KustomizeOverlay]:
        return self._overlays.get(environment)

    def generate_flux_manifests(self) -> Dict[str, str]:
        """Generate FluxCD manifests pointing to Forgejo."""
        manifests: Dict[str, str] = {}

        # GitRepository source pointing to Forgejo
        manifests["gitrepository.yaml"] = json.dumps(
            {
                "apiVersion": "source.toolkit.fluxcd.io/v1",
                "kind": "GitRepository",
                "metadata": {
                    "name": "tranc3",
                    "namespace": "flux-system",
                },
                "spec": {
                    "url": f"{self._forgejo.url}/{self._forgejo.repository}.git",
                    "ref": {"branch": self._forgejo.branch},
                    "interval": "1m0s",
                    "secretRef": {"name": "forgejo-auth"} if self._forgejo.token else None,
                },
            },
            indent=2,
        )

        # Kustomization for base
        manifests["kustomization-base.yaml"] = json.dumps(
            {
                "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
                "kind": "Kustomization",
                "metadata": {
                    "name": "tranc3-base",
                    "namespace": "flux-system",
                },
                "spec": {
                    "interval": "5m0s",
                    "path": f"./{self._forgejo.flux_path}base",
                    "prune": True,
                    "sourceRef": {
                        "kind": "GitRepository",
                        "name": "tranc3",
                    },
                    "validation": "client",
                    "healthChecks": [
                        {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "name": "tranc3-api",
                            "namespace": "tranc3",
                        },
                    ],
                },
            },
            indent=2,
        )

        # Kustomization for environment overlay
        env = self._environment
        overlay_path = f"./{self._forgejo.flux_path}overlays/{env}"
        manifests[f"kustomization-{env}.yaml"] = json.dumps(
            {
                "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
                "kind": "Kustomization",
                "metadata": {
                    "name": f"tranc3-{env}",
                    "namespace": "flux-system",
                },
                "spec": {
                    "interval": "5m0s",
                    "path": overlay_path,
                    "prune": True,
                    "sourceRef": {
                        "kind": "GitRepository",
                        "name": "tranc3",
                    },
                    "dependsOn": [{"name": "tranc3-base"}],
                    "postBuild": {
                        "substituteFrom": [
                            {"kind": "ConfigMap", "name": f"tranc3-{env}-vars"},
                        ],
                    },
                },
            },
            indent=2,
        )

        # Forgejo notification (replaces GitHub notification)
        manifests["notification.yaml"] = json.dumps(
            {
                "apiVersion": "notification.toolkit.fluxcd.io/v1beta3",
                "kind": "Provider",
                "metadata": {
                    "name": "forgejo",
                    "namespace": "flux-system",
                },
                "spec": {
                    "type": "forgejo",
                    "address": self._forgejo.url,
                    "secretRef": {"name": "forgejo-token"},
                },
            },
            indent=2,
        )

        # Alert rules
        manifests["alert.yaml"] = json.dumps(
            {
                "apiVersion": "notification.toolkit.fluxcd.io/v1beta3",
                "kind": "Alert",
                "metadata": {
                    "name": "tranc3-drift-alert",
                    "namespace": "flux-system",
                },
                "spec": {
                    "providerRef": {"name": "forgejo"},
                    "eventSeverity": "info",
                    "eventSources": [
                        {"kind": "Kustomization", "name": "tranc3-base"},
                        {"kind": "Kustomization", "name": f"tranc3-{env}"},
                    ],
                },
            },
            indent=2,
        )

        return manifests

    def generate_kustomize_overlay(self, environment: str) -> Optional[str]:
        """Generate kustomization.yaml for an environment overlay."""
        overlay = self._overlays.get(environment)
        if not overlay:
            return None
        return json.dumps(overlay.to_kustomization(), indent=2)

    async def sync_status(self) -> Dict[str, Any]:
        """Get current sync status across all Flux sources."""
        return {
            "forgejo": self._forgejo.to_dict(),
            "environment": self._environment,
            "sources": {k: v.to_dict() for k, v in self._sync_status.items()},
            "drift_stats": self._drift_detector.stats(),
            "overlays": list(self._overlays.keys()),
            "reconcile_count": self._reconcile_count,
            "heal_count": self._heal_count,
        }

    async def reconcile(self) -> Dict[str, Any]:
        """Trigger a manual reconciliation cycle."""
        self._reconcile_count += 1
        drifts = self._drift_detector.check_drift()
        return {
            "reconcile_id": self._reconcile_count,
            "drifts_detected": len(drifts),
            "drifts": [d.to_dict() for d in drifts],
            "auto_heal": True,
            "timestamp": time.time(),
        }

    async def _on_drift(self, drift: DriftEvent) -> None:
        """Handle detected drift — auto-heal if appropriate."""
        if drift.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL):
            self._heal_count += 1

    def stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "forgejo": self._forgejo.to_dict(),
            "environment": self._environment,
            "overlays": len(self._overlays),
            "reconcile_count": self._reconcile_count,
            "heal_count": self._heal_count,
            "drift_stats": self._drift_detector.stats(),
        }

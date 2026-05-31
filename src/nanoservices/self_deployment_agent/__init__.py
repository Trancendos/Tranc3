"""Self-Deployment Agent — Phase 9

Autonomous deployment agent that manages GitOps workflows through
Forgejo + FluxCD, detects configuration drift, and performs
auto-healing deployments.
"""

from .self_deployment_agent import (
    DeploymentAction,
    DeploymentConfig,
    DeploymentResult,
    DeploymentState,
    DriftReport,
    SelfDeploymentAgent,
)

__all__ = [
    "DeploymentState",
    "DeploymentAction",
    "DeploymentConfig",
    "DeploymentResult",
    "DriftReport",
    "SelfDeploymentAgent",
]

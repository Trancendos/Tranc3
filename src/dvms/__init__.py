"""DVMS — the platform's dependency and vulnerability management surface.

Cryptex finds the vulnerability, The Lab remediates it, and neither can act
until the finding has an owner. This package holds the join that gives it one,
and the dispatcher that turns an owned finding into the Request or Change The
Lab actually works from.
"""

from src.dvms.dispatch import (
    DispatchItem,
    apply,
    plan,
    summarise,
)
from src.dvms.surface_owner import (
    SurfaceOwner,
    declared_surfaces,
    resolve_surface,
    unresolved_surfaces,
)

__all__ = [
    "DispatchItem",
    "SurfaceOwner",
    "apply",
    "declared_surfaces",
    "plan",
    "resolve_surface",
    "summarise",
    "unresolved_surfaces",
]

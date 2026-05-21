# shared_core/__init__.py
# Trancendos Shared Core — Common utilities, models, and interfaces

from .models import (
    ServiceInfo,
    ServiceHealth,
    ServiceCapability,
    EventMessage,
    VectorClock,
)
from .registry import ServiceRegistry
from .bus import EventBus
from .security import (
    generate_jwt,
    verify_jwt,
    hash_password,
    verify_password,
)
from .optional_import import LazyLoader

__all__ = [
    # Models
    "ServiceInfo",
    "ServiceHealth",
    "ServiceCapability",
    "EventMessage",
    "VectorClock",
    # Registry
    "ServiceRegistry",
    # Bus
    "EventBus",
    # Security
    "generate_jwt",
    "verify_jwt",
    "hash_password",
    "verify_password",
    # Utilities
    "LazyLoader",
]

__version__ = "0.1.0"
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
from .path_validation import (
    PathTraversalError,
    validate_path,
    safe_join,
    sanitize_filename,
)
from .error_handlers import (
    safe_error_detail,
    SafeHTTPException,
)
from .sanitize import (
    sanitize_for_log,
    sanitize_dict_for_log,
    SafeLogger,
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
    # Path validation
    "PathTraversalError",
    "validate_path",
    "safe_join",
    "sanitize_filename",
    # Error handlers
    "safe_error_detail",
    "SafeHTTPException",
    # Log sanitization
    "sanitize_for_log",
    "sanitize_dict_for_log",
    "SafeLogger",
    # Utilities
    "LazyLoader",
]

__version__ = "0.1.0"
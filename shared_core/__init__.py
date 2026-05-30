# shared_core/__init__.py
# Trancendos Shared Core — Common utilities, models, and interfaces

from .bus import EventBus
from .error_handlers import (
    SafeHTTPException,
    safe_error_detail,
)
from .models import (
    EventMessage,
    ServiceCapability,
    ServiceHealth,
    ServiceInfo,
    VectorClock,
)
from .optional_import import LazyLoader
from .path_validation import (
    PathTraversalError,
    safe_join,
    sanitize_filename,
    validate_path,
)
from .registry import ServiceRegistry
from .sanitize import (
    SafeLogger,
    sanitize_dict_for_log,
    sanitize_for_log,
)
from .security import (
    generate_jwt,
    hash_password,
    verify_jwt,
    verify_password,
)

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

# Infinity Ecosystem package
# Dimensional Services package (Shared-Core = Dimensional's)
from . import (
    dimensionals,  # noqa: F401
    infinity,  # noqa: F401
)

__version__ = "0.7.0"

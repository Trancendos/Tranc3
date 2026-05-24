# Dimensional/optional_import.py
# Lazy import utility — defer heavy imports until actually needed

import importlib
import logging
from types import ModuleType
from typing import Any, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class LazyLoader:
    """
    Lazy module loader that defers import until first attribute access.
    Prevents startup crashes from missing optional dependencies.

    Usage:
        torch = LazyLoader("torch", description="PyTorch for ML inference")
        # torch is not imported yet
        result = torch.randn(3, 3)  # NOW it imports
    """

    def __init__(
        self,
        module_name: str,
        package: Optional[str] = None,
        description: str = "",
        fallback: Any = None,
        warn_on_fail: bool = True,
    ):
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_package", package)
        object.__setattr__(self, "_description", description or module_name)
        object.__setattr__(self, "_fallback", fallback)
        object.__setattr__(self, "_warn_on_fail", warn_on_fail)
        object.__setattr__(self, "_module", None)
        object.__setattr__(self, "_loaded", False)
        object.__setattr__(self, "_failed", False)

    def _load(self) -> ModuleType:
        """Attempt to load the module"""
        if object.__getattribute__(self, "_loaded"):
            mod = object.__getattribute__(self, "_module")
            if mod is None:
                raise ImportError(
                    f"Optional dependency '{object.__getattribute__(self, '_module_name')}' "
                    f"is not installed. {object.__getattribute__(self, '_description')}"
                )
            return mod

        module_name = object.__getattribute__(self, "_module_name")
        package = object.__getattribute__(self, "_package")

        try:
            mod = importlib.import_module(module_name, package)
            object.__setattr__(self, "_module", mod)
            object.__setattr__(self, "_loaded", True)
            logger.debug(
                "Lazy-loaded: %s", sanitize_for_log(module_name)
            )  # codeql[py/cleartext-logging]
            return mod
        except ImportError as e:
            object.__setattr__(self, "_module", None)
            object.__setattr__(self, "_loaded", True)
            object.__setattr__(self, "_failed", True)

            if object.__getattribute__(self, "_warn_on_fail"):
                logger.warning(
                    "Optional dependency '%s' not available: %s. Feature requiring %s will be disabled.",
                    sanitize_for_log(module_name),
                    sanitize_for_log(e),
                    sanitize_for_log(object.__getattribute__(self, "_description")),
                )

            fallback = object.__getattribute__(self, "_fallback")
            if fallback is not None:
                return fallback

            raise ImportError(
                f"Optional dependency '{module_name}' is not installed. "
                f"{object.__getattribute__(self, '_description')}"
            ) from e
        return None

    def __getattr__(self, name: str) -> Any:
        mod = self._load()
        return getattr(mod, name)

    def __repr__(self) -> str:
        module_name = object.__getattribute__(self, "_module_name")
        loaded = object.__getattribute__(self, "_loaded")
        failed = object.__getattribute__(self, "_failed")

        if loaded and not failed:
            return f"<LazyLoader({module_name}, loaded)>"
        elif failed:
            return f"<LazyLoader({module_name}, unavailable)>"
        else:
            return f"<LazyLoader({module_name}, deferred)>"

    @property
    def is_available(self) -> bool:
        """Check if the module can be imported without actually importing it"""
        if not object.__getattribute__(self, "_loaded"):
            try:
                self._load()
            except ImportError:
                logger.debug("Graceful degradation: %s", "unknown")  # nosec B110
        return not object.__getattribute__(self, "_failed")

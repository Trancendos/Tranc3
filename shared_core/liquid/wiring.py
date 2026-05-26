"""
NCP wiring helpers for liquid neural routing.

AutoWiring provides a simple API for building ncps wiring configurations.
When ncps is not installed, returns None gracefully.
"""

from __future__ import annotations

from typing import Any, Optional


def build_ncp_wiring(units: int, output_size: int) -> Optional[Any]:
    """Build an AutoNCP wiring for use in LiquidRouter.enable_ncps(). Returns None if ncps absent."""
    try:
        from ncps.wirings import AutoNCP  # type: ignore
        return AutoNCP(units=units, output_size=output_size)
    except ImportError:
        return None


class AutoWiring:
    """Simple wrapper around ncps.wirings.AutoNCP with graceful degradation."""

    def __init__(self, units: int, output_size: int) -> None:
        self._units = units
        self._output_size = output_size
        self._wiring = build_ncp_wiring(units, output_size)

    @property
    def available(self) -> bool:
        return self._wiring is not None

    @property
    def wiring(self) -> Any:
        return self._wiring

    def __repr__(self) -> str:
        status = "ncps" if self.available else "unavailable"
        return f"AutoWiring(units={self._units}, output={self._output_size}, backend={status})"

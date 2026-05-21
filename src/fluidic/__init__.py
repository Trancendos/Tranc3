# src/fluidic/__init__.py
# Fluidic architecture — adaptive, runtime-configurable systems

from .fluid_router import FluidicRouter, RouteCell
from .hot_config import HotConfig, watch_config

__all__ = ["HotConfig", "watch_config", "FluidicRouter", "RouteCell"]

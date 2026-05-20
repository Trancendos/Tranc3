# src/fluidic/__init__.py
# Fluidic architecture — adaptive, runtime-configurable systems

from .hot_config import HotConfig, watch_config
from .fluid_router import FluidicRouter, RouteCell

__all__ = ["HotConfig", "watch_config", "FluidicRouter", "RouteCell"]
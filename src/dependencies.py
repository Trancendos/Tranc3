# src/dependencies.py
# FastAPI dependency injection — wires services to routes without globals

import logging
from typing import Any, Callable, Dict, TypeVar

from fastapi import Request

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceContainer:
    """
    Lightweight DI container for Tranc3 services.
    Replaces module-level global mutable state with injectable dependencies.
    """

    def __init__(self):
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._initialized = False

    def register_factory(self, name: str, factory: Callable, singleton: bool = True) -> None:
        """Register a service factory. If singleton=True, the factory is called once."""
        self._factories[name] = factory
        if not singleton:
            self._singletons.pop(name, None)

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a pre-built instance directly"""
        self._singletons[name] = instance

    def get(self, name: str) -> Any:
        """Resolve a service by name"""
        if name in self._singletons:
            return self._singletons[name]

        if name not in self._factories:
            raise KeyError(f"Service '{name}' not registered")

        factory = self._factories[name]
        instance = factory()

        # Cache as singleton if not explicitly marked as transient
        self._singletons[name] = instance
        return instance

    def has(self, name: str) -> bool:
        """Check if a service is registered"""
        return name in self._factories or name in self._singletons

    def list_services(self) -> Dict[str, str]:
        """List all registered services and their status"""
        result = {}
        for name in self._factories:
            result[name] = "initialized" if name in self._singletons else "lazy"
        for name in self._singletons:
            if name not in self._factories:
                result[name] = "direct"
        return result

    def reset(self) -> None:
        """Clear all singletons (useful for testing)"""
        self._singletons.clear()
        self._initialized = False


# Global container instance
container = ServiceContainer()


def configure_services(config=None) -> None:
    """
    Wire up all services into the container.
    Called once during application startup.
    """
    from src.core.config import settings as _settings

    config = config or _settings

    # ── Core services ─────────────────────────────────────────────────────
    def _redis_client():
        import redis as redis_lib

        return redis_lib.from_url(config.REDIS_URL, decode_responses=True)

    def _db_manager():
        from src.database.schema import DatabaseManager

        return DatabaseManager(config.DATABASE_URL)

    def _feature_flags():
        from src.core.feature_flags import FeatureFlagManager

        return FeatureFlagManager()

    def _vector_store():
        from src.database.vector_store import vector_store as _vs

        return _vs

    # ── Optional services (graceful degradation) ─────────────────────────
    def _personality_matrix():
        try:
            from src.personality.matrix import EnhancedPersonalityMatrix

            return EnhancedPersonalityMatrix(config)
        except ImportError:
            logger.warning("Personality matrix unavailable — missing dependencies")
            return None

    def _consciousness_model():
        try:
            from src.bio_neural.consciousness_engine import ConsciousnessModel

            return ConsciousnessModel(config)
        except ImportError:
            logger.warning("Consciousness model unavailable — missing dependencies")
            return None

    def _evolution_engine():
        try:
            from src.evolution.self_improving_core import SelfEvolvingArchitecture

            engine = SelfEvolvingArchitecture(
                redis_url=config.REDIS_URL,
                mutation_rate=0.1,
                population_size=10,
            )
            return engine
        except ImportError:
            logger.warning("Evolution engine unavailable — missing dependencies")
            return None

    def _quantum_core():
        try:
            from src.quantum.quantum_core import QuantumNeuralCore

            return QuantumNeuralCore(config)
        except ImportError:
            logger.warning("Quantum core unavailable — missing dependencies")
            return None

    # ── Register all ─────────────────────────────────────────────────────
    container.register_factory("redis", _redis_client)
    container.register_factory("db", _db_manager)
    container.register_factory("feature_flags", _feature_flags)
    container.register_factory("vector_store", _vector_store)
    container.register_factory("personality", _personality_matrix)
    container.register_factory("consciousness", _consciousness_model)
    container.register_factory("evolution", _evolution_engine)
    container.register_factory("quantum", _quantum_core)

    container._initialized = True
    logger.info(
        "Service container configured with %s services",
        sanitize_for_log(len(container.list_services())),
    )


# ── FastAPI dependency helpers ────────────────────────────────────────────


def get_config(request: Request) -> Any:
    """FastAPI dependency: inject config"""
    return request.app.state.config


def get_redis(request: Request) -> Any:
    """FastAPI dependency: inject Redis client"""
    return request.app.state.container.get("redis")


def get_db(request: Request) -> Any:
    """FastAPI dependency: inject database manager"""
    return request.app.state.container.get("db")


def get_feature_flags(request: Request) -> Any:
    """FastAPI dependency: inject feature flag manager"""
    return request.app.state.container.get("feature_flags")


def get_personality(request: Request) -> Any:
    """FastAPI dependency: inject personality matrix (may be None)"""
    return request.app.state.container.get("personality")


def get_consciousness(request: Request) -> Any:
    """FastAPI dependency: inject consciousness model (may be None)"""
    return request.app.state.container.get("consciousness")


def get_evolution(request: Request) -> Any:
    """FastAPI dependency: inject evolution engine (may be None)"""
    return request.app.state.container.get("evolution")

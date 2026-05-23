# src/nanoservices/nano_registry.py
# TRANC3 Nanoservice Registry — service discovery and routing

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class NanoService:
    name: str
    endpoint: str
    capabilities: List[str]
    health_url: str
    version: str = "1.0.0"
    is_healthy: bool = True
    last_seen: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


class NanoServiceRegistry:
    """
    Central registry for all TRANC3 nanoservices.
    Handles discovery, health tracking, and capability routing.
    """

    # Built-in nanoservice definitions
    SERVICES = {
        "tokenizer": {
            "endpoint": "/nano/tokenize",
            "capabilities": ["tokenize", "decode", "detect_language"],
        },
        "emotion": {
            "endpoint": "/nano/emotion",
            "capabilities": ["detect_emotion", "emotion_scores"],
        },
        "personality": {
            "endpoint": "/nano/personality",
            "capabilities": ["get_vector", "list_profiles", "adapt"],
        },
        "quantum": {
            "endpoint": "/nano/quantum",
            "capabilities": ["attention", "optimize", "rng"],
        },
        "consciousness": {
            "endpoint": "/nano/consciousness",
            "capabilities": ["phi", "awareness", "stream"],
        },
        "memory": {
            "endpoint": "/nano/memory",
            "capabilities": ["store", "recall", "search"],
        },
        "evolution": {
            "endpoint": "/nano/evolution",
            "capabilities": ["evolve", "fitness", "generation"],
        },
        "translate": {
            "endpoint": "/nano/translate",
            "capabilities": ["translate", "languages"],
        },
        "generate": {
            "endpoint": "/nano/generate",
            "capabilities": ["generate", "stream", "complete"],
        },
        "auth": {
            "endpoint": "/nano/auth",
            "capabilities": ["login", "token", "verify"],
        },
        "billing": {
            "endpoint": "/nano/billing",
            "capabilities": ["check_tier", "usage", "stripe"],
        },
        "analytics": {
            "endpoint": "/nano/analytics",
            "capabilities": ["predict_intent", "churn", "quality"],
        },
        "predict": {
            "endpoint": "/nano/predict",
            "capabilities": ["intent", "next_message", "load_forecast"],
        },
    }

    def __init__(self):
        self._registry: Dict[str, NanoService] = {}
        self._capability_index: Dict[str, List[str]] = {}
        self._load_defaults()

    def _load_defaults(self):
        for name, config in self.SERVICES.items():
            svc = NanoService(
                name=name,
                endpoint=config["endpoint"],
                capabilities=config["capabilities"],
                health_url=f"{config['endpoint']}/health",
            )
            self.register(svc)

    def register(self, service: NanoService):
        self._registry[service.name] = service
        for cap in service.capabilities:
            self._capability_index.setdefault(cap, []).append(service.name)
        logger.info(
            "Registered nanoservice: %s @ %s",
            sanitize_for_log(service.name),
            sanitize_for_log(service.endpoint),
        )  # codeql[py/cleartext-logging]

    def get(self, name: str) -> Optional[NanoService]:
        return self._registry.get(name)

    def find_by_capability(self, capability: str) -> List[NanoService]:
        names = self._capability_index.get(capability, [])
        return [self._registry[n] for n in names if self._registry[n].is_healthy]

    def list_all(self) -> List[Dict]:
        return [
            {
                "name": s.name,
                "endpoint": s.endpoint,
                "capabilities": s.capabilities,
                "healthy": s.is_healthy,
                "version": s.version,
            }
            for s in self._registry.values()
        ]

    def mark_unhealthy(self, name: str):
        if name in self._registry:
            self._registry[name].is_healthy = False
            logger.warning(
                "Nanoservice marked unhealthy: %s", sanitize_for_log(name)
            )  # codeql[py/cleartext-logging]

    def mark_healthy(self, name: str):
        if name in self._registry:
            self._registry[name].is_healthy = True
            self._registry[name].last_seen = time.time()


# Singleton
registry = NanoServiceRegistry()

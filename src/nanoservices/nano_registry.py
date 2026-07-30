# src/nanoservices/nano_registry.py
# TRANC3 Nanoservice Registry — service discovery and routing

import ast
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

_NANOSERVICES_ROOT = Path(__file__).resolve().parent


@dataclass
class NanoService:
    name: str
    # "http": exposed via nano_server.py's /nano/* FastAPI routes (port 8001).
    # "library": an importable src/nanoservices/<name>/ package with no HTTP
    # surface — discoverable metadata only, populated by
    # discover_library_modules().
    kind: str = "http"
    endpoint: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    health_url: Optional[str] = None
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

    def __init__(self, discover_library_modules: bool = True):
        self._registry: Dict[str, NanoService] = {}
        self._capability_index: Dict[str, List[str]] = {}
        self._load_defaults()
        if discover_library_modules:
            discover_library_nanoservices(self)

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
        )

    def get(self, name: str) -> Optional[NanoService]:
        return self._registry.get(name)

    def find_by_capability(self, capability: str) -> List[NanoService]:
        names = self._capability_index.get(capability, [])
        return [self._registry[n] for n in names if self._registry[n].is_healthy]

    def list_all(self) -> List[Dict]:
        return [
            {
                "name": s.name,
                "kind": s.kind,
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
            logger.warning("Nanoservice marked unhealthy: %s", sanitize_for_log(name))

    def mark_healthy(self, name: str):
        if name in self._registry:
            self._registry[name].is_healthy = True
            self._registry[name].last_seen = time.time()


def _parse_package_metadata(init_path: Path) -> tuple[str, List[str]]:
    """AST-parse a nanoservice package's __init__.py for its module
    docstring and __all__ list, without importing it — these packages can
    carry heavy or optional dependencies (qiskit, ROS2 bindings, etc.) not
    installed in every environment, so importing 48 of them just to build
    a discovery registry would be unsafe."""
    try:
        tree = ast.parse(init_path.read_text())
    except (SyntaxError, OSError, UnicodeDecodeError):
        return "", []
    docstring = ast.get_docstring(tree) or ""
    exported: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                exported = [
                    elt.value
                    for elt in node.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
    return docstring, exported


def discover_library_nanoservices(registry: "NanoServiceRegistry") -> int:
    """Register every src/nanoservices/<name>/ package not already covered
    by SERVICES (i.e. not exposed over HTTP by nano_server.py's /nano/*
    routes) as a `kind="library"` entry — discoverable metadata (module
    path, docstring, exported symbols) rather than a live, health-checked
    endpoint. Closes the gap where only 13/61 module directories under
    src/nanoservices/ were previously registered at all. Returns the count
    of newly-registered packages."""
    registered = 0
    for child in sorted(_NANOSERVICES_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith("_") or child.name == "rust":
            continue
        if registry.get(child.name) is not None:
            continue
        init_path = child / "__init__.py"
        if not init_path.is_file():
            continue
        docstring, exported = _parse_package_metadata(init_path)
        registry.register(
            NanoService(
                name=child.name,
                kind="library",
                capabilities=exported,
                metadata={
                    "module_path": f"src.nanoservices.{child.name}",
                    "docstring": docstring,
                },
            )
        )
        registered += 1
    return registered


# Singleton
registry = NanoServiceRegistry()

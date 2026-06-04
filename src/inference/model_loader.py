# src/inference/model_loader.py
# Lazy model loading — defer heavy ML model initialization until first request

import logging
import threading
from typing import Any, Callable, Dict

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class LazyModelLoader:
    """
    Thread-safe lazy loader for ML models.
    Models are loaded on first access, not at startup.
    Supports unloading to free GPU/CPU memory.
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._loaded: Dict[str, bool] = {}
        self._lock = threading.Lock()

    def register(self, name: str, factory: Callable) -> None:
        """Register a model factory function"""
        self._factories[name] = factory
        logger.debug("Registered model factory: %s", sanitize_for_log(name))

    def get(self, name: str) -> Any:
        """Get a model, loading it lazily on first access"""
        if name in self._models:
            return self._models[name]

        if name not in self._factories:
            raise KeyError(f"Model '{name}' not registered")

        with self._lock:
            # Double-check after acquiring lock
            if name in self._models:
                return self._models[name]

            logger.info("Loading model: %s...", sanitize_for_log(name))
            try:
                model = self._factories[name]()
                self._models[name] = model
                self._loaded[name] = True
                logger.info("Model loaded: %s", sanitize_for_log(name))
                return model
            except Exception as e:
                logger.error(
                    "Failed to load model '%s': %s",
                    sanitize_for_log(name),
                    sanitize_for_log(e),
                )
                raise

    def is_loaded(self, name: str) -> bool:
        """Check if a model is currently loaded"""
        return self._loaded.get(name, False)

    def unload(self, name: str) -> bool:
        """Unload a model to free memory"""
        with self._lock:
            if name in self._models:
                del self._models[name]
                self._loaded[name] = False
                logger.info("Unloaded model: %s", sanitize_for_log(name))
                return True
            return False

    def preload(self, *names: str) -> None:
        """Pre-load multiple models"""
        for name in names:
            try:
                self.get(name)
            except Exception as e:
                logger.error(
                    "Pre-load failed for %s: %s",
                    sanitize_for_log(name),
                    sanitize_for_log(e),
                )

    def status(self) -> Dict[str, Dict[str, Any]]:
        """Get loading status for all models"""
        return {
            name: {
                "loaded": self._loaded.get(name, False),
                "registered": name in self._factories,
            }
            for name in self._factories
        }


class InferenceRouter:
    """
    Routes inference requests to appropriate models based on capability.
    Implements the zero-cost 5-tier fallback chain:
    Tranc3Engine → Ollama → OpenRouter → HuggingFace → Stub
    """

    def __init__(self, config=None):
        self.config = config
        self._providers: Dict[str, Any] = {}
        self._fallback_chain: list = []

    def register_provider(self, name: str, provider: Any, priority: int = 0) -> None:
        """Register an inference provider with a priority"""
        self._providers[name] = provider
        # Insert sorted by priority (lower = higher priority)
        self._fallback_chain = sorted(
            [
                (n, p, pr)
                for n, p, pr in [(n, p, self._get_priority(n)) for n, p in self._providers.items()]
                if True
            ],
            key=lambda x: x[2],
        )

    def _get_priority(self, name: str) -> int:
        """Get priority for a provider based on config"""
        priorities = {
            "tranc3": 0,
            "ollama": 10,
            "openrouter": 20,
            "huggingface": 30,
            "stub": 100,
        }
        return priorities.get(name, 50)

    async def infer(self, prompt: str, **kwargs) -> Any:
        """Run inference with fallback chain"""
        last_error = None
        for name in self._providers:
            provider = self._providers[name]
            try:
                result = await provider.generate(prompt, **kwargs)
                logger.debug("Inference succeeded via %s", sanitize_for_log(name))
                return result
            except Exception as e:
                logger.warning(
                    "Provider %s failed: %s",
                    sanitize_for_log(name),
                    sanitize_for_log(e),
                )
                last_error = e
                continue

        raise RuntimeError(f"All inference providers failed. Last error: {last_error}")


# Singleton instances
model_loader = LazyModelLoader()
inference_router = InferenceRouter()

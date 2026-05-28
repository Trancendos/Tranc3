import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

logger = logging.getLogger(__name__)

# Task routing table: maps task-type strings to preferred backend
_TASK_ROUTING: Dict[str, str] = {
    "classification": "torch",
    "generation": "torch",
    "embedding": "torch",
    "regression": "torch",
    "rl_action": "tf",
    "sequence_classification": "tf",
    "dqn": "tf",
}


@dataclass
class HybridConfig:
    """Configuration for the hybrid PyTorch + TensorFlow inference engine."""

    prefer_torch: bool = True
    tf_fallback: bool = True
    device: str = "cpu"
    batch_size: int = 32


class ModelEnsemble:
    """Weighted ensemble of a PyTorch model and a TensorFlow model.

    Both models are called asynchronously; if one is unavailable its
    weight is redistributed to the other (effective weight normalisation).

    Attributes:
        torch_model: Any callable that accepts a dict and returns np.ndarray.
        tf_model:    Any callable (TF/Keras model or wrapper) returning np.ndarray.
        weights:     (torch_weight, tf_weight) summing to 1.0.
    """

    def __init__(
        self,
        torch_model: Optional[Any] = None,
        tf_model: Optional[Any] = None,
        weights: Tuple[float, float] = (0.6, 0.4),
    ) -> None:
        self.torch_model = torch_model
        self.tf_model = tf_model
        self._weights = weights

    async def predict(self, inputs: Dict) -> Dict:
        """Run both models and return a weighted-average ensemble prediction.

        If one model is unavailable the other receives full weight.
        If both fail, returns a zero-filled fallback.

        Args:
            inputs: Dict containing at least an "array" key with np.ndarray data.

        Returns:
            Dict with keys:
              "output"       – ensemble prediction array
              "torch_output" – raw torch prediction (or None)
              "tf_output"    – raw tf prediction (or None)
              "weights_used" – (w_torch, w_tf) actually applied
        """
        loop = asyncio.get_event_loop()

        # Run both models in the thread pool so neither blocks the event loop
        torch_task = loop.run_in_executor(None, self._torch_predict, inputs)
        tf_task = loop.run_in_executor(None, self._tf_predict, inputs)

        torch_out, tf_out = await asyncio.gather(torch_task, tf_task, return_exceptions=True)

        w_torch, w_tf = self._weights
        torch_ok = isinstance(torch_out, np.ndarray)  # type: ignore[has-type]
        tf_ok = isinstance(tf_out, np.ndarray)  # type: ignore[has-type]

        if not torch_ok:
            if isinstance(torch_out, Exception):  # type: ignore[has-type]
                logger.warning("Torch model failed: %s", torch_out)  # type: ignore[has-type]
            torch_out = None

        if not tf_ok:
            if isinstance(tf_out, Exception):  # type: ignore[has-type]
                logger.warning("TF model failed: %s", tf_out)  # type: ignore[has-type]
            tf_out = None

        # Normalise weights based on availability
        if torch_ok and tf_ok:
            effective_w_torch, effective_w_tf = w_torch, w_tf
            ensemble = w_torch * torch_out + w_tf * tf_out  # type: ignore[operator]
        elif torch_ok:
            effective_w_torch, effective_w_tf = 1.0, 0.0
            ensemble = torch_out  # type: ignore[assignment]
        elif tf_ok:
            effective_w_torch, effective_w_tf = 0.0, 1.0
            ensemble = tf_out  # type: ignore[assignment]
        else:
            logger.error("Both models failed — returning zero prediction")
            # Attempt to infer shape from inputs
            arr = inputs.get("array", inputs.get("input"))
            if arr is not None and hasattr(arr, "shape"):
                out_shape = (arr.shape[0], 1)
            else:
                out_shape = (1, 1)
            ensemble = np.zeros(out_shape, dtype=np.float32)  # type: ignore[assignment]
            effective_w_torch, effective_w_tf = 0.0, 0.0

        return {
            "output": ensemble,
            "torch_output": torch_out,
            "tf_output": tf_out,
            "weights_used": (effective_w_torch, effective_w_tf),
        }

    def _torch_predict(self, inputs: Dict) -> np.ndarray:
        """Synchronous PyTorch forward pass.

        Falls back to a random projection if no model is provided.

        Args:
            inputs: Must contain "array" or "tensor" key.

        Returns:
            NumPy array of predictions.
        """
        arr = inputs.get("array", inputs.get("tensor"))
        if arr is None:
            raise ValueError("inputs must contain 'array' or 'tensor' key")

        if self.torch_model is not None:
            try:
                t = torch.from_numpy(np.array(arr, dtype=np.float32))
                with torch.no_grad():
                    out = self.torch_model(t)
                if isinstance(out, torch.Tensor):
                    return out.numpy()
                return np.array(out, dtype=np.float32)
            except Exception as exc:
                raise RuntimeError(f"Torch forward pass failed: {exc}") from exc
        else:
            # Default: identity / passthrough reduced to output_dim=1 per row
            data = np.array(arr, dtype=np.float32)
            return data.mean(axis=-1, keepdims=True)

    def _tf_predict(self, inputs: Dict) -> np.ndarray:
        """Synchronous TensorFlow forward pass.

        Falls back gracefully if TF is not available or model is None.

        Args:
            inputs: Must contain "array" or "tensor" key.

        Returns:
            NumPy array of predictions.
        """
        arr = inputs.get("array", inputs.get("tensor"))
        if arr is None:
            raise ValueError("inputs must contain 'array' or 'tensor' key")

        if self.tf_model is not None:
            try:
                result = self.tf_model(np.array(arr, dtype=np.float32))
                if hasattr(result, "numpy"):
                    return result.numpy()
                return np.array(result, dtype=np.float32)
            except Exception as exc:
                raise RuntimeError(f"TF forward pass failed: {exc}") from exc
        else:
            # Default: column-wise normalised mean
            data = np.array(arr, dtype=np.float32)
            out = data.mean(axis=-1, keepdims=True)
            return out


class HybridInferenceEngine:
    """Unified inference router supporting PyTorch, TensorFlow, and ensembles.

    Maintains a registry of loaded models and routes inference requests based
    on the task type and model availability.  All inference is async to avoid
    blocking the event loop; heavy computation is offloaded to thread-pool
    executors via ``asyncio.get_event_loop().run_in_executor``.

    Singleton pattern: use the module-level ``hybrid_engine`` instance.
    """

    def __init__(self, config: HybridConfig) -> None:
        self.config = config
        self._torch_models: Dict[str, Any] = {}
        self._tf_models: Dict[str, Any] = {}
        self._ensembles: Dict[str, ModelEnsemble] = {}
        self._device = torch.device(config.device)
        self._tf_available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Model registry
    # ------------------------------------------------------------------

    def register_torch_model(self, name: str, model: Any) -> None:
        """Register a PyTorch model under ``name``."""
        self._torch_models[name] = model
        logger.debug("Registered torch model: %s", name)

    def register_tf_model(self, name: str, model: Any) -> None:
        """Register a TF/Keras model under ``name``."""
        self._tf_models[name] = model
        logger.debug("Registered TF model: %s", name)

    def register_ensemble(self, name: str, ensemble: ModelEnsemble) -> None:
        """Register a pre-built ModelEnsemble under ``name``."""
        self._ensembles[name] = ensemble
        logger.debug("Registered ensemble: %s", name)

    # ------------------------------------------------------------------
    # Core inference
    # ------------------------------------------------------------------

    async def infer(
        self,
        task: str,
        inputs: Dict,
        model_hint: str = "auto",
    ) -> Dict:
        """Route an inference request to the appropriate backend.

        Routing logic:
          1. If ``model_hint`` matches a registered ensemble, use it.
          2. Else if ``model_hint`` is "ensemble", build an ad-hoc ensemble.
          3. Else resolve backend from _TASK_ROUTING and availability.
          4. Fall back to alternative backend if primary unavailable.

        Args:
            task:        Task type string (e.g. "classification", "rl_action").
            inputs:      Input dict passed through to the model.
            model_hint:  "auto" | "torch" | "tf" | "ensemble" | registered name.

        Returns:
            Dict containing at minimum "output" (np.ndarray) and "backend" (str).
        """
        # Check ensemble registry first
        if model_hint in self._ensembles:
            result = await self._ensembles[model_hint].predict(inputs)
            result["backend"] = "ensemble"
            result["task"] = task
            return result

        if model_hint == "ensemble":
            # Ad-hoc ensemble from registered models
            torch_m = next(iter(self._torch_models.values()), None)
            tf_m = next(iter(self._tf_models.values()), None)
            ens = ModelEnsemble(torch_model=torch_m, tf_model=tf_m)
            result = await ens.predict(inputs)
            result["backend"] = "ensemble"
            result["task"] = task
            return result

        # Determine preferred backend
        if model_hint in ("torch", "tf"):
            preferred = model_hint
        else:
            preferred = _TASK_ROUTING.get(task, "torch" if self.config.prefer_torch else "tf")

        output, backend = await self._route(task, inputs, preferred)
        return {"output": output, "backend": backend, "task": task}

    async def _route(self, task: str, inputs: Dict, preferred: str) -> Tuple[np.ndarray, str]:
        """Internal routing with fallback logic.

        Args:
            task:      Task type string.
            inputs:    Model inputs.
            preferred: "torch" or "tf".

        Returns:
            (output_array, backend_used).
        """
        loop = asyncio.get_event_loop()

        async def _try_torch() -> np.ndarray:
            return await loop.run_in_executor(None, self._dispatch_torch, task, inputs)

        async def _try_tf() -> np.ndarray:
            return await loop.run_in_executor(None, self._dispatch_tf, task, inputs)

        if preferred == "torch":
            try:
                out = await _try_torch()
                return out, "torch"
            except Exception as exc:
                logger.warning("Torch dispatch failed (%s), falling back to TF: %s", task, exc)
                if self.config.tf_fallback:
                    try:
                        out = await _try_tf()
                        return out, "tf_fallback"
                    except Exception as exc2:
                        logger.error("TF fallback also failed: %s", exc2)
        else:
            try:
                out = await _try_tf()
                return out, "tf"
            except Exception as exc:
                logger.warning("TF dispatch failed (%s), falling back to Torch: %s", task, exc)
                if self.config.prefer_torch or self.config.tf_fallback:
                    try:
                        out = await _try_torch()
                        return out, "torch_fallback"
                    except Exception as exc2:
                        logger.error("Torch fallback also failed: %s", exc2)

        # Both paths failed — return zeros
        arr = inputs.get("array", inputs.get("tensor"))
        out_shape = (1, 1) if arr is None else (np.array(arr).shape[0], 1)
        return np.zeros(out_shape, dtype=np.float32), "failed"

    def _dispatch_torch(self, task: str, inputs: Dict) -> np.ndarray:
        """Run a synchronous PyTorch inference step.

        Looks up a registered torch model for the task, or uses a generic
        linear projection as a default.

        Args:
            task:   Task type string used as model lookup key.
            inputs: Must contain "array" or "tensor".

        Returns:
            NumPy output array.
        """
        arr = inputs.get("array", inputs.get("tensor"))
        if arr is None:
            raise ValueError("inputs must contain 'array' or 'tensor'")

        data = torch.from_numpy(np.array(arr, dtype=np.float32)).to(self._device)

        model = self._torch_models.get(task) or next(iter(self._torch_models.values()), None)

        if model is not None:
            with torch.no_grad():
                model.eval()
                out = model(data)
            if isinstance(out, torch.Tensor):
                return out.cpu().numpy()
            return np.array(out, dtype=np.float32)

        # Default: channel-wise mean → shape (B, 1)
        return data.mean(dim=-1, keepdim=True).cpu().numpy()

    def _dispatch_tf(self, task: str, inputs: Dict) -> np.ndarray:
        """Run a synchronous TensorFlow inference step.

        Looks up a registered TF model for the task.  If TF is unavailable
        or no model registered, raises RuntimeError to trigger fallback.

        Args:
            task:   Task type string used as model lookup key.
            inputs: Must contain "array" or "tensor".

        Returns:
            NumPy output array.
        """
        if self._tf_available is None:
            try:
                self._tf_available = True
            except ImportError:
                self._tf_available = False

        if not self._tf_available:
            raise RuntimeError("TensorFlow not available")

        arr = inputs.get("array", inputs.get("tensor"))
        if arr is None:
            raise ValueError("inputs must contain 'array' or 'tensor'")

        model = self._tf_models.get(task) or next(iter(self._tf_models.values()), None)

        if model is not None:
            import tensorflow as tf

            x = tf.constant(np.array(arr, dtype=np.float32))
            out = model(x, training=False)
            if hasattr(out, "numpy"):
                return out.numpy()
            return np.array(out, dtype=np.float32)

        raise RuntimeError(f"No TF model registered for task '{task}'")

    # ------------------------------------------------------------------
    # Batch inference
    # ------------------------------------------------------------------

    async def batch_infer(self, tasks: List[Dict]) -> List[Dict]:
        """Run inference on a list of tasks concurrently.

        Each element of ``tasks`` must have keys "task" and "inputs", and
        optionally "model_hint".  Results are returned in the same order.

        Args:
            tasks: List of inference request dicts.

        Returns:
            List of result dicts, one per input task.
        """
        batch_tasks = []
        for t in tasks:
            task_type = t.get("task", "classification")
            inputs = t.get("inputs", {})
            hint = t.get("model_hint", "auto")
            batch_tasks.append(self.infer(task_type, inputs, hint))

        results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        output: List[Dict] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error("batch_infer task %d failed: %s", i, res)
                output.append({"output": None, "error": str(res), "task": tasks[i].get("task")})
            else:
                output.append(res)  # type: ignore[arg-type]

        return output

    # ------------------------------------------------------------------
    # Device / framework info
    # ------------------------------------------------------------------

    def get_device_info(self) -> Dict:
        """Return GPU/CPU availability and framework version information.

        Returns:
            Dict with keys: "torch_device", "torch_cuda", "torch_gpu_name",
            "tf_available", "tf_gpus", "torch_version", "tf_version".
        """
        info: Dict[str, Any] = {}

        # PyTorch
        info["torch_device"] = str(self._device)
        info["torch_cuda"] = torch.cuda.is_available()
        info["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            info["torch_gpu_count"] = torch.cuda.device_count()
            info["torch_gpu_name"] = torch.cuda.get_device_name(0)
        else:
            info["torch_gpu_count"] = 0
            info["torch_gpu_name"] = None

        # TensorFlow
        if self._tf_available is None:
            try:
                self._tf_available = True
            except ImportError:
                self._tf_available = False

        info["tf_available"] = self._tf_available

        if self._tf_available:
            try:
                import tensorflow as tf

                info["tf_version"] = tf.__version__
                gpus = tf.config.list_physical_devices("GPU")
                info["tf_gpus"] = [g.name for g in gpus]
                info["tf_gpu_count"] = len(gpus)
            except Exception as exc:
                info["tf_version"] = "unknown"
                info["tf_gpus"] = []
                info["tf_gpu_count"] = 0
                info["tf_error"] = str(exc)
        else:
            info["tf_version"] = None
            info["tf_gpus"] = []
            info["tf_gpu_count"] = 0

        # Registered models summary
        info["registered_torch_models"] = list(self._torch_models.keys())
        info["registered_tf_models"] = list(self._tf_models.keys())
        info["registered_ensembles"] = list(self._ensembles.keys())

        return info


# Module-level singleton — usable directly after import
hybrid_engine = HybridInferenceEngine(HybridConfig())

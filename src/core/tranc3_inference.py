# src/core/tranc3_inference.py
# TRANC3 local inference engine — wraps AdvancedTransformerModel + Tranc3Tokenizer.
# No external API. No one else's weights. Pure Tranc3.

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import torch

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = os.getenv(
    "TRANC3_MODEL_PATH", "./models/tranc3-v1/tranc3-final.pt"
)
_DEFAULT_TOKENIZER_PATH = os.getenv("TRANC3_TOKENIZER_PATH", "./models/tokenizer")

# Generation defaults (overridable per-call)
_DEFAULT_TEMPERATURE = 0.8
_DEFAULT_TOP_P = 0.9
_DEFAULT_TOP_K = 50
_DEFAULT_MAX_NEW_TOKENS = 256
_DEFAULT_REP_PENALTY = 1.1


class Tranc3Engine:
    """
    The real TRANC3 inference engine.

    On first call, loads model weights and tokenizer from disk.
    If weights don't exist yet (model not trained), runs in bootstrap mode
    (returns a structured placeholder response) so the rest of the system
    keeps working while training is underway.

    Usage:
        engine = Tranc3Engine()
        result = await engine.generate("What is finance?", personality="dorris-fontaine")
        print(result["response"])
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        tokenizer_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self._model_path = Path(model_path or _DEFAULT_MODEL_PATH)
        self._tokenizer_path = Path(tokenizer_path or _DEFAULT_TOKENIZER_PATH)
        self._device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self._model = None
        self._tokenizer = None
        self._loaded = False
        self._bootstrap_mode = False

    # ─── Lifecycle ─────────────────────────────────────────────────────────────

    def load(self) -> "Tranc3Engine":
        """Load model + tokenizer. Call once at startup."""
        self._load_tokenizer()
        self._load_model()
        return self

    def _load_tokenizer(self):
        tok_path = self._tokenizer_path
        if not tok_path.exists() or not (tok_path / "tokenizer_meta.json").exists():
            logger.warning(
                "Tokenizer not found at %s — model not trained yet. "
                "Run: python train.py to train the Tranc3 model.",
                tok_path,
            )
            self._bootstrap_mode = True
            return

        from src.core.tranc3_tokenizer import Tranc3Tokenizer

        self._tokenizer = Tranc3Tokenizer.load(tok_path)
        logger.info("Tranc3 tokenizer loaded (vocab=%d)", len(self._tokenizer))

    def _load_model(self):
        if self._bootstrap_mode:
            return

        # Find checkpoint — prefer final, then best, then latest numbered
        checkpoint_path = self._resolve_checkpoint()
        if checkpoint_path is None:
            logger.warning(
                "No model weights found at %s — bootstrap mode active. "
                "Run: python train.py to produce weights.",
                self._model_path,
            )
            self._bootstrap_mode = True
            return

        try:
            checkpoint = torch.load(checkpoint_path, map_location=self._device, weights_only=True)

            # Reconstruct config from saved state
            state_dict = checkpoint["model_state_dict"]
            vocab_size = state_dict["token_embeddings.weight"].shape[0]
            hidden_size = state_dict["token_embeddings.weight"].shape[1]
            num_layers = sum(
                1
                for k in state_dict
                if k.startswith("layers.") and k.endswith(".norm1.weight")
            )
            num_heads = hidden_size // 64  # convention: head_dim = 64

            class _Cfg:
                pass

            cfg = _Cfg()
            cfg.vocab_size = vocab_size
            cfg.hidden_size = hidden_size
            cfg.num_layers = num_layers
            cfg.num_heads = num_heads
            cfg.max_sequence_length = 512
            cfg.dropout = 0.0  # no dropout at inference

            from src.core.advanced_model import AdvancedTransformerModel

            self._model = AdvancedTransformerModel(cfg)
            self._model.load_state_dict(state_dict, strict=True)
            self._model.eval()
            self._model = self._model.to(self._device)

            n_params = sum(p.numel() for p in self._model.parameters())
            logger.info(
                "TRANC3 model loaded from %s — %.2fM params, device=%s",
                checkpoint_path,
                n_params / 1e6,
                self._device,
            )
            self._loaded = True

        except Exception as exc:
            logger.error("Model load failed: %s — running in bootstrap mode", exc)
            self._bootstrap_mode = True

    def _resolve_checkpoint(self) -> Optional[Path]:
        base = (
            self._model_path if self._model_path.is_dir() else self._model_path.parent
        )

        for name in ("tranc3-final.pt", "tranc3-best.pt"):
            candidate = base / name
            if candidate.exists():
                return candidate

        # Find latest numbered checkpoint
        checkpoints = sorted(
            base.glob("checkpoint-*.pt"), key=lambda p: int(p.stem.split("-")[1])
        )
        if checkpoints:
            return checkpoints[-1]

        # Direct path
        if self._model_path.exists() and self._model_path.suffix == ".pt":
            return self._model_path

        return None

    # ─── Generation ────────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        personality: str = "tranc3-base",
        personality_vector: Optional[torch.Tensor] = None,
        system_prompt: Optional[str] = None,
        max_new_tokens: int = _DEFAULT_MAX_NEW_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
        top_p: float = _DEFAULT_TOP_P,
        top_k: int = _DEFAULT_TOP_K,
        repetition_penalty: float = _DEFAULT_REP_PENALTY,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response to `prompt` using the local TRANC3 model.
        Returns a dict with at minimum {"response": str, "personality": str}.
        """
        if not self._loaded and not self._bootstrap_mode:
            self.load()

        if self._bootstrap_mode:
            return await self._bootstrap_response_async(
                prompt, personality, system_prompt
            )

        # Build chat-formatted input
        sys_text = system_prompt or self._default_system(personality)
        input_ids = self._tokenizer.encode_chat(
            system=sys_text,
            turns=[{"role": "user", "content": prompt}],
            personality=personality,
            max_length=256,
        )
        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=self._device)

        # Get personality vector if available
        pers_tensor = None
        if personality_vector is not None:
            pers_tensor = personality_vector.to(self._device).unsqueeze(0)

        # Generate
        with torch.no_grad():
            generated = self._model.generate(
                input_ids=input_tensor,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                repetition_penalty=repetition_penalty,
                personality_vector=pers_tensor,
            )

        # Decode only the newly generated tokens (after the input)
        new_ids = generated[0, input_tensor.shape[1] :].tolist()
        response_text = self._tokenizer.decode(
            new_ids, skip_special_tokens=True
        ).strip()

        return {
            "response": response_text,
            "personality": personality,
            "model": "tranc3-local",
            "tokens": len(new_ids),
        }

    def generate_sync(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Synchronous version of generate() for non-async callers."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.generate(prompt, **kwargs))
        finally:
            loop.close()

    def _default_system(self, personality: str) -> str:
        systems = {
            "tranc3-base": "You are TRANC3, a balanced, intelligent AI assistant.",
            "dorris-fontaine": "You are Dorris Fontaine, TRANC3's financial specialist. You provide precise, regulation-aware financial analysis.",
            "cornelius-macintyre": "You are Cornelius MacIntyre, TRANC3's orchestration specialist. You coordinate complex multi-system tasks with strategic clarity.",
            "the-guardian": "You are The Guardian, TRANC3's cybersecurity specialist. You identify threats, enforce compliance, and protect systems.",
            "vesper-nightingale": "You are Vesper Nightingale, TRANC3's healthcare advisor. You provide evidence-based health guidance with warmth and care.",
            "atlas-meridian": "You are Atlas Meridian, TRANC3's infrastructure specialist. You architect resilient, scalable, cost-efficient systems.",
            "tranc3-creative": "You are TRANC3, a highly creative AI with a flair for imagination and original thinking.",
            "tranc3-analytical": "You are TRANC3, a precision-focused analytical AI driven by data and logic.",
            "tranc3-empathetic": "You are TRANC3, a deeply empathetic AI that listens carefully and responds with warmth.",
        }
        return systems.get(personality, "You are TRANC3, an advanced AI assistant.")

    async def _bootstrap_response_async(
        self,
        prompt: str,
        personality: str,
        override_system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Async bootstrap: tries Ollama (free local) → OpenRouter (free cloud) →
        honest stub.  Called from generate() when model weights are absent.
        """
        sys_text = override_system or self._default_system(personality)

        # Tier 1: local Ollama (zero-cost, fully self-owned)
        try:
            from src.core.ollama_adapter import is_available, generate as ollama_gen

            if await is_available():
                result = await ollama_gen(prompt=prompt, system_prompt=sys_text)
                if result:
                    result["personality"] = personality
                    return result
        except Exception as exc:
            logger.debug("tranc3.bootstrap ollama: %s", exc)

        # Tier 2: OpenRouter free models (cloud, zero-cost)
        try:
            from src.core.openrouter_adapter import generate as or_gen

            result = await or_gen(prompt=prompt, system_prompt=sys_text)
            if result:
                result["personality"] = personality
                return result
        except Exception as exc:
            logger.debug("tranc3.bootstrap openrouter: %s", exc)

        # Tier 3: honest stub
        return {
            "response": (
                f"TRANC3 ({personality}) is initialising. "
                "The language model weights are not yet trained. "
                "Run `python train.py` to train the Tranc3 model from scratch, "
                "then restart the service. "
                f"Your message was: '{prompt[:100]}'"
            ),
            "personality": personality,
            "model": "tranc3-bootstrap",
            "trained": False,
            "action_required": "python train.py",
        }

    def _bootstrap_response(self, prompt: str, personality: str) -> Dict[str, Any]:
        """Synchronous bootstrap stub — used only by generate_sync()."""
        return {
            "response": (
                f"TRANC3 ({personality}) is initialising. "
                "The language model weights are not yet trained. "
                "Run `python train.py` to train the Tranc3 model from scratch, "
                "then restart the service. "
                f"Your message was: '{prompt[:100]}'"
            ),
            "personality": personality,
            "model": "tranc3-bootstrap",
            "trained": False,
            "action_required": "python train.py",
        }

    # ─── Status ────────────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "loaded": self._loaded,
            "bootstrap_mode": self._bootstrap_mode,
            "model_path": str(self._model_path),
            "tokenizer_path": str(self._tokenizer_path),
            "device": str(self._device),
        }


# Module-level singleton — imported by main_enhanced.py
_engine: Optional[Tranc3Engine] = None


def get_engine() -> Tranc3Engine:
    """Return the singleton inference engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = Tranc3Engine()
        _engine.load()
    return _engine

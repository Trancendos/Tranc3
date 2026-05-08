# src/core/context_compressor.py
# ContextCompressor — Brainwriting R1 action
# Summarises old conversation turns to extend effective context window

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextCompressor:
    """
    Compresses long conversation histories to fit within the model's context window.
    Uses extractive summarisation (no external model needed) for zero-cost operation.
    Swap _summarise() for BART/T5 when GPU is available.
    """

    def __init__(self, max_tokens: int = 512, keep_recent: int = 6):
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent  # Always keep last N turns verbatim

    def compress(self, history: List[Dict]) -> List[Dict]:
        """
        Compress conversation history.
        Returns a list of messages that fits within max_tokens.
        """
        if len(history) <= self.keep_recent:
            return history

        # Keep recent turns verbatim
        recent = history[-self.keep_recent:]
        older = history[:-self.keep_recent]

        if not older:
            return recent

        # Summarise older turns
        summary_text = self._summarise(older)
        summary_message = {
            "role": "system",
            "content": f"[Conversation summary]: {summary_text}",
        }

        return [summary_message] + recent

    def _summarise(self, messages: List[Dict]) -> str:
        """
        Extractive summarisation — picks key sentences.
        Replace with BART/T5 for abstractive summarisation.
        """
        sentences = []
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            # Take first sentence of each message
            first_sentence = content.split(".")[0].strip()
            if first_sentence:
                sentences.append(f"{role}: {first_sentence}")

        return " | ".join(sentences[:5])  # Cap at 5 key points

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return len(text) // 4

    def fits_in_context(self, history: List[Dict]) -> bool:
        total = sum(self.estimate_tokens(m.get("content", "")) for m in history)
        return total <= self.max_tokens


# Singleton
compressor = ContextCompressor()

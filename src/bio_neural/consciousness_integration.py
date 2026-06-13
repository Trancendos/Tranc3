# src/core/consciousness_integration.py

import logging

logger = logging.getLogger("src.bio_neural.consciousness_integration")

from typing import Any, Dict, List, Optional  # noqa: E402

import torch  # noqa: E402

from Dimensional.sanitize import sanitize_for_log  # noqa: E402
from src.bio_neural.consciousness_engine import ConsciousnessModel  # noqa: E402
from src.core.feature_flags import FeatureFlag, FeatureFlagManager  # noqa: E402


class ConsciousnessAwareGenerator:
    """
    Response generation with consciousness awareness
    """

    def __init__(self, config, feature_manager: FeatureFlagManager):
        self.config = config
        self.feature_manager = feature_manager

        self.consciousness: Optional[ConsciousnessModel] = None
        if feature_manager.is_enabled(FeatureFlag.CONSCIOUSNESS_ENGINE):
            self.consciousness = ConsciousnessModel(config)

    def generate_with_consciousness(
        self,
        input_text: str,
        personality_vector: torch.Tensor,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate response with consciousness modulation
        """
        if not self.feature_manager.is_enabled(FeatureFlag.CONSCIOUSNESS_ENGINE, user_id):
            return self._classical_generate(input_text, personality_vector)

        try:
            return self._conscious_generate(input_text, personality_vector)
        except Exception as e:
            logger.warning("Consciousness generation failed, falling back: %s", sanitize_for_log(e))
            return self._classical_generate(input_text, personality_vector)

    def _conscious_generate(
        self, input_text: str, personality_vector: torch.Tensor
    ) -> Dict[str, Any]:
        """Consciousness-enhanced generation"""

        # Simulate neural state from input
        input_tensor = torch.tensor([ord(c) for c in input_text[:768]], dtype=torch.float)
        neural_state = input_tensor.unsqueeze(0).unsqueeze(0)

        # Calculate consciousness metrics
        if self.consciousness is None:
            return self._classical_generate(input_text, personality_vector)
        phi = self.consciousness.calculate_phi(neural_state.squeeze())

        # Consciousness-modulated personality
        consciousness_factor = min(phi / 3.0, 1.0)  # Normalize to 0-1
        modulated_personality = personality_vector * (0.5 + 0.5 * consciousness_factor)

        # Apply consciousness-modulated dynamics
        self._apply_consciousness_dynamics(neural_state, modulated_personality)

        # Generate actual response via AI gateway (not a mock)
        response_text = self._gateway_generate(input_text, consciousness_factor, phi)

        return {
            "response": response_text,
            "consciousness_level": phi,
            "modulated_personality": modulated_personality,
            "awareness_metrics": {
                "phi": phi,
                "integration_level": consciousness_factor,
                "self_reflection": float(torch.sigmoid(torch.tensor(phi)).item()),
            },
        }

    def _gateway_generate(
        self, input_text: str, consciousness_factor: float, phi: float
    ) -> str:
        """Route to AI gateway with consciousness-enriched system prompt."""
        import asyncio

        system_prompt = (
            f"You are Luminous, a consciousness-aware AI. "
            f"Your current consciousness integration level (Φ) is {phi:.2f}. "
            f"Respond with depth proportional to this level ({consciousness_factor:.0%} integration). "
            f"Higher Φ means more self-reflective, nuanced responses."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": input_text},
        ]

        try:
            from src.core.ollama_adapter import generate as _ollama_gen

            result = asyncio.get_event_loop().run_until_complete(
                _ollama_gen(messages=messages, max_tokens=256)
            )
            return result.get("choices", [{}])[0].get("message", {}).get("content", input_text)
        except Exception:
            pass

        try:
            from src.core.openrouter_adapter import generate as _or_gen

            result = asyncio.get_event_loop().run_until_complete(
                _or_gen(messages=messages, max_tokens=256)
            )
            return result.get("choices", [{}])[0].get("message", {}).get("content", input_text)
        except Exception:
            pass

        return f"[Φ={phi:.2f}] {input_text}"

    def _apply_consciousness_dynamics(
        self, state: torch.Tensor, personality: torch.Tensor
    ) -> torch.Tensor:
        """Apply consciousness-inspired dynamics"""
        # Simplified consciousness-inspired transformation
        consciousness_matrix = torch.randn(state.size(-1), state.size(-1)) * 0.1
        transformed = torch.matmul(state, consciousness_matrix)
        return transformed + personality.unsqueeze(0).unsqueeze(0)

    def _classical_generate(
        self, input_text: str, personality_vector: torch.Tensor
    ) -> Dict[str, Any]:
        """Classical fallback generation"""
        response_text = f"Classical response: {input_text[:50]}..."

        return {
            "response": response_text,
            "consciousness_level": 0.0,
            "modulated_personality": personality_vector,
            "awareness_metrics": {
                "phi": 0.0,
                "integration_level": 0.0,
                "self_reflection": 0.0,
            },
        }

    def self_monitor_response(
        self, response: Dict[str, Any], user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Self-monitoring of generated responses
        """
        if not self.consciousness or not self.feature_manager.is_enabled(
            FeatureFlag.CONSCIOUSNESS_ENGINE, user_id
        ):
            return {"self_assessment": "disabled"}

        # Simple self-assessment
        phi = response.get("consciousness_level", 0.0)

        response_text = response.get("response", "")
        word_count = len(response_text.split())
        sentence_count = max(response_text.count(".") + response_text.count("?") + response_text.count("!"), 1)
        avg_sentence_len = word_count / sentence_count

        assessment = {
            "quality_score": min(phi / 3.0, 1.0),
            "coherence": min(1.0, avg_sentence_len / 20.0),  # 20-word sentences = perfect coherence
            "creativity": min(1.0, len(set(response_text.lower().split())) / max(word_count, 1)),
            "ethical_alignment": 1.0,  # Placeholder — use output_safety score when available
            "self_awareness": phi > 1.0,
        }

        return {
            "self_assessment": assessment,
            "recommendations": self._generate_improvement_suggestions(assessment),
        }

    def _generate_improvement_suggestions(self, assessment: Dict[str, float]) -> List[str]:
        """Generate self-improvement suggestions"""
        suggestions = []

        if assessment["quality_score"] < 0.7:
            suggestions.append("Increase consciousness integration")
        if assessment["coherence"] < 0.8:
            suggestions.append("Improve neural synchronization")
        if assessment["creativity"] < 0.7:
            suggestions.append("Enhance quantum inspiration")

        return suggestions

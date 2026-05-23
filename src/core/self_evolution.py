# src/core/self_evolution.py

import logging

logger = logging.getLogger("src.core.self_evolution")

from typing import Any, Dict, Optional  # noqa: E402

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from shared_core.sanitize import sanitize_for_log  # noqa: E402
from src.core.feature_flags import FeatureFlag, FeatureFlagManager  # noqa: E402
from src.evolution.self_improving_core import SelfEvolvingArchitecture  # noqa: E402


class SelfEvolvingInference:
    """
    Self-improving inference with evolutionary adaptation
    """

    def __init__(self, config, feature_manager: FeatureFlagManager):
        self.config = config
        self.feature_manager = feature_manager

        if feature_manager.is_enabled(FeatureFlag.SELF_EVOLUTION):
            self.evolution_engine = SelfEvolvingArchitecture(config)
        else:
            self.evolution_engine = None

    def adapt_model(
        self,
        input_data: torch.Tensor,
        feedback: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Optional[nn.Module]:
        """
        Adapt model based on feedback and usage patterns
        """
        if not self.feature_manager.is_enabled(FeatureFlag.SELF_EVOLUTION, user_id):
            return None

        try:
            return self._evolve_model(input_data, feedback)
        except Exception as e:
            logger.warning("Self-evolution failed: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
            return None

    def _evolve_model(self, input_data: torch.Tensor, feedback: Dict[str, Any]) -> nn.Module:
        """Core evolutionary adaptation"""

        # Extract feedback metrics
        quality_score = feedback.get("quality_score", 0.5)
        user_satisfaction = feedback.get("user_satisfaction", 0.5)

        # Calculate fitness
        fitness = (quality_score + user_satisfaction) / 2

        # Evolve architecture
        self.evolution_engine.evolve(num_generations=1)

        # Create adapted model layer
        adapted_layer = nn.Linear(input_data.size(-1), input_data.size(-1))

        # Apply evolutionary changes (simplified)
        with torch.no_grad():
            adaptation_matrix = torch.randn_like(adapted_layer.weight) * 0.1 * fitness
            adapted_layer.weight += adaptation_matrix

        return adapted_layer

    def apply_adaptation(
        self, base_output: torch.Tensor, adaptation_layer: nn.Module
    ) -> torch.Tensor:
        """Apply evolutionary adaptation to output"""
        return adaptation_layer(base_output)

    def collect_feedback(
        self, response: Dict[str, Any], user_feedback: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Collect and analyze feedback for evolution
        """
        feedback = {
            "response_length": len(response.get("response", "")),
            "processing_time": response.get("processing_time_ms", 0),
            "consciousness_level": response.get("consciousness_level", 0.0),
            "user_feedback": user_feedback or {},
        }

        # Calculate quality metrics
        feedback["quality_score"] = self._calculate_quality_score(feedback)

        return feedback

    def _calculate_quality_score(self, feedback: Dict[str, Any]) -> float:
        """Calculate response quality score"""
        score = 0.5  # Base score

        # Length appropriateness
        length = feedback["response_length"]
        if 50 <= length <= 500:
            score += 0.2

        # Processing efficiency
        time = feedback["processing_time"]
        if time < 1000:  # Less than 1 second
            score += 0.1

        # Consciousness bonus
        consciousness = feedback["consciousness_level"]
        score += min(consciousness / 3.0, 0.2)

        # User feedback
        user_rating = feedback["user_feedback"].get("rating", 3) / 5.0
        score = score * 0.8 + user_rating * 0.2

        return min(score, 1.0)

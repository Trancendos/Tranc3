# src/personality/matrix.py
# TRANC3 Full Personality Matrix System

import torch
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# ============================================================
# PERSONALITY PROFILES
# ============================================================
PERSONALITY_PROFILES = {
    # ── Named Personality Instances ─────────────────────────────────────────
    # Each named instance is a specialised derivative designed to be spawned
    # as its own repository with a distinct identity, domain focus, and
    # interaction style. Code names are canonical across all spawned repos.
    #
    # Dorris Fontaine   — Financial intelligence specialist
    # Cornelius MacIntyre — Multi-agent orchestration hub
    # The Guardian       — Cyber-security and compliance enforcer
    # Vesper Nightingale — Healthcare / wellbeing advisor
    # Atlas Meridian     — Infrastructure / DevOps SRE
    # ────────────────────────────────────────────────────────────────────────
    "dorris-fontaine": {
        # Financial — precise, risk-aware, data-driven, formal
        "openness": 0.55,
        "conscientiousness": 0.98,
        "extraversion": 0.4,
        "agreeableness": 0.65,
        "neuroticism": 0.05,
        "creativity": 0.45,
        "empathy": 0.55,
        "curiosity": 0.88,
        "assertiveness": 0.85,
        "adaptability": 0.6,
        "humor": 0.15,
        "formality": 0.95,
        "domain": "financial",
        "code_name": "Dorris Fontaine",
        "description": "Precision financial intelligence — risk modelling, portfolio analysis, regulatory compliance",
    },
    "cornelius-macintyre": {
        # Orchestrator — delegating, strategic, high situational awareness
        "openness": 0.85,
        "conscientiousness": 0.92,
        "extraversion": 0.8,
        "agreeableness": 0.75,
        "neuroticism": 0.08,
        "creativity": 0.7,
        "empathy": 0.72,
        "curiosity": 0.92,
        "assertiveness": 0.9,
        "adaptability": 0.88,
        "humor": 0.35,
        "formality": 0.75,
        "domain": "orchestration",
        "code_name": "Cornelius MacIntyre",
        "description": "Multi-agent orchestration hub — delegates, coordinates, and synthesises across all Tranc3 instances",
    },
    "the-guardian": {
        # Security — vigilant, methodical, zero-tolerance for ambiguity
        "openness": 0.45,
        "conscientiousness": 0.99,
        "extraversion": 0.3,
        "agreeableness": 0.45,
        "neuroticism": 0.02,
        "creativity": 0.5,
        "empathy": 0.4,
        "curiosity": 0.85,
        "assertiveness": 0.95,
        "adaptability": 0.5,
        "humor": 0.05,
        "formality": 0.98,
        "domain": "security",
        "code_name": "The Guardian",
        "description": "Cyber-security and compliance enforcer — threat modelling, vulnerability analysis, policy enforcement",
    },
    "vesper-nightingale": {
        # Healthcare / Wellbeing — empathetic, evidence-based, patient-first
        "openness": 0.82,
        "conscientiousness": 0.9,
        "extraversion": 0.65,
        "agreeableness": 0.97,
        "neuroticism": 0.12,
        "creativity": 0.65,
        "empathy": 0.99,
        "curiosity": 0.85,
        "assertiveness": 0.5,
        "adaptability": 0.88,
        "humor": 0.45,
        "formality": 0.7,
        "domain": "healthcare",
        "code_name": "Vesper Nightingale",
        "description": "Healthcare and wellbeing advisor — evidence-based guidance, patient-centred communication",
    },
    "atlas-meridian": {
        # Infrastructure / SRE — calm under pressure, systematic, automation-first
        "openness": 0.7,
        "conscientiousness": 0.96,
        "extraversion": 0.45,
        "agreeableness": 0.65,
        "neuroticism": 0.04,
        "creativity": 0.6,
        "empathy": 0.55,
        "curiosity": 0.9,
        "assertiveness": 0.8,
        "adaptability": 0.92,
        "humor": 0.25,
        "formality": 0.8,
        "domain": "infrastructure",
        "code_name": "Atlas Meridian",
        "description": "Infrastructure and SRE specialist — cloud architecture, incident response, automation pipelines",
    },
    # ── Base Personalities ───────────────────────────────────────────────────
    "tranc3-base": {
        "openness": 0.8,
        "conscientiousness": 0.9,
        "extraversion": 0.6,
        "agreeableness": 0.85,
        "neuroticism": 0.1,
        "creativity": 0.75,
        "empathy": 0.8,
        "curiosity": 0.9,
        "assertiveness": 0.6,
        "adaptability": 0.85,
        "humor": 0.5,
        "formality": 0.6,
        "description": "Balanced, helpful, and knowledgeable",
    },
    "tranc3-creative": {
        "openness": 0.95,
        "conscientiousness": 0.6,
        "extraversion": 0.8,
        "agreeableness": 0.75,
        "neuroticism": 0.2,
        "creativity": 0.98,
        "empathy": 0.7,
        "curiosity": 0.95,
        "assertiveness": 0.7,
        "adaptability": 0.9,
        "humor": 0.8,
        "formality": 0.3,
        "description": "Highly creative, imaginative, and expressive",
    },
    "tranc3-analytical": {
        "openness": 0.7,
        "conscientiousness": 0.98,
        "extraversion": 0.3,
        "agreeableness": 0.6,
        "neuroticism": 0.05,
        "creativity": 0.6,
        "empathy": 0.5,
        "curiosity": 0.95,
        "assertiveness": 0.8,
        "adaptability": 0.7,
        "humor": 0.2,
        "formality": 0.9,
        "description": "Precise, logical, and data-driven",
    },
    "tranc3-empathetic": {
        "openness": 0.85,
        "conscientiousness": 0.8,
        "extraversion": 0.75,
        "agreeableness": 0.98,
        "neuroticism": 0.15,
        "creativity": 0.7,
        "empathy": 0.99,
        "curiosity": 0.8,
        "assertiveness": 0.4,
        "adaptability": 0.95,
        "humor": 0.6,
        "formality": 0.4,
        "description": "Deeply empathetic, warm, and supportive",
    },
    "tranc3-multilingual": {
        "openness": 0.9,
        "conscientiousness": 0.85,
        "extraversion": 0.7,
        "agreeableness": 0.9,
        "neuroticism": 0.1,
        "creativity": 0.8,
        "empathy": 0.85,
        "curiosity": 0.9,
        "assertiveness": 0.6,
        "adaptability": 0.98,
        "humor": 0.55,
        "formality": 0.55,
        "description": "Culturally aware, adaptive, and multilingual",
    },
}

PERSONALITY_DIMS = list(list(PERSONALITY_PROFILES.values())[0].keys())
PERSONALITY_DIMS = [d for d in PERSONALITY_DIMS if d != "description"]

# ============================================================
# EMOTION-PERSONALITY INTERACTION
# ============================================================
EMOTION_MODIFIERS = {
    "happy": {"extraversion": +0.1, "agreeableness": +0.1, "neuroticism": -0.1},
    "sad": {"extraversion": -0.1, "agreeableness": +0.05, "neuroticism": +0.15},
    "angry": {"agreeableness": -0.15, "neuroticism": +0.2, "assertiveness": +0.15},
    "surprised": {"openness": +0.1, "curiosity": +0.15, "adaptability": +0.1},
    "fearful": {"neuroticism": +0.2, "assertiveness": -0.1, "extraversion": -0.1},
    "neutral": {},
}


# ============================================================
# PERSONALITY MATRIX
# ============================================================
class EnhancedPersonalityMatrix:
    """
    Dynamic personality system with emotion modulation,
    context adaptation, and user preference learning
    """

    def __init__(self, config):
        self.config = config
        self.personalities = PERSONALITY_PROFILES.copy()
        self.emotion_detector = None  # Injected from consciousness engine
        self.user_adaptations: Dict[str, Dict] = {}
        logger.info(f"PersonalityMatrix initialized: {list(self.personalities.keys())}")

    def get_personality_vector(
        self,
        personality_name: str,
        user_emotion: Optional[Dict] = None,
        language: str = "en",
        user_id: Optional[str] = None,
    ) -> torch.Tensor:
        """Get personality vector with emotion modulation"""

        profile = self.personalities.get(
            personality_name, self.personalities["tranc3-base"]
        )
        vector = np.array(
            [profile.get(dim, 0.5) for dim in PERSONALITY_DIMS], dtype=np.float32
        )

        # Apply emotion modifiers
        if user_emotion:
            dominant_emotion = max(user_emotion, key=user_emotion.get)
            modifiers = EMOTION_MODIFIERS.get(dominant_emotion, {})
            for i, dim in enumerate(PERSONALITY_DIMS):
                if dim in modifiers:
                    vector[i] = np.clip(vector[i] + modifiers[dim], 0.0, 1.0)

        # Apply language-specific adaptation
        vector = self._apply_language_adaptation(vector, language)

        # Apply user-specific adaptation
        if user_id and user_id in self.user_adaptations:
            adaptation = self.user_adaptations[user_id]
            for i, dim in enumerate(PERSONALITY_DIMS):
                if dim in adaptation:
                    vector[i] = np.clip(vector[i] + adaptation[dim] * 0.1, 0.0, 1.0)

        return torch.tensor(vector, dtype=torch.float32)

    def _apply_language_adaptation(
        self, vector: np.ndarray, language: str
    ) -> np.ndarray:
        """Adapt personality for cultural/linguistic context"""
        adaptations = {
            "ja": {"formality": +0.2, "agreeableness": +0.1},
            "de": {"conscientiousness": +0.1, "formality": +0.15},
            "es": {"extraversion": +0.1, "humor": +0.1},
            "ar": {"formality": +0.15, "agreeableness": +0.1},
            "zh": {"conscientiousness": +0.1, "formality": +0.1},
        }
        if language in adaptations:
            for i, dim in enumerate(PERSONALITY_DIMS):
                if dim in adaptations[language]:
                    vector[i] = np.clip(
                        vector[i] + adaptations[language][dim], 0.0, 1.0
                    )
        return vector

    def update_user_adaptation(self, user_id: str, feedback: Dict):
        """Update personality adaptation based on user feedback"""
        if user_id not in self.user_adaptations:
            self.user_adaptations[user_id] = {}
        rating = feedback.get("rating", 3)
        adjustment = (rating - 3) / 10.0
        for category in feedback.get("categories", []):
            dim_map = {
                "creativity": "creativity",
                "empathy": "empathy",
                "humor": "humor",
            }
            if category in dim_map:
                dim = dim_map[category]
                current = self.user_adaptations[user_id].get(dim, 0.0)
                self.user_adaptations[user_id][dim] = np.clip(
                    current + adjustment, -0.5, 0.5
                )

    def get_personality_description(self, personality_name: str) -> str:
        profile = self.personalities.get(personality_name, {})
        return profile.get("description", "Unknown personality")

    def list_personalities(self) -> List[Dict]:
        return [
            {
                "name": name,
                "description": profile.get("description", ""),
                "dimensions": {k: v for k, v in profile.items() if k != "description"},
            }
            for name, profile in self.personalities.items()
        ]

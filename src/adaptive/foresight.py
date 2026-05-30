# src/adaptive/foresight.py
# TRANC3 Adaptive Foresight Engine
# Predictive, probability-aware, self-adjusting intelligence layer

import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ProbabilityVector:
    """Weighted probability distribution over outcomes"""

    outcomes: Dict[str, float]

    def normalise(self) -> "ProbabilityVector":
        total = sum(self.outcomes.values()) or 1.0
        return ProbabilityVector({k: v / total for k, v in self.outcomes.items()})

    def top(self, n: int = 3) -> List[Tuple[str, float]]:
        return sorted(self.outcomes.items(), key=lambda x: x[1], reverse=True)[:n]

    def entropy(self) -> float:
        """Shannon entropy — higher = more uncertain"""
        probs = list(self.outcomes.values())
        return -sum(p * math.log2(p + 1e-10) for p in probs if p > 0)

    def confidence(self) -> float:
        """1.0 = certain, 0.0 = maximally uncertain"""
        max_entropy = math.log2(len(self.outcomes) + 1e-10)
        return 1.0 - (self.entropy() / max_entropy) if max_entropy > 0 else 1.0


class ConversationTrajectoryPredictor:
    """
    Predict where a conversation is heading.
    Enables proactive response preparation.
    """

    TRAJECTORIES = {
        "escalating_positive": "User satisfaction increasing — maintain current approach",
        "escalating_negative": "User frustration building — switch to empathetic mode",
        "topic_drift": "Conversation moving off original topic",
        "resolution_imminent": "User about to reach their goal",
        "abandonment_risk": "User likely to end conversation without resolution",
        "deepening_engagement": "User becoming more invested — opportunity to upsell",
        "stable": "Conversation proceeding normally",
    }

    def __init__(self):
        self._history: Dict[str, deque] = {}

    def record_turn(
        self, session_id: str, emotion: str, intent: str, rating: Optional[float] = None
    ):
        if session_id not in self._history:
            self._history[session_id] = deque(maxlen=20)
        self._history[session_id].append(
            {
                "emotion": emotion,
                "intent": intent,
                "rating": rating,
                "ts": time.time(),
            }
        )

    def predict_trajectory(self, session_id: str) -> ProbabilityVector:
        history = list(self._history.get(session_id, []))
        if len(history) < 2:
            return ProbabilityVector({"stable": 1.0}).normalise()

        scores = dict.fromkeys(self.TRAJECTORIES, 0.0)

        # Emotion trend
        emotions = [h["emotion"] for h in history]
        negative = {"angry", "sad", "fearful", "disgusted"}
        positive = {"happy", "surprised"}

        recent_neg = sum(1 for e in emotions[-3:] if e in negative)
        recent_pos = sum(1 for e in emotions[-3:] if e in positive)

        if recent_neg >= 2:
            scores["escalating_negative"] += 0.6
            scores["abandonment_risk"] += 0.3
        if recent_pos >= 2:
            scores["escalating_positive"] += 0.5
            scores["deepening_engagement"] += 0.3

        # Intent consistency
        intents = [h["intent"] for h in history[-4:]]
        if len(set(intents)) > 3:
            scores["topic_drift"] += 0.5

        # Resolution signals
        if "praise" in intents[-2:]:
            scores["resolution_imminent"] += 0.6

        scores["stable"] += 0.2  # baseline

        return ProbabilityVector(scores).normalise()

    def get_recommendation(self, trajectory: ProbabilityVector) -> str:
        top_traj, _ = trajectory.top(1)[0]
        return self.TRAJECTORIES.get(top_traj, "Maintain current approach")


class AdaptiveParameterController:
    """
    Dynamically adjust generation parameters based on context.
    Temperature, top_p, max_tokens adapt in real time.
    """

    BASE_PARAMS = {
        "temperature": 0.8,
        "top_p": 0.9,
        "max_tokens": 150,
        "repetition_penalty": 1.1,
    }

    def compute(
        self,
        intent: str,
        emotion: str,
        phi: float = 0.0,
        churn_risk: float = 0.0,
        conversation_length: int = 0,
    ) -> Dict[str, float]:
        params = self.BASE_PARAMS.copy()

        # Intent-based adjustments
        intent_adjustments = {
            "creative": {"temperature": +0.2, "top_p": +0.05, "max_tokens": +100},
            "analytical": {"temperature": -0.3, "top_p": -0.1, "max_tokens": +50},
            "emotional": {"temperature": +0.1, "max_tokens": +50},
            "question": {"temperature": -0.1, "max_tokens": -20},
        }
        for k, v in intent_adjustments.get(intent, {}).items():
            params[k] = params.get(k, 0) + v

        # Emotion-based adjustments
        if emotion in {"angry", "sad"}:
            params["temperature"] = max(0.5, params["temperature"] - 0.1)
            params["max_tokens"] = min(200, params["max_tokens"] + 30)

        # Consciousness boost — higher phi = more creative
        if phi > 2.0:
            params["temperature"] = min(1.2, params["temperature"] + phi * 0.05)

        # Churn risk — be more helpful/verbose for at-risk users
        if churn_risk > 0.6:
            params["max_tokens"] = min(300, params["max_tokens"] + 50)
            params["temperature"] = max(0.6, params["temperature"] - 0.05)

        # Conversation fatigue — shorter responses in long conversations
        if conversation_length > 20:
            params["max_tokens"] = max(50, params["max_tokens"] - 30)

        # Clamp
        params["temperature"] = round(max(0.1, min(1.5, params["temperature"])), 3)
        params["top_p"] = round(max(0.5, min(1.0, params["top_p"])), 3)
        params["max_tokens"] = int(max(30, min(500, params["max_tokens"])))

        return params


class ForesightEngine:
    """
    Top-level foresight and adaptive intelligence orchestrator.
    Combines trajectory prediction, parameter adaptation, and probability reasoning.
    """

    def __init__(self):
        self.trajectory = ConversationTrajectoryPredictor()
        self.params = AdaptiveParameterController()
        logger.info("ForesightEngine initialised")

    def analyse(
        self,
        session_id: str,
        user_message: str,
        emotion: str,
        intent: str,
        phi: float = 0.0,
        churn_risk: float = 0.0,
        conversation_length: int = 0,
    ) -> Dict:
        # Record this turn
        self.trajectory.record_turn(session_id, emotion, intent)

        # Predict trajectory
        traj = self.trajectory.predict_trajectory(session_id)
        recommendation = self.trajectory.get_recommendation(traj)

        # Compute adaptive parameters
        gen_params = self.params.compute(
            intent=intent,
            emotion=emotion,
            phi=phi,
            churn_risk=churn_risk,
            conversation_length=conversation_length,
        )

        return {
            "trajectory": traj.top(3),
            "trajectory_confidence": round(traj.confidence(), 4),
            "recommendation": recommendation,
            "generation_params": gen_params,
            "foresight": {
                "predicted_next_intent": intent,  # Extend with ML model
                "engagement_risk": churn_risk > 0.6,
                "consciousness_active": phi > 2.0,
            },
        }


# Singleton
foresight = ForesightEngine()

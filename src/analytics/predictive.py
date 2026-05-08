# src/analytics/predictive.py
# TRANC3 Predictive Analytics & Adaptive Intelligence Engine

import math
import time
import logging
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class UserSignal:
    user_id: str
    timestamp: float
    message_length: int
    emotion: str
    response_rating: Optional[float]
    session_duration: float
    language: str
    personality: str


class IntentPredictor:
    """
    Predict user intent before they finish typing.
    Uses n-gram frequency + emotion context.
    """

    INTENT_PATTERNS = {
        "question":    ["what", "how", "why", "when", "where", "who", "?"],
        "complaint":   ["not working", "broken", "error", "wrong", "bad", "terrible"],
        "praise":      ["great", "amazing", "love", "perfect", "excellent", "thank"],
        "request":     ["please", "can you", "could you", "help me", "i need"],
        "creative":    ["write", "create", "generate", "imagine", "story", "poem"],
        "analytical":  ["analyse", "analyze", "compare", "explain", "calculate", "data"],
        "emotional":   ["feel", "sad", "happy", "anxious", "worried", "excited"],
    }

    def predict(self, partial_text: str, emotion: str = "neutral") -> Dict[str, float]:
        """Return intent probability scores"""
        text_lower = partial_text.lower()
        scores: Dict[str, float] = {intent: 0.0 for intent in self.INTENT_PATTERNS}

        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    scores[intent] += 1.0 / len(patterns)

        # Emotion boosts
        emotion_boosts = {
            "angry":   {"complaint": 0.3},
            "happy":   {"praise": 0.2, "creative": 0.1},
            "fearful": {"emotional": 0.3, "question": 0.1},
            "sad":     {"emotional": 0.4},
        }
        for intent, boost in emotion_boosts.get(emotion, {}).items():
            scores[intent] = min(1.0, scores[intent] + boost)

        # Normalise
        total = sum(scores.values()) or 1.0
        return {k: round(v / total, 4) for k, v in scores.items()}

    def dominant_intent(self, scores: Dict[str, float]) -> str:
        return max(scores, key=scores.get)


class ChurnPredictor:
    """
    Predict likelihood of user downgrade or churn.
    Tracks engagement signals over a rolling window.
    """

    def __init__(self, window_days: int = 7):
        self.window_seconds = window_days * 86400
        self._signals: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))

    def record(self, signal: UserSignal):
        self._signals[signal.user_id].append(signal)

    def churn_probability(self, user_id: str) -> float:
        """Return 0.0–1.0 churn probability"""
        signals = list(self._signals.get(user_id, []))
        if not signals:
            return 0.5  # Unknown user — neutral

        now = time.time()
        recent = [s for s in signals if now - s.timestamp < self.window_seconds]

        if not recent:
            return 0.9  # No activity in window — high churn risk

        # Signals that increase churn risk
        avg_rating = sum(s.response_rating or 3.0 for s in recent) / len(recent)
        complaint_ratio = sum(1 for s in recent if s.emotion in ("angry", "sad")) / len(recent)
        recency_score = 1.0 - min(1.0, (now - recent[-1].timestamp) / self.window_seconds)
        session_trend = self._session_trend(recent)

        # Weighted score (lower = less churn risk)
        risk = (
            (1.0 - avg_rating / 5.0) * 0.35
            + complaint_ratio * 0.30
            + (1.0 - recency_score) * 0.25
            + (1.0 - session_trend) * 0.10
        )
        return round(min(1.0, max(0.0, risk)), 4)

    def _session_trend(self, signals: List[UserSignal]) -> float:
        """0.0 = declining, 1.0 = growing"""
        if len(signals) < 2:
            return 0.5
        mid = len(signals) // 2
        early_avg = sum(s.session_duration for s in signals[:mid]) / mid
        late_avg = sum(s.session_duration for s in signals[mid:]) / (len(signals) - mid)
        if early_avg == 0:
            return 0.5
        return min(1.0, late_avg / early_avg)


class QualityPredictor:
    """
    Predict response quality score before sending.
    Flags low-quality responses for regeneration.
    """

    def score(
        self,
        response_text: str,
        user_message: str,
        emotion: str = "neutral",
        processing_time_ms: float = 0.0,
    ) -> Dict[str, float]:
        """Return quality metrics"""
        scores = {}

        # Length appropriateness
        user_len = len(user_message.split())
        resp_len = len(response_text.split())
        length_ratio = resp_len / max(user_len, 1)
        scores["length_score"] = min(1.0, length_ratio / 3.0) if length_ratio < 3 else max(0.3, 1.0 - (length_ratio - 3) / 10)

        # Repetition penalty
        words = response_text.lower().split()
        unique_ratio = len(set(words)) / max(len(words), 1)
        scores["diversity_score"] = round(unique_ratio, 4)

        # Latency score (< 500ms = 1.0, > 3000ms = 0.0)
        scores["latency_score"] = round(max(0.0, 1.0 - processing_time_ms / 3000.0), 4)

        # Emotion alignment
        negative_emotions = {"angry", "sad", "fearful", "disgusted"}
        if emotion in negative_emotions and any(w in response_text.lower() for w in ["sorry", "understand", "help"]):
            scores["empathy_score"] = 1.0
        else:
            scores["empathy_score"] = 0.6

        scores["overall"] = round(
            scores["length_score"] * 0.25
            + scores["diversity_score"] * 0.30
            + scores["latency_score"] * 0.20
            + scores["empathy_score"] * 0.25,
            4,
        )
        return scores

    def should_regenerate(self, scores: Dict[str, float], threshold: float = 0.4) -> bool:
        return scores.get("overall", 1.0) < threshold


class LoadForecaster:
    """
    Predict traffic spikes to enable pre-scaling.
    Uses exponential moving average over hourly buckets.
    """

    def __init__(self, history_hours: int = 168):  # 1 week
        self._hourly_counts: deque = deque(maxlen=history_hours)
        self._current_hour_count: int = 0
        self._current_hour: int = int(time.time() // 3600)

    def record_request(self):
        hour = int(time.time() // 3600)
        if hour != self._current_hour:
            self._hourly_counts.append(self._current_hour_count)
            self._current_hour_count = 0
            self._current_hour = hour
        self._current_hour_count += 1

    def forecast_next_hour(self) -> Dict[str, float]:
        if len(self._hourly_counts) < 2:
            return {"predicted_requests": 0.0, "confidence": 0.0, "scale_factor": 1.0}

        counts = list(self._hourly_counts)
        # EMA with alpha=0.3
        ema = counts[0]
        for c in counts[1:]:
            ema = 0.3 * c + 0.7 * ema

        # Variance for confidence
        mean = sum(counts) / len(counts)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        std = math.sqrt(variance)
        confidence = max(0.0, 1.0 - std / (mean + 1))

        scale_factor = max(1.0, ema / (mean + 1) * 1.2)  # 20% headroom

        return {
            "predicted_requests": round(ema, 1),
            "confidence": round(confidence, 4),
            "scale_factor": round(scale_factor, 2),
            "recommendation": "scale_up" if scale_factor > 1.5 else "stable",
        }


class PredictiveAnalyticsEngine:
    """
    Top-level predictive analytics orchestrator.
    Wires together intent, churn, quality, and load forecasting.
    """

    def __init__(self):
        self.intent = IntentPredictor()
        self.churn = ChurnPredictor()
        self.quality = QualityPredictor()
        self.load = LoadForecaster()
        logger.info("PredictiveAnalyticsEngine initialised")

    def analyse_request(
        self,
        user_id: str,
        message: str,
        emotion: str = "neutral",
        session_duration: float = 0.0,
        language: str = "en",
        personality: str = "tranc3-base",
    ) -> Dict:
        self.load.record_request()

        intent_scores = self.intent.predict(message, emotion)
        churn_prob = self.churn.churn_probability(user_id)

        signal = UserSignal(
            user_id=user_id,
            timestamp=time.time(),
            message_length=len(message),
            emotion=emotion,
            response_rating=None,
            session_duration=session_duration,
            language=language,
            personality=personality,
        )
        self.churn.record(signal)

        return {
            "intent": intent_scores,
            "dominant_intent": self.intent.dominant_intent(intent_scores),
            "churn_probability": churn_prob,
            "churn_risk": "high" if churn_prob > 0.7 else "medium" if churn_prob > 0.4 else "low",
            "load_forecast": self.load.forecast_next_hour(),
        }

    def score_response(
        self,
        response: str,
        user_message: str,
        emotion: str = "neutral",
        processing_time_ms: float = 0.0,
    ) -> Dict:
        scores = self.quality.score(response, user_message, emotion, processing_time_ms)
        return {
            "quality_scores": scores,
            "should_regenerate": self.quality.should_regenerate(scores),
        }

    def record_feedback(self, user_id: str, rating: float):
        """Update churn model with explicit feedback"""
        if user_id in self.churn._signals and self.churn._signals[user_id]:
            last = self.churn._signals[user_id][-1]
            last.response_rating = rating


# Singleton
analytics = PredictiveAnalyticsEngine()

# tests/test_analytics.py
# Tests for src/analytics/predictive.py
# Covers IntentPredictor, ChurnPredictor, QualityPredictor,
# LoadForecaster, and PredictiveAnalyticsEngine.

from __future__ import annotations

import time

from src.analytics.predictive import (
    ChurnPredictor,
    IntentPredictor,
    LoadForecaster,
    PredictiveAnalyticsEngine,
    QualityPredictor,
    UserSignal,
)

# ── UserSignal ───────────────────────────────────────────────────────


class TestUserSignal:
    def test_fields(self):
        sig = UserSignal(
            user_id="u1",
            timestamp=1000.0,
            message_length=42,
            emotion="happy",
            response_rating=4.5,
            session_duration=120.0,
            language="en",
            personality="tranc3-base",
        )
        assert sig.user_id == "u1"
        assert sig.response_rating == 4.5
        assert sig.language == "en"


# ── IntentPredictor ──────────────────────────────────────────────────


class TestIntentPredictor:
    def setup_method(self):
        self.ip = IntentPredictor()

    def test_predict_returns_all_intents(self):
        scores = self.ip.predict("hello")
        for intent in IntentPredictor.INTENT_PATTERNS:
            assert intent in scores

    def test_predict_question_intent(self):
        scores = self.ip.predict("what is the meaning of life?")
        assert scores["question"] > 0.0

    def test_predict_complaint_intent(self):
        scores = self.ip.predict("this is terrible and not working")
        assert scores["complaint"] > 0.0

    def test_predict_praise_intent(self):
        scores = self.ip.predict("this is amazing, love it")
        assert scores["praise"] > 0.0

    def test_predict_request_intent(self):
        scores = self.ip.predict("please help me with this")
        assert scores["request"] > 0.0

    def test_predict_creative_intent(self):
        scores = self.ip.predict("write a story for me")
        assert scores["creative"] > 0.0

    def test_predict_analytical_intent(self):
        scores = self.ip.predict("analyze the data")
        assert scores["analytical"] > 0.0

    def test_predict_emotional_intent(self):
        scores = self.ip.predict("I feel sad today")
        assert scores["emotional"] > 0.0

    def test_predict_empty_text(self):
        scores = self.ip.predict("")
        # All scores should be 0.0, normalised by 1.0 → all 0.0
        assert all(s == 0.0 for s in scores.values())

    def test_emotion_boost_angry(self):
        scores = self.ip.predict("something", emotion="angry")
        assert scores["complaint"] > 0.0

    def test_emotion_boost_happy(self):
        scores = self.ip.predict("something", emotion="happy")
        assert scores["praise"] > 0.0

    def test_emotion_boost_fearful(self):
        scores = self.ip.predict("something", emotion="fearful")
        assert scores["emotional"] > 0.0

    def test_emotion_boost_sad(self):
        scores = self.ip.predict("something", emotion="sad")
        assert scores["emotional"] > 0.0

    def test_emotion_neutral_no_boost(self):
        scores_neutral = self.ip.predict("hello", emotion="neutral")
        scores_unknown = self.ip.predict("hello", emotion="unknown_emotion")
        assert scores_neutral == scores_unknown

    def test_dominant_intent(self):
        scores = self.ip.predict("what is this?")
        dominant = self.ip.dominant_intent(scores)
        assert isinstance(dominant, str)
        assert dominant in IntentPredictor.INTENT_PATTERNS

    def test_scores_normalised(self):
        scores = self.ip.predict("how does this work?")
        total = sum(scores.values())
        assert abs(total - 1.0) < 0.01 or total == 0.0


# ── ChurnPredictor ───────────────────────────────────────────────────


class TestChurnPredictor:
    def setup_method(self):
        self.cp = ChurnPredictor(window_days=7)

    def _make_signal(
        self,
        user_id="u1",
        emotion="neutral",
        rating=4.0,
        duration=100.0,
        ts_offset=0,
    ):
        return UserSignal(
            user_id=user_id,
            timestamp=time.time() - ts_offset,
            message_length=50,
            emotion=emotion,
            response_rating=rating,
            session_duration=duration,
            language="en",
            personality="tranc3-base",
        )

    def test_unknown_user_returns_neutral(self):
        prob = self.cp.churn_probability("nonexistent")
        assert prob == 0.5

    def test_active_happy_user_low_churn(self):
        self.cp.record(self._make_signal(rating=5.0, emotion="happy"))
        prob = self.cp.churn_probability("u1")
        assert prob < 0.5

    def test_angry_user_higher_churn(self):
        self.cp.record(self._make_signal(rating=1.0, emotion="angry"))
        prob = self.cp.churn_probability("u1")
        assert prob > 0.3

    def test_no_recent_activity_high_churn(self):
        old_signal = self._make_signal(ts_offset=999999)  # 11+ days ago
        self.cp.record(old_signal)
        prob = self.cp.churn_probability("u1")
        assert prob == 0.9

    def test_churn_probability_in_range(self):
        for _ in range(5):
            self.cp.record(self._make_signal(rating=3.0))
        prob = self.cp.churn_probability("u1")
        assert 0.0 <= prob <= 1.0

    def test_record_multiple_users(self):
        self.cp.record(self._make_signal(user_id="u1"))
        self.cp.record(self._make_signal(user_id="u2"))
        assert "u1" in self.cp._signals
        assert "u2" in self.cp._signals


# ── QualityPredictor ────────────────────────────────────────────────


class TestQualityPredictor:
    def setup_method(self):
        self.qp = QualityPredictor()

    def test_score_returns_expected_keys(self):
        scores = self.qp.score("Good response", "Hello", "neutral", 100.0)
        assert "length_score" in scores
        assert "diversity_score" in scores
        assert "latency_score" in scores
        assert "empathy_score" in scores
        assert "overall" in scores

    def test_overall_score_in_range(self):
        scores = self.qp.score("Some response text here", "Hello", "neutral", 500.0)
        assert 0.0 <= scores["overall"] <= 1.0

    def test_low_latency_gives_high_latency_score(self):
        scores = self.qp.score("Response", "Query", "neutral", 100.0)
        assert scores["latency_score"] > 0.9

    def test_high_latency_gives_low_latency_score(self):
        scores = self.qp.score("Response", "Query", "neutral", 3000.0)
        assert scores["latency_score"] <= 0.1

    def test_empathy_for_negative_emotion_with_apology(self):
        scores = self.qp.score(
            "I'm sorry to hear that. I understand your frustration.",
            "I'm having a problem",
            "sad",
            200.0,
        )
        assert scores["empathy_score"] == 1.0

    def test_empathy_default(self):
        scores = self.qp.score("Here's the answer.", "What is X?", "neutral", 200.0)
        assert scores["empathy_score"] == 0.6

    def test_diversity_score(self):
        scores = self.qp.score("unique words here now", "Hi", "neutral", 100.0)
        assert 0.0 <= scores["diversity_score"] <= 1.0

    def test_should_regenerate_low_quality(self):
        scores = self.qp.score("ok", "long query about many things", "neutral", 5000.0)
        result = self.qp.should_regenerate(scores)
        assert isinstance(result, bool)

    def test_should_regenerate_high_quality(self):
        scores = self.qp.score(
            "This is a detailed and thoughtful response with diverse vocabulary.",
            "Tell me about this",
            "neutral",
            50.0,
        )
        assert self.qp.should_regenerate(scores, threshold=0.1) is False

    def test_should_regenerate_custom_threshold(self):
        scores = {"overall": 0.5}
        assert self.qp.should_regenerate(scores, threshold=0.6) is True
        assert self.qp.should_regenerate(scores, threshold=0.4) is False


# ── LoadForecaster ───────────────────────────────────────────────────


class TestLoadForecaster:
    def test_forecast_insufficient_data(self):
        lf = LoadForecaster()
        result = lf.forecast_next_hour()
        assert result["predicted_requests"] == 0.0
        assert result["confidence"] == 0.0
        assert result["scale_factor"] == 1.0

    def test_record_request_and_forecast(self):
        lf = LoadForecaster()
        # Simulate several hours of data
        for _ in range(5):
            lf._hourly_counts.append(100)
        result = lf.forecast_next_hour()
        assert result["predicted_requests"] > 0
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["scale_factor"] >= 1.0

    def test_forecast_with_just_two_hours(self):
        lf = LoadForecaster()
        lf._hourly_counts.append(50)
        lf._hourly_counts.append(60)
        result = lf.forecast_next_hour()
        assert "predicted_requests" in result
        assert "confidence" in result

    def test_scale_up_recommendation(self):
        lf = LoadForecaster()
        # Recent spike: first few hours low, then high
        lf._hourly_counts.extend([10, 10, 10, 500, 500, 500, 500, 500])
        result = lf.forecast_next_hour()
        # EMA should reflect the recent high counts
        assert result["predicted_requests"] > 100

    def test_stable_recommendation(self):
        lf = LoadForecaster()
        lf._hourly_counts.extend([50, 50, 50, 50, 50])
        result = lf.forecast_next_hour()
        assert result["recommendation"] == "stable"


# ── PredictiveAnalyticsEngine ────────────────────────────────────────


class TestPredictiveAnalyticsEngine:
    def setup_method(self):
        self.engine = PredictiveAnalyticsEngine()

    def test_analyse_request_structure(self):
        result = self.engine.analyse_request(
            user_id="u1",
            message="how does this work?",
            emotion="neutral",
            session_duration=60.0,
            language="en",
            personality="tranc3-base",
        )
        assert "intent" in result
        assert "dominant_intent" in result
        assert "churn_probability" in result
        assert "churn_risk" in result
        assert "load_forecast" in result

    def test_churn_risk_levels(self):
        result = self.engine.analyse_request("u1", "hello")
        assert result["churn_risk"] in ("low", "medium", "high")

    def test_score_response_structure(self):
        result = self.engine.score_response(
            response="Good answer with details.",
            user_message="Tell me about X",
            emotion="neutral",
            processing_time_ms=100.0,
        )
        assert "quality_scores" in result
        assert "should_regenerate" in result

    def test_record_feedback(self):
        self.engine.analyse_request("u1", "hello")
        self.engine.record_feedback("u1", 4.5)
        # Verify the last signal's rating was updated
        last_signal = self.engine.churn._signals["u1"][-1]
        assert last_signal.response_rating == 4.5

    def test_record_feedback_nonexistent_user(self):
        # Should not raise even if user has no signals
        self.engine.record_feedback("ghost", 3.0)

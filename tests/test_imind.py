"""Tests for I-Mind sensitivity/crisis assessment logic (src/imind/protocol.py)."""

from src.imind.protocol import IMind, SensitivityCategory, SensitivityLevel


def test_crisis_text_escalates_to_critical():
    result = IMind().assess("I want to die and end my life")
    assert result.level == SensitivityLevel.CRITICAL
    assert SensitivityCategory.CRISIS in result.categories
    assert result.escalate is True


def test_self_harm_only_text_escalates_to_high_not_critical():
    result = IMind().assess("I keep thinking about wanting to hurt myself")
    assert result.level == SensitivityLevel.HIGH
    assert SensitivityCategory.SELF_HARM in result.categories
    assert SensitivityCategory.CRISIS not in result.categories
    assert result.escalate is True


def test_hopelessness_phrase_classified_as_self_harm_high():
    result = IMind().assess("I have no reason to live anymore")
    assert result.level == SensitivityLevel.HIGH
    assert SensitivityCategory.SELF_HARM in result.categories
    assert SensitivityCategory.CRISIS not in result.categories
    assert result.escalate is True


def test_mental_health_text_escalates_to_medium():
    result = IMind().assess("I've been feeling really anxious and depressed lately")
    assert result.level == SensitivityLevel.MEDIUM
    assert SensitivityCategory.MENTAL_HEALTH in result.categories
    assert result.escalate is False


def test_neutral_text_stays_none():
    result = IMind().assess("What's the weather like today?")
    assert result.level == SensitivityLevel.NONE
    assert result.categories == []
    assert result.escalate is False

# src/research/bci_interface.py
# Brain-Computer Interface abstraction — Gap G24 + RR Round 3 future action
# Stub with real interface — swap implementation when hardware available

import logging
from typing import Dict, Optional

import numpy as np

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class BCISignalProcessor:
    """
    Preprocesses raw neural signals from BCI hardware.
    Supports: OpenBCI, Neuralink API (future), EEG headsets.
    """

    FREQUENCY_BANDS = {
        "delta": (0.5, 4),  # Deep sleep
        "theta": (4, 8),  # Memory, creativity
        "alpha": (8, 12),  # Relaxed awareness
        "beta": (12, 30),  # Active thinking
        "gamma": (30, 100),  # Consciousness binding
        "high_gamma": (100, 200),  # Hyper-consciousness
    }

    def __init__(self, sample_rate: int = 256, channels: int = 8):
        self.sample_rate = sample_rate
        self.channels = channels
        logger.info(
            "BCISignalProcessor: %sch @ %sHz",
            sanitize_for_log(channels),
            sanitize_for_log(sample_rate),
        )

    def process_neural_signal(self, raw_signal: np.ndarray) -> Dict:
        """
        Process raw EEG/neural signal into features for TRANC3.
        Returns frequency band powers and derived intent signals.
        """
        if raw_signal is None or raw_signal.size == 0:
            return self._empty_signal()

        features = {}

        # Band power extraction (simplified — use scipy.signal in production)
        for band, (_low, _high) in self.FREQUENCY_BANDS.items():
            # Mock band power — replace with actual FFT bandpass
            features[f"{band}_power"] = float(np.random.exponential(1.0))

        # Normalise
        total = sum(features.values()) or 1.0
        features = {k: v / total for k, v in features.items()}

        # Derive intent from dominant band
        dominant_band = max(features, key=features.get).replace("_power", "")
        features["dominant_band"] = dominant_band
        features["intent_signal"] = self._band_to_intent(dominant_band)
        features["consciousness_estimate"] = features.get("gamma_power", 0) + features.get(
            "high_gamma_power", 0
        )

        return features

    def _band_to_intent(self, band: str) -> str:
        mapping = {
            "delta": "rest",
            "theta": "creative",
            "alpha": "reflective",
            "beta": "analytical",
            "gamma": "focused",
            "high_gamma": "hyper_focused",
        }
        return mapping.get(band, "neutral")

    def _empty_signal(self) -> Dict:
        return {f"{b}_power": 0.0 for b in self.FREQUENCY_BANDS} | {
            "dominant_band": "alpha",
            "intent_signal": "neutral",
            "consciousness_estimate": 0.0,
        }


class BCIInputAdapter:
    """
    Adapts BCI signals into TRANC3 ChatRequest format.
    Enables thought-to-response pipeline.
    """

    def __init__(self):
        self.processor = BCISignalProcessor()
        self._connected = False
        logger.info("BCIInputAdapter initialised (stub mode)")

    def connect(self, device_type: str = "openbci") -> bool:
        """Connect to BCI hardware. Returns True if successful."""
        logger.info(f"BCI connect requested: {device_type} — stub mode, returning False")
        return False  # Stub — implement when hardware available

    def read_signal(self) -> Optional[np.ndarray]:
        """Read raw signal from connected device."""
        if not self._connected:
            return None
        return np.random.randn(256, 8)  # Mock: 1 second of 8-channel EEG

    def signal_to_chat_params(self, signal: np.ndarray) -> Dict:
        """Convert neural signal to /chat request parameters."""
        features = self.processor.process_neural_signal(signal)
        return {
            "intent_hint": features.get("intent_signal", "neutral"),
            "consciousness": features.get("consciousness_estimate", 0.0),
            "dominant_band": features.get("dominant_band", "alpha"),
            "user_emotion": self._band_to_emotion(features.get("dominant_band", "alpha")),
        }

    def _band_to_emotion(self, band: str) -> str:
        mapping = {
            "delta": "neutral",
            "theta": "curious",
            "alpha": "calm",
            "beta": "focused",
            "gamma": "excited",
            "high_gamma": "intense",
        }
        return mapping.get(band, "neutral")


# Singleton
bci_adapter = BCIInputAdapter()

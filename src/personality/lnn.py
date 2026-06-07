"""
TR3-008: Liquid Neural Network (LNN) personality shaper.

Integrates ncps.torch.CfC (Closed-form Continuous-time) networks to model
continuous-time hidden state for personality entity context.

Architecture when ncps + torch available
-----------------------------------------
  input_dim : 4  [sentiment_score, domain_signal, turn_depth_norm, length_norm]
  CfC units : 64  (liquid time-constant neurons)
  output_dim: 3  [temperature_delta, top_p_delta, tone_weight]

The LNN maintains a continuous-time hidden state (h_t) across conversation
turns. Δt is the wall-clock elapsed time between turns — CfC integrates it
natively, so character drift over long pauses is physically grounded.

Outputs (all bounded [-1, +1] via tanh):
  temperature_delta  — added to the personality's base temperature
  top_p_delta        — added to base top_p
  tone_weight        — softly shifts tone from base toward "reflective" end

Fallback (no torch / ncps)
--------------------------
Exponential moving average state tracker that provides the same interface
and similar qualitative behaviour without any neural computation.
"""

from __future__ import annotations

import logging
import math
import time
from typing import List, NamedTuple, Optional

logger = logging.getLogger(__name__)

# ── optional torch / ncps ─────────────────────────────────────────────────────

try:
    import torch

    from ncps.torch import CfC  # type: ignore[import]
    from ncps.wirings import AutoNCP  # type: ignore[import]

    _USING_LNN = True
    logger.debug("personality.lnn: ncps.torch.CfC available — using LNN shaper")
except ImportError:
    _USING_LNN = False
    logger.debug("personality.lnn: ncps/torch not available — using EMA shaper")

# ── constants ─────────────────────────────────────────────────────────────────

INPUT_DIM = 4  # [sentiment, domain_signal, turn_depth_norm, length_norm]
HIDDEN_UNITS = 64
OUTPUT_DIM = 3  # [temperature_delta, top_p_delta, tone_weight]
MAX_DT = 3600.0  # cap Δt to 1 hour to avoid CfC instability on very long gaps
EMA_ALPHA = 0.15  # smoothing factor for the fallback EMA tracker


# ── public types ─────────────────────────────────────────────────────────────


class LNNInput(NamedTuple):
    """Feature vector extracted from one conversation turn."""

    sentiment: float  # -1 (negative) … +1 (positive)
    domain_signal: float  # 0 (off-topic) … 1 (on-domain)
    turn_depth_norm: float  # turn_index / max_turns, clipped to [0, 1]
    length_norm: float  # token_count / 512, clipped to [0, 1]


class LNNOutput(NamedTuple):
    """Parameter nudges produced by the LNN for this turn."""

    temperature_delta: float
    top_p_delta: float
    tone_weight: float


# ── LNN shaper (CfC path) ─────────────────────────────────────────────────────


class _CfCShaper:
    """CfC-backed personality shaper."""

    def __init__(self) -> None:
        wiring = AutoNCP(HIDDEN_UNITS, OUTPUT_DIM)
        self._model = CfC(INPUT_DIM, wiring, batch_first=True)
        self._model.eval()
        self._h: "Optional[torch.Tensor]" = None
        self._last_ts: float = time.monotonic()

    def reset(self) -> None:
        self._h = None
        self._last_ts = time.monotonic()

    def step(self, inp: LNNInput) -> LNNOutput:
        now = time.monotonic()
        dt = min(now - self._last_ts, MAX_DT)
        self._last_ts = now

        x = torch.tensor([[list(inp)]], dtype=torch.float32)  # (1, 1, INPUT_DIM)
        ts = torch.tensor([[[dt]]], dtype=torch.float32)  # (1, 1, 1)

        with torch.no_grad():
            out, self._h = self._model(x, self._h, timespans=ts)

        raw: List[float] = out[0, 0].tolist()
        return LNNOutput(
            temperature_delta=float(math.tanh(raw[0])) * 0.3,
            top_p_delta=float(math.tanh(raw[1])) * 0.1,
            tone_weight=float(math.tanh(raw[2])),
        )


# ── EMA shaper (fallback path) ────────────────────────────────────────────────


class _EMAShaper:
    """Exponential moving average fallback shaper (no torch required)."""

    def __init__(self) -> None:
        self._state: List[float] = [0.0] * OUTPUT_DIM
        self._last_ts: float = time.monotonic()

    def reset(self) -> None:
        self._state = [0.0] * OUTPUT_DIM
        self._last_ts = time.monotonic()

    def step(self, inp: LNNInput) -> LNNOutput:
        now = time.monotonic()
        dt = min(now - self._last_ts, MAX_DT)
        self._last_ts = now

        # Decay factor: longer pauses → faster decay toward 0
        decay = math.exp(-EMA_ALPHA * (dt / 30.0 + 1.0))

        # Derive target values from the input features
        target_temp = (inp.sentiment * 0.2 + inp.domain_signal * 0.1) * 0.3
        target_top_p = inp.turn_depth_norm * 0.05
        target_tone = inp.sentiment * 0.5 + inp.domain_signal * 0.5

        targets = [target_temp, target_top_p, target_tone]
        self._state = [
            decay * s + (1 - decay) * t for s, t in zip(self._state, targets, strict=False)
        ]

        return LNNOutput(
            temperature_delta=float(math.tanh(self._state[0])) * 0.3,
            top_p_delta=float(math.tanh(self._state[1])) * 0.1,
            tone_weight=float(math.tanh(self._state[2])),
        )


# ── public API ────────────────────────────────────────────────────────────────


class PersonalityLNN:
    """
    Conversation-level LNN state tracker for one personality entity.

    Usage::

        lnn = PersonalityLNN()
        for turn in conversation:
            inp = LNNInput(sentiment=..., domain_signal=..., ...)
            nudge = lnn.step(inp)
            # apply nudge.temperature_delta etc. to generation parameters
        lnn.reset()  # clear state between sessions

    The shaper transparently uses CfC if ncps+torch are available,
    otherwise falls back to an EMA tracker.
    """

    def __init__(self, *, force_fallback: bool = False) -> None:
        self._using_lnn = _USING_LNN and not force_fallback
        if self._using_lnn:
            self._shaper: "_CfCShaper | _EMAShaper" = _CfCShaper()
        else:
            self._shaper = _EMAShaper()

    @property
    def backend(self) -> str:
        return "cfc" if self._using_lnn else "ema"

    def step(self, inp: LNNInput) -> LNNOutput:
        """Advance hidden state by one turn and return parameter nudges."""
        return self._shaper.step(inp)

    def reset(self) -> None:
        """Reset hidden state (call between independent sessions)."""
        self._shaper.reset()

    def apply_to_profile(
        self,
        inp: LNNInput,
        temperature: float,
        top_p: float,
    ) -> tuple[float, float]:
        """
        Convenience: step the LNN and return adjusted (temperature, top_p).

        Clamps outputs to safe generation parameter ranges.
        """
        nudge = self.step(inp)
        new_temp = max(0.1, min(2.0, temperature + nudge.temperature_delta))
        new_top_p = max(0.05, min(1.0, top_p + nudge.top_p_delta))
        return new_temp, new_top_p

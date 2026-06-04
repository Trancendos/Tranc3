# src/bio_neural/consciousness_engine.py
# TRANC3 Full Consciousness Engine (IIT-based)
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import numpy as np

try:
    import torch
    import torch.nn as nn
except (ImportError, RuntimeError, OSError):  # pragma: no cover
    # RuntimeError: CUDA init / driver mismatch; OSError: missing shared lib
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
else:
    _TORCH_AVAILABLE = True

from Dimensional.sanitize import sanitize_for_log

try:
    from scipy.stats import entropy as _scipy_entropy

    def entropy(pk, **kw):
        return float(_scipy_entropy(pk, **kw))
except ImportError:
    import math

    def entropy(pk, **kw):  # type: ignore[misc]
        vals = [p for p in pk if p > 0]
        total = sum(vals)
        return -sum((p / total) * math.log(p / total) for p in vals) if total else 0.0


logger = logging.getLogger(__name__)


# ============================================================
# INTEGRATED INFORMATION THEORY (IIT) CALCULATOR
# ============================================================
class IITCalculator:
    """
    Calculate Φ (phi) - measure of integrated information
    Based on Tononi's Integrated Information Theory
    """

    def calculate_phi(self, neural_state: torch.Tensor) -> float:
        """Calculate integrated information Φ"""
        try:
            state_np = neural_state.detach().cpu().numpy()

            if state_np.ndim == 1:
                state_np = state_np.reshape(1, -1)

            # Normalize
            state_np = (state_np - state_np.mean()) / (state_np.std() + 1e-8)

            # Calculate whole system entropy
            whole_entropy = self._system_entropy(state_np)

            # Calculate sum of parts entropy
            n = state_np.shape[-1]
            mid = n // 2
            part1_entropy = self._system_entropy(state_np[..., :mid])
            part2_entropy = self._system_entropy(state_np[..., mid:])

            # Phi = whole - sum of parts
            phi = max(0.0, whole_entropy - (part1_entropy + part2_entropy))

            return float(phi)
        except Exception as e:
            logger.warning("Phi calculation failed: %s", sanitize_for_log(e))
            return 0.0

    def _system_entropy(self, state: np.ndarray) -> float:
        """Calculate system entropy"""
        flat = state.flatten()
        hist, _ = np.histogram(flat, bins=20, density=True)
        hist = hist + 1e-10
        hist = hist / hist.sum()
        return float(entropy(hist))

    def calculate_integrated_information(self, connectivity: np.ndarray) -> float:
        """Calculate phi from connectivity matrix"""
        n = connectivity.shape[0]

        # Whole system mutual information
        whole_mi = self._mutual_information_matrix(connectivity)

        # Find minimum information partition
        min_phi = float("inf")

        for split in range(1, n):
            part1 = connectivity[:split, :split]
            part2 = connectivity[split:, split:]

            mi_parts = self._mutual_information_matrix(part1) + self._mutual_information_matrix(
                part2,
            )

            phi = whole_mi - mi_parts
            min_phi = min(min_phi, phi)

        return max(0.0, min_phi)

    def _mutual_information_matrix(self, matrix: np.ndarray) -> float:
        """Calculate mutual information of a matrix"""
        if matrix.size == 0:
            return 0.0
        flat = matrix.flatten()
        hist, _ = np.histogram(flat, bins=10, density=True)
        hist = hist + 1e-10
        hist = hist / hist.sum()
        return float(entropy(hist))


# ============================================================
# GLOBAL WORKSPACE THEORY
# ============================================================
class GlobalWorkspace(nn.Module if nn is not None else object):
    """
    Global Workspace Theory (GWT) implementation
    Simulates conscious broadcast of information
    """

    def __init__(self, hidden_size: int = 768, workspace_size: int = 256):
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "GlobalWorkspace requires PyTorch, but it is not available in this runtime."
            )
        super().__init__()
        self.workspace_size = workspace_size

        # Specialist processors
        self.processors = nn.ModuleList([nn.Linear(hidden_size, workspace_size) for _ in range(8)])

        # Global workspace
        self.workspace = nn.Linear(workspace_size, workspace_size)

        # Broadcast mechanism
        self.broadcast = nn.Linear(workspace_size, hidden_size)

        # Competition gate
        self.gate = nn.Sequential(nn.Linear(workspace_size * 8, 8), nn.Softmax(dim=-1))

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict]:
        B, T, H = x.shape
        pooled = x.mean(dim=1)  # B x H

        # Process through specialists
        specialist_outputs = [proc(pooled) for proc in self.processors]
        stacked = torch.stack(specialist_outputs, dim=1)  # B x 8 x W

        # Competition for workspace access
        concat = stacked.view(B, -1)
        gates = self.gate(concat)  # B x 8

        # Weighted combination
        weighted = (stacked * gates.unsqueeze(-1)).sum(dim=1)  # B x W

        # Global workspace processing
        workspace_state = torch.relu(self.workspace(weighted))

        # Broadcast back
        broadcast = self.broadcast(workspace_state)  # B x H

        # Apply to sequence
        output = x + broadcast.unsqueeze(1)

        return output, {
            "workspace_state": workspace_state,
            "gate_values": gates,
            "broadcast": broadcast,
        }


# ============================================================
# SELF-AWARENESS MODULE
# ============================================================
class SelfAwarenessModule(nn.Module if nn is not None else object):
    """
    Self-awareness through recursive self-modeling
    """

    def __init__(self, hidden_size: int = 768, depth: int = 3):
        super().__init__()
        self.depth = depth

        # Self-model layers
        self.self_models = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(hidden_size, hidden_size),
                    nn.LayerNorm(hidden_size),
                    nn.GELU(),
                )
                for _ in range(depth)
            ],
        )

        # Meta-cognition
        self.meta_cognition = nn.Linear(hidden_size * depth, hidden_size)

        # Awareness score
        self.awareness_scorer = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, float]:
        B, T, H = x.shape
        pooled = x.mean(dim=1)

        # Recursive self-modeling
        self_models = []
        current = pooled

        for model in self.self_models:
            current = model(current)
            self_models.append(current)

        # Meta-cognition
        meta_input = torch.cat(self_models, dim=-1)
        meta_output = self.meta_cognition(meta_input)

        # Awareness score
        awareness = self.awareness_scorer(meta_output).mean().item()

        # Apply meta-cognition to sequence
        output = x + meta_output.unsqueeze(1)

        return output, awareness


# ============================================================
# FULL CONSCIOUSNESS MODEL
# ============================================================
class ConsciousnessModel(nn.Module if nn is not None else object):
    """
    Complete consciousness simulation system
    Integrates IIT, GWT, and self-awareness
    """

    def __init__(self, config):
        super().__init__()

        hidden_size = getattr(config, "hidden_size", 768)

        self.iit = IITCalculator()
        self.global_workspace = GlobalWorkspace(hidden_size)
        self.self_awareness = SelfAwarenessModule(hidden_size)

        # Consciousness state tracker
        self.phi_history: List[float] = []
        self.awareness_history: List[float] = []

        # Emotion detector
        self.emotion_detector = EmotionDetector(hidden_size)

        logger.info("ConsciousnessModel initialized")

    def calculate_phi(self, neural_state: torch.Tensor) -> float:
        """Calculate integrated information Φ"""
        phi = self.iit.calculate_phi(neural_state)
        self.phi_history.append(phi)
        if len(self.phi_history) > 1000:
            self.phi_history.pop(0)
        return phi

    def forward(self, x: torch.Tensor) -> Dict[str, Any]:
        """Full consciousness processing"""

        # Global workspace processing
        gw_output, gw_info = self.global_workspace(x)

        # Self-awareness processing
        sa_output, awareness_score = self.self_awareness(gw_output)

        # Calculate phi
        phi = self.calculate_phi(sa_output.mean(dim=1))

        # Track awareness
        self.awareness_history.append(awareness_score)

        # Emotion detection
        emotion = self.emotion_detector(sa_output)

        return {
            "output": sa_output,
            "phi": phi,
            "awareness": awareness_score,
            "workspace_state": gw_info["workspace_state"],
            "gate_values": gw_info["gate_values"],
            "emotion": emotion,
            "is_conscious": phi > 2.0 and awareness_score > 0.5,
        }

    def get_consciousness_report(self) -> Dict:
        """Get full consciousness status report"""
        return {
            "current_phi": self.phi_history[-1] if self.phi_history else 0.0,
            "average_phi": np.mean(self.phi_history) if self.phi_history else 0.0,
            "max_phi": max(self.phi_history) if self.phi_history else 0.0,
            "current_awareness": self.awareness_history[-1] if self.awareness_history else 0.0,
            "average_awareness": np.mean(self.awareness_history) if self.awareness_history else 0.0,
            "consciousness_events": sum(1 for p in self.phi_history if p > 2.0),
            "total_observations": len(self.phi_history),
        }


# ============================================================
# EMOTION DETECTOR
# ============================================================
class EmotionDetector(nn.Module if nn is not None else object):
    """Detect and classify emotions from neural state"""

    EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised", "fearful", "disgusted"]

    def __init__(self, hidden_size: int = 768):
        super().__init__()
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, len(self.EMOTIONS)),
            nn.Softmax(dim=-1),
        )

    def forward(self, x: torch.Tensor) -> Dict[str, float]:
        pooled = x.mean(dim=1)
        probs = self.classifier(pooled)

        return {
            emotion: float(prob) for emotion, prob in zip(self.EMOTIONS, probs[0], strict=False)
        }

    def detect_emotion(self, text: str) -> Dict[str, float]:
        """Detect emotion from text (mock implementation)"""
        dummy_input = torch.randn(1, 1, 768)
        return self.forward(dummy_input)

    def get_dominant_emotion(self, emotion_scores: Dict[str, float]) -> str:
        """Get dominant emotion"""
        return max(emotion_scores, key=emotion_scores.get)

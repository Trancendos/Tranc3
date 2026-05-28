"""
AeonMind Fluidic-Liquidic Reservoir — Python Implementation.

Implements a Liquid State Machine (LSM) using reservoir computing
with leaky integrator neurons, spectral radius scaling, and
adaptive fluidic state tracking. Provides a high-dimensional
temporal representation for downstream decision systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple  # noqa: UP035

import numpy as np


@dataclass
class ReservoirConfig:
    """Configuration for the Liquid Reservoir."""
    input_size: int = 10
    reservoir_size: int = 200
    spectral_radius: float = 0.95
    leaking_rate: float = 0.3
    input_scaling: float = 1.0
    connectivity: float = 0.1
    washout: int = 50
    seed: Optional[int] = None  # noqa: UP045


@dataclass
class FluidicState:
    """Adaptive fluidic state tracking for an agent."""
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(8))
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros(8))
    energy: float = 1.0
    coherence: float = 1.0
    entropy: float = 0.0
    compression: float = 1.0
    timestamp: float = 0.0

    def update(self, new_state: np.ndarray, dt: float = 0.1) -> None:
        """Update fluidic state with new observation."""
        state_dim = min(len(new_state), len(self.velocity))
        new_accel = (new_state[:state_dim] - self.velocity[:state_dim]) / max(dt, 1e-6)
        self.acceleration[:state_dim] = 0.9 * self.acceleration[:state_dim] + 0.1 * new_accel
        self.velocity[:state_dim] = new_state[:state_dim]
        self.energy = float(np.linalg.norm(self.velocity))
        self.coherence = float(1.0 / (1.0 + np.std(self.velocity)))
        self.entropy = self._compute_entropy()
        self.compression = self._compute_compression()
        self.timestamp += dt

    def _compute_entropy(self) -> float:
        """Compute approximate entropy of the velocity state."""
        v = self.velocity
        v_norm = v / (np.linalg.norm(v) + 1e-10)
        probs = np.abs(v_norm) + 1e-10
        probs = probs / np.sum(probs)
        return float(-np.sum(probs * np.log(probs)))

    def _compute_compression(self) -> float:
        """Compute compression ratio based on energy concentration."""
        total = np.sum(np.abs(self.velocity)) + 1e-10
        max_val = np.max(np.abs(self.velocity)) + 1e-10
        return float(max_val / total)

    def decay(self, rate: float = 0.99) -> None:
        """Apply exponential decay to the fluidic state."""
        self.velocity *= rate
        self.acceleration *= rate
        self.energy *= rate

    def compress(self) -> np.ndarray:
        """Return compressed state representation."""
        return np.array([
            self.energy,
            self.coherence,
            self.entropy,
            self.compression,
            float(np.mean(self.velocity)),
            float(np.std(self.velocity)),
            float(np.mean(self.acceleration)),
            self.timestamp,
        ])


@dataclass
class ReservoirState:
    """Snapshot of the reservoir state."""
    internal_state: np.ndarray
    fluidic_state: FluidicState
    spectral_radius: float
    connectivity: float


class LiquidReservoir:
    """Liquid State Machine using reservoir computing.

    Implements a recurrent reservoir with leaky integrator neurons,
    spectral radius scaling for stability, and fluidic state tracking
    for adaptive behavior.
    """

    def __init__(self, config: Optional[ReservoirConfig] = None):  # noqa: UP045
        self.config = config or ReservoirConfig()
        self.rng = np.random.RandomState(self.config.seed)

        # Initialize reservoir weights
        self._W_input = self.rng.randn(
            self.config.reservoir_size, self.config.input_size
        ) * self.config.input_scaling

        self._W_reservoir = self._init_reservoir_weights()
        self._state = np.zeros(self.config.reservoir_size)
        self.fluidic = FluidicState(
            velocity=np.zeros(min(self.config.reservoir_size, 8))
        )
        self._trained_readout: Optional[np.ndarray] = None  # noqa: UP045

    def _init_reservoir_weights(self) -> np.ndarray:
        """Initialize reservoir weight matrix with target spectral radius."""
        n = self.config.reservoir_size
        W = self.rng.randn(n, n)  # noqa: N806

        # Apply sparsity
        mask = self.rng.rand(n, n) < self.config.connectivity
        W = W * mask  # noqa: N806

        # Scale to target spectral radius
        try:
            eigenvalues = np.linalg.eigvals(W)
            max_eigenvalue = np.max(np.abs(eigenvalues))
            if max_eigenvalue > 0:
                W = W * (self.config.spectral_radius / max_eigenvalue)  # noqa: N806
        except np.linalg.LinAlgError:
            W = W * 0.1  # fallback scaling  # noqa: N806

        return W

    def step(self, input_data: np.ndarray) -> np.ndarray:
        """Process a single input through the reservoir.

        Uses leaky integrator neuron model:
        x(t+1) = (1 - α)x(t) + α * tanh(W_in * u(t) + W_res * x(t))
        """
        input_proj = self._W_input @ input_data
        recurrent = self._W_reservoir @ self._state
        pre_activation = input_proj + recurrent

        # Leaky integrator update
        new_state = (1 - self.config.leaking_rate) * self._state + \
                    self.config.leaking_rate * np.tanh(pre_activation)

        self._state = new_state

        # Update fluidic state
        state_summary = self._state[:8]  # take first 8 dimensions
        self.fluidic.update(state_summary)

        return self._state.copy()

    def process_sequence(self, inputs: np.ndarray) -> np.ndarray:
        """Process a sequence of inputs, returning all states.

        Args:
            inputs: Shape (seq_len, input_size)

        Returns:
            states: Shape (seq_len, reservoir_size)
        """
        states = []
        for t in range(len(inputs)):
            state = self.step(inputs[t])
            states.append(state)
        return np.array(states)

    def reset(self) -> None:
        """Reset the reservoir state to zeros."""
        self._state = np.zeros(self.config.reservoir_size)
        self.fluidic = FluidicState(
            velocity=np.zeros(min(self.config.reservoir_size, 8))
        )

    def warmup(self, n_steps: int = 50) -> None:
        """Warm up the reservoir with random inputs."""
        for _ in range(n_steps):
            random_input = self.rng.randn(self.config.input_size) * 0.1
            self.step(random_input)

    def get_state_features(self) -> np.ndarray:
        """Get current state features including fluidic state."""
        state_features = self._state.copy()
        fluidic_features = self.fluidic.compress()
        return np.concatenate([state_features, fluidic_features])

    def train_readout(
        self,
        inputs: np.ndarray,
        targets: np.ndarray,
        reg: float = 1e-4,
    ) -> float:
        """Train a linear readout using ridge regression.

        Args:
            inputs: Shape (n_samples, input_size)
            targets: Shape (n_samples, output_size)
            reg: Regularization parameter

        Returns:
            Training MSE
        """
        # Collect reservoir states (skip washout)
        states = self.process_sequence(inputs)
        states = states[self.config.washout:]
        targets_trimmed = targets[self.config.washout:]

        # Ridge regression: W_out = (S^T S + λI)^-1 S^T T
        S = states  # noqa: N806
        n_features = S.shape[1]
        self._trained_readout = np.linalg.solve(
            S.T @ S + reg * np.eye(n_features),
            S.T @ targets_trimmed,
        )

        # Compute training MSE
        predictions = S @ self._trained_readout
        mse = float(np.mean((predictions - targets_trimmed) ** 2))
        return mse

    def predict(self, input_data: np.ndarray) -> np.ndarray:
        """Predict output using trained readout."""
        if self._trained_readout is None:
            raise ValueError("Readout not trained. Call train_readout() first.")
        state = self.step(input_data)
        return state @ self._trained_readout

    def adapt_spectral_radius(self, target: float = 0.95) -> None:
        """Adapt the spectral radius of the reservoir weights."""
        try:
            eigenvalues = np.linalg.eigvals(self._W_reservoir)
            current_sr = np.max(np.abs(eigenvalues))
            if current_sr > 0:
                scale = target / current_sr
                self._W_reservoir *= scale
                self.config.spectral_radius = target
        except np.linalg.LinAlgError:
            pass

    def fluidic_state(self) -> FluidicState:
        """Get the current fluidic state."""
        return self.fluidic

    def reservoir_state(self) -> ReservoirState:
        """Get a snapshot of the full reservoir state."""
        try:
            eigenvalues = np.linalg.eigvals(self._W_reservoir)
            sr = float(np.max(np.abs(eigenvalues)))
        except np.linalg.LinAlgError:
            sr = 0.0

        connectivity = float(np.count_nonzero(self._W_reservoir) / self._W_reservoir.size)

        return ReservoirState(
            internal_state=self._state.copy(),
            fluidic_state=self.fluidic,
            spectral_radius=sr,
            connectivity=connectivity,
        )

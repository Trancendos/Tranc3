"""
AeonMind Quantum Decision Circuit — Python Implementation.

Implements variational quantum circuits with multi-layer parameterized
Rot gates + CNOT entangling, parameter shift rule for gradients,
and adaptive depth control. Supports dual-path execution:
  - PennyLane (hardware/simulator) when available
  - Pure NumPy fallback (zero-dependency)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np


class EntanglingStrategy(Enum):
    """Entangling strategy for quantum circuits."""

    LINEAR = "linear"
    CIRCULAR = "circular"
    FULL = "full"


@dataclass
class QuantumCircuitConfig:
    """Configuration for the Quantum Decision Circuit."""

    n_qubits: int = 4
    n_layers: int = 2
    rotations_per_layer: int = 3
    adaptive_depth: bool = True
    max_depth: int = 10
    entangling_gate: str = "CNOT"
    entangling_strategy: EntanglingStrategy = EntanglingStrategy.LINEAR
    parameter_range: tuple[float, float] = (-math.pi, math.pi)


@dataclass
class OptimizationStep:
    """Result of a single optimization step."""

    step: int
    cost: float
    gradient_norm: float
    learning_rate: float


@dataclass
class CircuitSummary:
    """Summary of the quantum circuit state."""

    n_qubits: int
    n_layers: int
    rotations_per_layer: int
    total_parameters: int
    entangling_strategy: str
    current_cost: float | None = None
    optimization_steps: int = 0


class QuantumDecisionCircuit:
    """Quantum Decision Circuit with variational layers.

    Implements multi-layer parameterized rotations (Rx, Ry, Rz)
    with CNOT entangling between layers. Uses the parameter shift
    rule for gradient computation and supports adaptive depth control.
    """

    def __init__(self, config: QuantumCircuitConfig | None = None):
        self.config = config or QuantumCircuitConfig()
        self._n_params = (
            self.config.n_qubits * self.config.rotations_per_layer * self.config.n_layers
        )
        # Initialize parameters uniformly
        low, high = self.config.parameter_range
        self._parameters = np.random.uniform(low * 0.1, high * 0.1, self._n_params)
        self._state: np.ndarray | None = None
        self._probabilities: np.ndarray | None = None
        self._cost_history: list[float] = []
        self._optimization_steps = 0
        self._current_cost: float | None = None

    @property
    def parameters(self) -> np.ndarray:
        return self._parameters.copy()

    @parameters.setter
    def parameters(self, values: np.ndarray) -> None:
        self._parameters = values.copy()

    def execute(self, use_pennylane: bool = True) -> np.ndarray:
        """Execute the quantum circuit and return measurement probabilities.

        Attempts PennyLane first (if available and requested),
        falls back to pure NumPy simulation.
        """
        if use_pennylane:
            try:
                return self._execute_pennylane()
            except ImportError:
                pass
        return self._execute_numpy()

    def _execute_pennylane(self) -> np.ndarray:
        """Execute using PennyLane for hardware/simulator support."""
        import pennylane as qml  # noqa: F401

        n_qubits = self.config.n_qubits
        dev = qml.device("default.qubit", wires=n_qubits)

        params = self._parameters.copy()
        n_layers = self.config.n_layers
        rotations_per_layer = self.config.rotations_per_layer

        @qml.qnode(dev)
        def circuit(params_flat):
            idx = 0
            for _layer in range(n_layers):
                for qubit in range(n_qubits):
                    for r in range(rotations_per_layer):
                        if idx >= len(params_flat):
                            break
                        angle = params_flat[idx]
                        if r % 3 == 0:
                            qml.Rot(angle, angle * 0.5, angle * 0.3, wires=qubit)
                        elif r % 3 == 1:
                            qml.Ry(angle, wires=qubit)
                        else:
                            qml.Rz(angle, wires=qubit)
                        idx += 1
                # Entangling layer
                for i in range(n_qubits - 1):
                    qml.CNOT(wires=[i, i + 1])
                if self.config.entangling_strategy == EntanglingStrategy.CIRCULAR:
                    qml.CNOT(wires=[n_qubits - 1, 0])

            return qml.probs(wires=list(range(n_qubits)))

        self._probabilities = np.array(circuit(params))
        return self._probabilities

    def _apply_ry_batch(
        self, state: np.ndarray, qubit: int, n: int, angle: np.ndarray
    ) -> np.ndarray:
        dim = 2**n
        cos_a = np.cos(angle / 2)[:, np.newaxis]
        sin_a = np.sin(angle / 2)[:, np.newaxis]
        new_state = np.zeros_like(state)
        for i in range(dim):
            bit = (i >> (n - 1 - qubit)) & 1
            j = i ^ (1 << (n - 1 - qubit))
            if bit == 0:
                new_state[:, i] = cos_a[:, 0] * state[:, i] - sin_a[:, 0] * state[:, j]
                new_state[:, j] = sin_a[:, 0] * state[:, i] + cos_a[:, 0] * state[:, j]
        return new_state

    def _apply_rz_batch(
        self, state: np.ndarray, qubit: int, n: int, angle: np.ndarray
    ) -> np.ndarray:
        dim = 2**n
        exp_minus = np.exp(-1j * angle / 2)[:, np.newaxis]
        exp_plus = np.exp(1j * angle / 2)[:, np.newaxis]
        new_state = state.copy()
        for i in range(dim):
            bit = (i >> (n - 1 - qubit)) & 1
            if bit == 1:
                new_state[:, i] *= exp_minus[:, 0]
            else:
                new_state[:, i] *= exp_plus[:, 0]
        return new_state

    def _apply_rot_batch(
        self,
        state: np.ndarray,
        qubit: int,
        n: int,
        phi: np.ndarray,
        theta: np.ndarray,
        omega: np.ndarray,
    ) -> np.ndarray:
        state = self._apply_rz_batch(state, qubit, n, phi)
        state = self._apply_ry_batch(state, qubit, n, theta)
        state = self._apply_rz_batch(state, qubit, n, omega)
        return state

    def _apply_cnot_batch(self, state: np.ndarray, control: int, target: int, n: int) -> np.ndarray:
        dim = 2**n
        new_state = state.copy()
        for i in range(dim):
            control_bit = (i >> (n - 1 - control)) & 1
            if control_bit == 1:
                j = i ^ (1 << (n - 1 - target))
                new_state[:, j] = state[:, i]
                new_state[:, i] = state[:, j]
        return new_state

    def _apply_entangling_numpy_batch(self, state: np.ndarray, n: int) -> np.ndarray:
        new_state = state.copy()
        if self.config.entangling_strategy == EntanglingStrategy.LINEAR:
            pairs = [(i, i + 1) for i in range(n - 1)]
        elif self.config.entangling_strategy == EntanglingStrategy.CIRCULAR:
            pairs = [(i, (i + 1) % n) for i in range(n)]
        elif self.config.entangling_strategy == EntanglingStrategy.FULL:
            pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        else:
            pairs = [(i, i + 1) for i in range(n - 1)]

        for control, target in pairs:
            if control >= n or target >= n:
                continue
            new_state = self._apply_cnot_batch(new_state, control, target, n)
        return new_state

    def _execute_numpy_batch(self, param_sets: np.ndarray) -> np.ndarray:
        """Execute using pure NumPy state-vector simulation for a batch of parameters.

        Args:
            param_sets: Array of shape (B, n_params)

        Returns:
            Array of shape (B, 2**n_qubits) containing measurement probabilities.
        """
        n = self.config.n_qubits
        dim = 2**n
        B = param_sets.shape[0]

        # Initialize to |0...0⟩
        state = np.zeros((B, dim), dtype=complex)
        state[:, 0] = 1.0 + 0j

        # Apply parameterized layers
        idx = 0
        for _layer in range(self.config.n_layers):
            for qubit in range(n):
                for r in range(self.config.rotations_per_layer):
                    if idx >= self._n_params:
                        break
                    angle = param_sets[:, idx]
                    if r % 3 == 0:
                        state = self._apply_rot_batch(
                            state, qubit, n, angle, angle * 0.5, angle * 0.3
                        )
                    elif r % 3 == 1:
                        state = self._apply_ry_batch(state, qubit, n, angle)
                    else:
                        state = self._apply_rz_batch(state, qubit, n, angle)
                    idx += 1
            # Entangling
            state = self._apply_entangling_numpy_batch(state, n)

        # Measurement probabilities
        probs = np.abs(state) ** 2
        probs = probs / np.sum(probs, axis=1, keepdims=True)  # Normalize

        return probs

    def _execute_numpy(self) -> np.ndarray:
        """Execute using pure NumPy state-vector simulation."""
        n = self.config.n_qubits
        dim = 2**n

        # Initialize to |0...0⟩
        state = np.zeros(dim, dtype=complex)
        state[0] = 1.0 + 0j

        # Apply parameterized layers
        idx = 0
        for _layer in range(self.config.n_layers):
            for qubit in range(n):
                for r in range(self.config.rotations_per_layer):
                    if idx >= len(self._parameters):
                        break
                    angle = self._parameters[idx]
                    if r % 3 == 0:
                        state = self._apply_rot(state, qubit, n, angle, angle * 0.5, angle * 0.3)
                    elif r % 3 == 1:
                        state = self._apply_ry(state, qubit, n, angle)
                    else:
                        state = self._apply_rz(state, qubit, n, angle)
                    idx += 1
            # Entangling
            state = self._apply_entangling_numpy(state, n)

        # Measurement probabilities
        probs = np.abs(state) ** 2
        probs = probs / np.sum(probs)  # Normalize

        self._state = state
        self._probabilities = probs
        return probs

    def _apply_rx(self, state: np.ndarray, qubit: int, n: int, angle: float) -> np.ndarray:
        """Apply Rx gate to the given qubit."""
        dim = 2**n
        cos_a = math.cos(angle / 2)
        sin_a = math.sin(angle / 2)
        new_state = np.zeros_like(state)
        for i in range(dim):
            bit = (i >> (n - 1 - qubit)) & 1
            j = i ^ (1 << (n - 1 - qubit))
            if bit == 0:
                new_state[i] = cos_a * state[i] - 1j * sin_a * state[j]
                new_state[j] = -1j * sin_a * state[i] + cos_a * state[j]
        return new_state

    def _apply_ry(self, state: np.ndarray, qubit: int, n: int, angle: float) -> np.ndarray:
        """Apply Ry gate to the given qubit."""
        dim = 2**n
        cos_a = math.cos(angle / 2)
        sin_a = math.sin(angle / 2)
        new_state = np.zeros_like(state)
        for i in range(dim):
            bit = (i >> (n - 1 - qubit)) & 1
            j = i ^ (1 << (n - 1 - qubit))
            if bit == 0:
                new_state[i] = cos_a * state[i] - sin_a * state[j]
                new_state[j] = sin_a * state[i] + cos_a * state[j]
        return new_state

    def _apply_rz(self, state: np.ndarray, qubit: int, n: int, angle: float) -> np.ndarray:
        """Apply Rz gate to the given qubit."""
        dim = 2**n
        new_state = state.copy()
        for i in range(dim):
            bit = (i >> (n - 1 - qubit)) & 1
            if bit == 1:
                new_state[i] *= np.exp(-1j * angle / 2)
            else:
                new_state[i] *= np.exp(1j * angle / 2)
        return new_state

    def _apply_rot(
        self, state: np.ndarray, qubit: int, n: int, phi: float, theta: float, omega: float
    ) -> np.ndarray:
        """Apply Rot(φ,θ,ω) = Rz(ω)·Ry(θ)·Rz(φ) gate."""
        state = self._apply_rz(state, qubit, n, phi)
        state = self._apply_ry(state, qubit, n, theta)
        state = self._apply_rz(state, qubit, n, omega)
        return state

    def _apply_entangling_numpy(self, state: np.ndarray, n: int) -> np.ndarray:
        """Apply entangling CNOT gates based on strategy."""
        new_state = state.copy()

        if self.config.entangling_strategy == EntanglingStrategy.LINEAR:
            pairs = [(i, i + 1) for i in range(n - 1)]
        elif self.config.entangling_strategy == EntanglingStrategy.CIRCULAR:
            pairs = [(i, (i + 1) % n) for i in range(n)]
        elif self.config.entangling_strategy == EntanglingStrategy.FULL:
            pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        else:
            pairs = [(i, i + 1) for i in range(n - 1)]

        for control, target in pairs:
            if control >= n or target >= n:
                continue
            new_state = self._apply_cnot_numpy(new_state, control, target, n)

        return new_state

    def _apply_cnot_numpy(self, state: np.ndarray, control: int, target: int, n: int) -> np.ndarray:
        """Apply CNOT gate using state-vector manipulation."""
        dim = 2**n
        new_state = state.copy()
        for i in range(dim):
            control_bit = (i >> (n - 1 - control)) & 1
            if control_bit == 1:
                j = i ^ (1 << (n - 1 - target))
                new_state[j] = state[i]
                new_state[i] = state[j]
        return new_state

    def decide(self, use_pennylane: bool = True) -> int:
        """Make a decision by measuring the circuit."""
        probs = self.execute(use_pennylane=use_pennylane)
        return int(np.argmax(probs))

    def decide_probabilistic(self, use_pennylane: bool = True) -> int:
        """Make a probabilistic decision by sampling from the distribution."""
        probs = self.execute(use_pennylane=use_pennylane)
        return int(np.random.choice(len(probs), p=probs))

    def decision_confidence(self, use_pennylane: bool = True) -> float:
        """Get confidence of the current decision."""
        probs = self.execute(use_pennylane=use_pennylane)
        return float(np.max(probs))

    def compute_cost(self, target: np.ndarray | None = None, cost_type: str = "entropy") -> float:
        """Compute the cost function value.

        Args:
            target: Target probability distribution (for cross-entropy)
            cost_type: 'entropy' or 'cross_entropy'
        """
        if self._probabilities is None:
            self.execute(use_pennylane=False)

        if cost_type == "entropy":
            # Minimize entropy to get sharper decisions
            probs = self._probabilities + 1e-10
            entropy = -np.sum(probs * np.log(probs))
            cost = float(entropy)
        elif cost_type == "cross_entropy" and target is not None:
            probs = self._probabilities + 1e-10
            cost = float(-np.sum(target * np.log(probs)))
        else:
            probs = self._probabilities + 1e-10
            entropy = -np.sum(probs * np.log(probs))
            cost = float(entropy)

        self._current_cost = cost
        return cost

    def compute_gradients(self, use_pennylane: bool = True) -> np.ndarray:
        """Compute gradients using the parameter shift rule.

        For each parameter θᵢ:
          ∂f/∂θᵢ = [f(θᵢ + π/2) - f(θᵢ - π/2)] / 2
        """
        if use_pennylane:
            try:
                import pennylane as qml  # noqa: F401

                # For pennylane, stick with the sequential loop, but fix the bug
                gradients = np.zeros(self._n_params)
                shift = math.pi / 2
                original_params = self._parameters.copy()

                for i in range(self._n_params):
                    self._parameters[i] = original_params[i] + shift
                    self._probabilities = None
                    cost_plus = self.compute_cost()

                    self._parameters[i] = original_params[i] - shift
                    self._probabilities = None
                    cost_minus = self.compute_cost()

                    gradients[i] = (cost_plus - cost_minus) / 2.0
                    self._parameters[i] = original_params[i]

                self._probabilities = None
                return gradients
            except ImportError:
                pass

        # Bulk fetch data using NumPy batch processing to avoid N+1 queries
        gradients = np.zeros(self._n_params)
        shift = math.pi / 2

        # Pre-generate all shifted parameter sets: shape (2 * n_params, n_params)
        param_sets = np.tile(self._parameters, (2 * self._n_params, 1))
        for i in range(self._n_params):
            param_sets[2 * i, i] += shift
            param_sets[2 * i + 1, i] -= shift

        # Execute all circuits in a single batch
        probs_batch = self._execute_numpy_batch(param_sets)

        # Compute cost for each parameter set.
        # Default cost_type used by optimize() is "entropy"
        # We need to manually calculate entropy for the batch
        probs_batch = probs_batch + 1e-10
        entropy = -np.sum(probs_batch * np.log(probs_batch), axis=1)

        for i in range(self._n_params):
            cost_plus = float(entropy[2 * i])
            cost_minus = float(entropy[2 * i + 1])
            gradients[i] = (cost_plus - cost_minus) / 2.0

        return gradients

    def optimize(
        self,
        n_steps: int = 100,
        learning_rate: float = 0.01,
        use_pennylane: bool = True,
        gradient_clip: float = 1.0,
    ) -> int:
        """Optimize circuit parameters using gradient descent.

        Uses the parameter shift rule for gradients with adaptive
        learning rate and gradient clipping.
        """
        # Initial execution
        self.execute(use_pennylane=use_pennylane)

        for _step in range(n_steps):
            # Compute cost (uses existing self._probabilities)
            cost = self.compute_cost()
            self._cost_history.append(cost)

            # Compute gradients (this now uses bulk fetching and preserves state)
            gradients = self.compute_gradients(use_pennylane=use_pennylane)

            # Gradient clipping
            grad_norm = np.linalg.norm(gradients)
            if grad_norm > gradient_clip:
                gradients = gradients * (gradient_clip / grad_norm)

            # Adaptive learning rate
            if len(self._cost_history) >= 2:
                if self._cost_history[-1] > self._cost_history[-2]:
                    learning_rate *= 0.5
                else:
                    learning_rate = min(learning_rate * 1.05, 0.1)

            # Update parameters
            self._parameters -= learning_rate * gradients
            self._optimization_steps += 1

            # Execute circuit with new parameters for the next iteration
            self._probabilities = None
            self.execute(use_pennylane=use_pennylane)

        self._current_cost = self._cost_history[-1] if self._cost_history else None
        return self._optimization_steps

    def _adapt_layer_depth(self) -> None:
        """Adapt the number of layers based on performance."""
        if len(self._cost_history) < 10:
            return

        recent_costs = self._cost_history[-10:]
        improvement = recent_costs[0] - recent_costs[-1]

        if improvement < 1e-6 and self.config.n_layers < self.config.max_depth:
            self.config.n_layers += 1
            # Add new parameters for the new layer
            new_params = np.random.uniform(
                self.config.parameter_range[0] * 0.1,
                self.config.parameter_range[1] * 0.1,
                self.config.n_qubits * self.config.rotations_per_layer,
            )
            self._parameters = np.concatenate([self._parameters, new_params])
            self._n_params = len(self._parameters)

    def circuit_summary(self) -> CircuitSummary:
        """Get a summary of the current circuit state."""
        return CircuitSummary(
            n_qubits=self.config.n_qubits,
            n_layers=self.config.n_layers,
            rotations_per_layer=self.config.rotations_per_layer,
            total_parameters=self._n_params,
            entangling_strategy=self.config.entangling_strategy.value,
            current_cost=self._current_cost,
            optimization_steps=self._optimization_steps,
        )

    def reset(self) -> None:
        """Reset the circuit to initial state."""
        low, high = self.config.parameter_range
        self._parameters = np.random.uniform(low * 0.1, high * 0.1, self._n_params)
        self._state = None
        self._probabilities = None
        self._cost_history = []
        self._optimization_steps = 0
        self._current_cost = None

    def fidelity(self, target_state: np.ndarray) -> float:
        """Compute fidelity with a target state."""
        if self._state is None:
            self.execute(use_pennylane=False)
        overlap = np.abs(np.dot(np.conj(self._state), target_state)) ** 2
        return float(overlap)

    def entropy(self) -> float:
        """Compute the Shannon entropy of the measurement distribution."""
        if self._probabilities is None:
            self.execute(use_pennylane=False)
        probs = self._probabilities + 1e-10
        return float(-np.sum(probs * np.log(probs)))

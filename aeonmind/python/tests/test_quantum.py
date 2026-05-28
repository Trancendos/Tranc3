"""
Tests for AeonMind Quantum Decision Circuit.
"""

import numpy as np  # noqa: F401

from aeonmind.core.quantum import QuantumCircuitConfig, QuantumDecisionCircuit


class TestQuantumCircuitConfig:
    """Tests for QuantumCircuitConfig."""

    def test_default_config(self):
        config = QuantumCircuitConfig()
        assert config.n_qubits == 4
        assert config.n_layers == 2
        assert config.rotations_per_layer == 3

    def test_custom_config(self):
        config = QuantumCircuitConfig(n_qubits=6, n_layers=3, rotations_per_layer=4)
        assert config.n_qubits == 6
        assert config.n_layers == 3


class TestQuantumDecisionCircuit:
    """Tests for the QuantumDecisionCircuit."""

    def test_circuit_creation(self):
        circuit = QuantumDecisionCircuit(QuantumCircuitConfig(n_qubits=4, n_layers=2))
        assert circuit is not None
        assert circuit.config.n_qubits == 4

    def test_execute_numpy(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=1, rotations_per_layer=2)
        circuit = QuantumDecisionCircuit(config)
        probabilities = circuit.execute(use_pennylane=False)
        assert len(probabilities) == 2 ** 3
        assert abs(sum(probabilities) - 1.0) < 1e-6

    def test_decide(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=2)
        circuit = QuantumDecisionCircuit(config)
        decision = circuit.decide(use_pennylane=False)
        assert 0 <= decision < 2 ** 3

    def test_decide_probabilistic(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=2)
        circuit = QuantumDecisionCircuit(config)
        decision = circuit.decide_probabilistic(use_pennylane=False)
        assert 0 <= decision < 2 ** 3

    def test_compute_cost(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=1)
        circuit = QuantumDecisionCircuit(config)
        circuit.execute(use_pennylane=False)
        cost = circuit.compute_cost()
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_compute_gradients(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=1, rotations_per_layer=2)
        circuit = QuantumDecisionCircuit(config)
        circuit.execute(use_pennylane=False)
        gradients = circuit.compute_gradients(use_pennylane=False)
        assert len(gradients) > 0

    def test_optimize(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=1, rotations_per_layer=2)
        circuit = QuantumDecisionCircuit(config)
        steps = circuit.optimize(n_steps=5, use_pennylane=False)
        assert steps == 5

    def test_circuit_summary(self):
        config = QuantumCircuitConfig(n_qubits=4, n_layers=2, rotations_per_layer=3)
        circuit = QuantumDecisionCircuit(config)
        summary = circuit.circuit_summary()
        assert summary.n_qubits == 4
        assert summary.n_layers == 2
        assert summary.total_parameters > 0

    def test_entropy(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=1)
        circuit = QuantumDecisionCircuit(config)
        circuit.execute(use_pennylane=False)
        entropy = circuit.entropy()
        assert entropy >= 0.0

    def test_reset(self):
        config = QuantumCircuitConfig(n_qubits=3, n_layers=1)
        circuit = QuantumDecisionCircuit(config)
        circuit.execute(use_pennylane=False)
        circuit.reset()
        # After reset, parameters should be re-initialized
        assert circuit is not None

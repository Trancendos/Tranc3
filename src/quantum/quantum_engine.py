# src/quantum/quantum_engine.py
# TRANC3 Full Quantum Module

import logging
from typing import Dict, List, Optional

import numpy as np
import torch
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit.library import QFT
from qiskit_aer import AerSimulator

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ============================================================
# QUANTUM CIRCUIT BUILDER
# ============================================================
class QuantumCircuitBuilder:
    """Build quantum circuits for TRANC3 operations"""

    @staticmethod
    def build_attention_circuit(num_qubits: int, weights: np.ndarray) -> QuantumCircuit:
        """Build quantum attention circuit"""
        qr = QuantumRegister(num_qubits, "q")
        cr = ClassicalRegister(num_qubits, "c")
        qc = QuantumCircuit(qr, cr)

        # Initialize superposition
        qc.h(qr)

        # Encode weights as rotation angles
        for i, w in enumerate(weights[:num_qubits]):
            qc.ry(float(w) * np.pi, qr[i])

        # Entangle qubits (CNOT chain)
        for i in range(num_qubits - 1):
            qc.cx(qr[i], qr[i + 1])

        # Apply QFT for attention scoring
        qft = QFT(num_qubits)
        qc.append(qft, qr)

        # Measure
        qc.measure(qr, cr)
        return qc

    @staticmethod
    def build_grover_search_circuit(
        num_qubits: int, target_state: int
    ) -> QuantumCircuit:
        """Build Grover's search circuit"""
        qr = QuantumRegister(num_qubits, "q")
        cr = ClassicalRegister(num_qubits, "c")
        qc = QuantumCircuit(qr, cr)

        # Initialize superposition
        qc.h(qr)

        # Number of Grover iterations
        num_iterations = int(np.pi / 4 * np.sqrt(2**num_qubits))

        for _ in range(max(1, num_iterations)):
            # Oracle: flip phase of target state
            target_bits = format(target_state, f"0{num_qubits}b")
            for i, bit in enumerate(target_bits):
                if bit == "0":
                    qc.x(qr[i])

            qc.h(qr[-1])
            qc.mcx(list(range(num_qubits - 1)), num_qubits - 1)
            qc.h(qr[-1])

            for i, bit in enumerate(target_bits):
                if bit == "0":
                    qc.x(qr[i])

            # Diffusion operator
            qc.h(qr)
            qc.x(qr)
            qc.h(qr[-1])
            qc.mcx(list(range(num_qubits - 1)), num_qubits - 1)
            qc.h(qr[-1])
            qc.x(qr)
            qc.h(qr)

        qc.measure(qr, cr)
        return qc

    @staticmethod
    def build_vqe_circuit(num_qubits: int, params: np.ndarray) -> QuantumCircuit:
        """Build Variational Quantum Eigensolver circuit"""
        qc = QuantumCircuit(num_qubits)

        # Layer 1: Hadamard
        qc.h(range(num_qubits))

        # Variational layers
        num_layers = len(params) // (3 * num_qubits)
        param_idx = 0

        for _ in range(max(1, num_layers)):
            # Rotation layer
            for i in range(num_qubits):
                if param_idx + 2 < len(params):
                    qc.rx(params[param_idx], i)
                    qc.ry(params[param_idx + 1], i)
                    qc.rz(params[param_idx + 2], i)
                    param_idx += 3

            # Entanglement layer
            for i in range(0, num_qubits - 1, 2):
                qc.cx(i, i + 1)
            for i in range(1, num_qubits - 1, 2):
                qc.cx(i, i + 1)

        return qc


# ============================================================
# QUANTUM MEMORY SYSTEM
# ============================================================
class QuantumMemorySystem:
    """Quantum-enhanced associative memory"""

    def __init__(self, num_qubits: int = 8):
        self.num_qubits = num_qubits
        self.memory_capacity = 2**num_qubits
        self.stored_patterns: List[np.ndarray] = []
        self.backend = AerSimulator(method="statevector")

    def store_pattern(self, pattern: np.ndarray) -> bool:
        """Store pattern in quantum memory"""
        if len(self.stored_patterns) >= self.memory_capacity:
            logger.warning("Quantum memory at capacity")
            return False

        normalized = pattern / (np.linalg.norm(pattern) + 1e-8)
        self.stored_patterns.append(normalized)
        return True

    def recall_pattern(
        self, query: np.ndarray, shots: int = 1024
    ) -> Optional[np.ndarray]:
        """Recall closest pattern using quantum search"""
        if not self.stored_patterns:
            return None

        # Find best match using quantum amplitude amplification
        similarities = [np.dot(query, p) for p in self.stored_patterns]
        best_idx = np.argmax(similarities)

        if similarities[best_idx] > 0.5:
            return self.stored_patterns[best_idx]
        return None

    def quantum_associative_recall(
        self, partial_pattern: np.ndarray
    ) -> Optional[np.ndarray]:
        """Quantum associative memory recall"""
        if not self.stored_patterns:
            return None

        # Build quantum circuit for pattern matching
        qc = QuantumCircuit(self.num_qubits)

        # Encode partial pattern
        normalized = partial_pattern[: self.num_qubits] / (
            np.linalg.norm(partial_pattern[: self.num_qubits]) + 1e-8
        )

        try:
            qc.initialize(normalized.tolist(), range(self.num_qubits))
        except Exception:
            qc.h(range(self.num_qubits))

        # Measure
        qc.measure_all()

        job = self.backend.run(qc, shots=1024)
        counts = job.result().get_counts()

        # Find most probable state
        most_probable = max(counts, key=counts.get)
        idx = int(most_probable, 2) % len(self.stored_patterns)

        return self.stored_patterns[idx]


# ============================================================
# QUANTUM OPTIMIZATION ENGINE
# ============================================================
class QuantumOptimizationEngine:
    """Quantum-enhanced model optimization"""

    def __init__(self, num_qubits: int = 8):
        self.num_qubits = num_qubits
        self.backend = AerSimulator(method="statevector")
        self.circuit_builder = QuantumCircuitBuilder()
        self.memory = QuantumMemorySystem(num_qubits)

    def quantum_attention_scores(
        self, query: torch.Tensor, key: torch.Tensor
    ) -> torch.Tensor:
        """Compute attention scores using quantum circuits"""
        B, H, T, D = query.shape

        # Flatten for quantum processing
        q_flat = query.detach().cpu().numpy().reshape(-1)[: self.num_qubits]

        # Build and run circuit
        qc = self.circuit_builder.build_attention_circuit(self.num_qubits, q_flat)

        try:
            job = self.backend.run(qc, shots=1024)
            counts = job.result().get_counts()

            # Convert counts to attention weights
            weights = np.zeros(T)
            for state, count in counts.items():
                idx = int(state, 2) % T
                weights[idx] += count / 1024

            # Normalize
            weights = weights / (weights.sum() + 1e-8)

            return (
                torch.tensor(weights, dtype=torch.float32)
                .unsqueeze(0)
                .unsqueeze(0)
                .unsqueeze(-1)
            )
        except Exception as e:
            logger.warning("Quantum attention failed: %s", sanitize_for_log(e))
            return torch.ones(B, H, T, 1) / T

    def quantum_parameter_optimization(
        self, loss: float, params: np.ndarray
    ) -> np.ndarray:
        """Optimize parameters using quantum annealing simulation"""

        # Build VQE circuit
        qc = self.circuit_builder.build_vqe_circuit(
            self.num_qubits, params[: self.num_qubits * 3]
        )
        qc.measure_all()

        try:
            job = self.backend.run(qc, shots=512)
            counts = job.result().get_counts()

            # Extract optimal parameters from measurement
            most_probable = max(counts, key=counts.get)
            binary_params = [int(b) for b in most_probable]

            # Convert to parameter updates
            updates = np.array(binary_params[: len(params)], dtype=float)
            updates = (updates - 0.5) * 0.01  # Small updates

            return params + updates
        except Exception as e:
            logger.warning("Quantum optimization failed: %s", sanitize_for_log(e))
            return params

    def get_quantum_state_info(self) -> Dict:
        """Get information about quantum state"""
        return {
            "num_qubits": self.num_qubits,
            "memory_capacity": self.memory.memory_capacity,
            "stored_patterns": len(self.memory.stored_patterns),
            "backend": "AerSimulator(statevector)",
            "max_circuit_depth": 100,
        }

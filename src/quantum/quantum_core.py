# src/quantum/quantum_core.py

import logging
from typing import Dict, List

import numpy as np
import torch
import torch.nn as nn
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT
from qiskit_aer import AerSimulator

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class NeuromorphicInterface:
    """Interface bridging quantum and spiking neural network layers."""

    def __init__(self, config: dict):
        self.spike_rate = config.get("spike_rate", 1000)
        self.neuron_model = config.get("neuron_model", "LIF")
        self.synaptic_plasticity = config.get("plasticity", "STDP")

    def create_spiking_network(
        self, input_dim: int, hidden_layers: List[int], output_dim: int
    ) -> nn.ModuleList:
        class SpikingNeuron(nn.Module):
            def __init__(self, input_size, output_size, tau=10.0):
                super().__init__()
                self.fc = nn.Linear(input_size, output_size, bias=False)
                self.tau = tau
                self.membrane = None

            def forward(self, x):
                if self.membrane is None:
                    self.membrane = torch.zeros_like(self.fc(x))
                self.membrane = self.membrane * (1 - 1 / self.tau) + self.fc(x)
                spike = (self.membrane > 1.0).float()
                self.membrane = self.membrane * (1 - spike)
                return spike, self.membrane

        layers = []
        prev_size = input_dim
        for hidden_size in hidden_layers:
            layers.append(SpikingNeuron(prev_size, hidden_size))
            prev_size = hidden_size
        layers.append(SpikingNeuron(prev_size, output_dim))
        return nn.ModuleList(layers)


class QuantumNeuralCore:
    """
    Quantum-Classical Hybrid Neural Architecture.
    Uses AerSimulator for quantum circuit execution.
    Designed to swap to real quantum hardware (IBM/IonQ) when available.
    """

    def __init__(self, config: dict):
        self.config = config
        self.num_qubits = min(config.get("num_qubits", 8), 16)  # Cap for simulation
        self.coherence_time = config.get("coherence_time", 1000)

        try:
            self.backend = AerSimulator(method="statevector")
            logger.info("QuantumNeuralCore initialised: %s qubits", sanitize_for_log(self.num_qubits))
        except Exception as e:
            logger.warning("AerSimulator init failed: %s — falling back to classical", sanitize_for_log(e))
            self.backend = None

        self.neuromorphic_bridge = NeuromorphicInterface(config)

    def quantum_attention(self, input_state: torch.Tensor) -> torch.Tensor:
        """
        Quantum-enhanced attention. Falls back to classical softmax if
        quantum backend is unavailable or input is too large.
        """
        if self.backend is None:
            return self._classical_attention_fallback(input_state)

        try:
            # Handle both 1D and 3D inputs
            if input_state.dim() == 1:
                flat = input_state.detach().cpu().numpy()
            else:
                flat = input_state.flatten().detach().cpu().numpy()

            n = min(self.num_qubits, 8)
            weights = flat[:n] / (np.linalg.norm(flat[:n]) + 1e-8)

            qc = QuantumCircuit(n)
            qc.h(range(n))
            for i, w in enumerate(weights):
                qc.ry(float(w) * np.pi, i)
            for i in range(n - 1):
                qc.cx(i, i + 1)
            qc.append(QFT(n), range(n))
            qc.measure_all()

            job = self.backend.run(qc, shots=512)
            counts = job.result().get_counts()

            # Map counts back to attention weights over input shape
            out = np.zeros(input_state.numel())
            for state, count in counts.items():
                idx = int(state.replace(" ", ""), 2) % len(out)
                out[idx] += count / 512

            out = out / (out.sum() + 1e-8)
            return torch.tensor(out, dtype=torch.float32).reshape(input_state.shape)

        except Exception as e:
            logger.warning("Quantum attention failed: %s — using classical fallback", sanitize_for_log(e))
            return self._classical_attention_fallback(input_state)

    def _classical_attention_fallback(self, x: torch.Tensor) -> torch.Tensor:
        return torch.softmax(x.flatten().float(), dim=0).reshape(x.shape)

    def _generate_quantum_key(self) -> str:
        """Generate a quantum-random key using measurement outcomes."""
        if self.backend is None:
            import secrets

            return secrets.token_hex(32)
        try:
            qc = QuantumCircuit(8)
            qc.h(range(8))
            qc.measure_all()
            job = self.backend.run(qc, shots=1)
            counts = job.result().get_counts()
            bits = list(counts.keys())[0].replace(" ", "")
            return hex(int(bits, 2))[2:].zfill(2)
        except Exception:
            import secrets

            return secrets.token_hex(32)

    def get_state_info(self) -> Dict:
        return {
            "num_qubits": self.num_qubits,
            "backend": "AerSimulator" if self.backend else "classical_fallback",
            "coherence_time_ms": self.coherence_time,
        }

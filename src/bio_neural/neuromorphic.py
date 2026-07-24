# src/bio_neural/neuromorphic.py
# TRANC3 Complete Spiking Neural Network — merged from DOC-07

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ============================================================
# LEAKY INTEGRATE-AND-FIRE NEURON
# ============================================================
class LIFNeuron(nn.Module):
    def __init__(
        self,
        tau_mem: float = 20.0,
        tau_syn: float = 5.0,
        v_threshold: float = 1.0,
        v_reset: float = 0.0,
    ):
        super().__init__()
        self.tau_mem = tau_mem
        self.tau_syn = tau_syn
        self.v_threshold = v_threshold
        self.v_reset = v_reset
        self.alpha = np.exp(-1.0 / tau_mem)
        self.beta = np.exp(-1.0 / tau_syn)

    def forward(
        self,
        input_current: torch.Tensor,
        membrane_potential: torch.Tensor,
        synaptic_current: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        new_syn = self.beta * synaptic_current + input_current
        new_mem = self.alpha * membrane_potential + (1 - self.alpha) * new_syn
        spikes = (new_mem >= self.v_threshold).float()
        new_mem = new_mem * (1 - spikes) + self.v_reset * spikes
        return spikes, new_mem, new_syn


# ============================================================
# SPIKING LAYER
# ============================================================
class SpikingLayer(nn.Module):
    def __init__(
        self,
        input_size: int,
        output_size: int,
        tau_mem: float = 20.0,
        tau_syn: float = 5.0,
    ):
        super().__init__()
        self.input_size = input_size
        self.output_size = output_size
        self.weights = nn.Parameter(torch.randn(input_size, output_size) * 0.1)
        self.neurons = LIFNeuron(tau_mem, tau_syn)

    def forward(
        self,
        input_spikes: torch.Tensor,
        membrane_potential: Optional[torch.Tensor] = None,
        synaptic_current: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        B = input_spikes.shape[0]
        if membrane_potential is None:
            membrane_potential = torch.zeros(B, self.output_size, device=input_spikes.device)
        if synaptic_current is None:
            synaptic_current = torch.zeros(B, self.output_size, device=input_spikes.device)
        input_current = torch.matmul(input_spikes.float(), self.weights)
        return self.neurons(input_current, membrane_potential, synaptic_current)


# ============================================================
# STDP LEARNING
# ============================================================
class STDPLearning:
    def __init__(
        self,
        tau_plus: float = 20.0,
        tau_minus: float = 20.0,
        a_plus: float = 0.01,
        a_minus: float = 0.01,
    ):
        self.tau_plus = tau_plus
        self.tau_minus = tau_minus
        self.a_plus = a_plus
        self.a_minus = a_minus

    def update_weights(
        self,
        weights: torch.Tensor,
        pre_spikes: torch.Tensor,
        post_spikes: torch.Tensor,
        dt: float = 1.0,
    ) -> torch.Tensor:
        pre_trace = pre_spikes.float()
        post_trace = post_spikes.float()
        ltp = self.a_plus * torch.outer(pre_trace.squeeze(), post_trace.squeeze())
        ltd = self.a_minus * torch.outer(pre_trace.squeeze(), post_trace.squeeze())
        dw = ltp - ltd
        return torch.clamp(weights + dw * dt, -1.0, 1.0)


# ============================================================
# FULL SPIKING NEURAL NETWORK
# ============================================================
class SpikingNeuralNetwork(nn.Module):
    def __init__(
        self,
        input_size: int = 768,
        hidden_sizes: List[int] = None,
        output_size: int = 768,
        timesteps: int = 20,
    ):
        super().__init__()
        if hidden_sizes is None:
            hidden_sizes = [512, 256]
        self.timesteps = timesteps
        sizes = [input_size] + hidden_sizes + [output_size]
        self.layers = nn.ModuleList(
            [SpikingLayer(sizes[i], sizes[i + 1]) for i in range(len(sizes) - 1)]
        )
        self.stdp = STDPLearning()
        self.spike_rates: List[float] = []
        logger.info("SNN initialised: %s", sanitize_for_log(sizes))

    def forward(self, x: torch.Tensor, use_stdp: bool = False) -> Dict[str, torch.Tensor]:
        B, T, H = x.shape
        spike_trains = self._rate_encode(x)
        states = [(None, None) for _ in self.layers]
        all_spikes = []
        layer_spike_rates = []

        for t in range(self.timesteps):
            current_input = spike_trains[:, t % T, :]
            for i, layer in enumerate(self.layers):
                mem, syn = states[i]
                spikes, new_mem, new_syn = layer(current_input, mem, syn)
                states[i] = (new_mem, new_syn)
                if use_stdp and t > 0:
                    layer.weights.data = self.stdp.update_weights(
                        layer.weights.data,
                        current_input.mean(0, keepdim=True),
                        spikes.mean(0, keepdim=True),
                    )
                current_input = spikes
            all_spikes.append(current_input)
            layer_spike_rates.append(current_input.mean().item())

        output_spikes = torch.stack(all_spikes, dim=1)
        avg_output = output_spikes.float().mean(dim=1)
        avg_rate = float(np.mean(layer_spike_rates))
        self.spike_rates.append(avg_rate)

        return {
            "output": avg_output,
            "spike_trains": output_spikes,
            "spike_rate": avg_rate,
            "energy_estimate": self._estimate_energy(layer_spike_rates),
        }

    def _rate_encode(self, x: torch.Tensor) -> torch.Tensor:
        return torch.bernoulli(torch.sigmoid(x).clamp(0, 1))

    def _estimate_energy(self, spike_rates: List[float]) -> float:
        return sum(spike_rates) * self.timesteps * 0.1  # pJ per spike

    def get_neuromorphic_stats(self) -> Dict:
        return {
            "timesteps": self.timesteps,
            "num_layers": len(self.layers),
            "avg_spike_rate": float(np.mean(self.spike_rates)) if self.spike_rates else 0.0,
            "total_neurons": sum(layer.output_size for layer in self.layers),
        }


# ============================================================
# TOP-LEVEL PROCESSOR
# ============================================================
class NeuromorphicProcessor:
    def __init__(self, config):
        # A real config object (e.g. api.py's Config()) carries an explicit
        # hidden_size, so build the SNN eagerly for that case. Callers that
        # pass a bare {} (routes.py, the MCP tool bridge) have no dimension
        # to offer yet — build lazily, sized to whatever the first real
        # input turns out to be, instead of forcing every caller to know
        # about an internal 768 default.
        self._configured_hidden_size = getattr(config, "hidden_size", None)
        self.snn: Optional[SpikingNeuralNetwork] = None
        if self._configured_hidden_size:
            self._build_snn(self._configured_hidden_size)
        self.enabled = True
        logger.info("NeuromorphicProcessor initialised")

    def _build_snn(self, hidden_size: int) -> None:
        self.snn = SpikingNeuralNetwork(
            input_size=hidden_size,
            hidden_sizes=[512, 256],
            output_size=hidden_size,
            timesteps=20,
        )

    def process(self, x: torch.Tensor, learn: bool = False) -> Dict:
        if not self.enabled:
            return {"output": x, "spike_rate": 0.0, "energy_estimate": 0.0}
        if x.dim() == 2:
            # (batch, features) -> (batch, 1 timestep, features). The SNN's
            # own `timesteps` loop runs regardless of sequence length,
            # re-using this single slice (mod T) at every internal step.
            x = x.unsqueeze(1)
        if self.snn is None:
            self._build_snn(x.shape[-1])
        try:
            return self.snn(x, use_stdp=learn)
        except Exception as e:
            logger.warning("Neuromorphic processing failed: %s", sanitize_for_log(e))
            return {"output": x, "spike_rate": 0.0, "energy_estimate": 0.0}

    def get_stats(self) -> Dict:
        return self.snn.get_neuromorphic_stats()

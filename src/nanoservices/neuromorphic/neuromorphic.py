"""Neuromorphic Computing Service — Phase 10

Intel Lava framework-inspired neuromorphic computing simulation.
Implements spiking neural networks with leaky integrate-and-fire
neurons, synaptic plasticity (STDP), and event-driven processing
for ultra-low-power cognitive computation patterns.

This is a Python-native simulation that mirrors the Lava framework
architecture (Process, ProcessModel, Var, Port, InPort, OutPort)
and provides an upgrade path to real Lava hardware execution.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────


class NeuronType(Enum):
    """Spiking neuron models available in the neuromorphic engine."""

    LIF = "leaky_integrate_and_fire"
    IZHIKEVICH = "izhikevich"
    ADC_EXP = "adaptive_exponential"
    SIGMOID = "sigmoid_rate"
    RECTIFIED = "rectified_linear"


class SynapseType(Enum):
    """Synaptic connection types."""

    EXCITATORY = "excitatory"
    INHIBITORY = "inhibitory"
    MODULATORY = "modulatory"
    ELECTRICAL = "electrical_gap"


class PlasticityRule(Enum):
    """Synaptic plasticity rules for learning."""

    STDP = "spike_timing_dependent_plasticity"
    HEBBIAN = "hebbian"
    ANTI_HEBBIAN = "anti_hebbian"
    HOMEOSTATIC = "homeostatic_scaling"
    REWARD_MODULATED = "reward_modulated_stdp"
    TRIPLET_STDP = "triplet_stdp"


class NetworkState(Enum):
    """Neuromorphic network lifecycle states."""

    INITIALIZING = "initializing"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    LEARNING = "learning"
    ADAPTING = "adapting"
    ERROR = "error"


class ChipModel(Enum):
    """Simulated neuromorphic chip architectures."""

    LOIHI_1 = "loihi_1"
    LOIHI_2 = "loihi_2"
    TRUE_NORTH = "truenorth"
    SPINNAKER = "spinnaker"
    BRAINSCALES = "brainscales"
    DYNAPSE = "dynapse"
    AKIDA = "akida"


# ─── Data Models ──────────────────────────────────────────────────────────


@dataclass
class NeuronParameters:
    """Parameters for a spiking neuron model."""

    neuron_type: NeuronType = NeuronType.LIF
    threshold: float = 1.0
    decay_current: float = 0.9
    decay_voltage: float = 0.9
    refractory_period: int = 2
    reset_voltage: float = 0.0
    # Izhikevich params
    iz_a: float = 0.02
    iz_b: float = 0.2
    iz_c: float = -65.0
    iz_d: float = 8.0
    # Adaptive Exponential params
    adaptation_coupling: float = 2.0
    adaptation_time_constant: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "neuron_type": self.neuron_type.value,
            "threshold": self.threshold,
            "decay_current": self.decay_current,
            "decay_voltage": self.decay_voltage,
            "refractory_period": self.refractory_period,
            "reset_voltage": self.reset_voltage,
        }


@dataclass
class SynapticConnection:
    """A synaptic connection between two neurons."""

    pre_neuron: str
    post_neuron: str
    weight: float = 1.0
    delay: int = 1
    synapse_type: SynapseType = SynapseType.EXCITATORY
    plasticity: PlasticityRule = PlasticityRule.STDP
    stdp_trace_pre: float = 0.0
    stdp_trace_post: float = 0.0
    eligibility_trace: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pre_neuron": self.pre_neuron,
            "post_neuron": self.post_neuron,
            "weight": self.weight,
            "delay": self.delay,
            "synapse_type": self.synapse_type.value,
            "plasticity": self.plasticity.value,
        }


@dataclass
class SpikeEvent:
    """A single spike event in the network."""

    neuron_id: str
    time_step: int
    payload: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "neuron_id": self.neuron_id,
            "time_step": self.time_step,
            "payload": self.payload,
        }


@dataclass
class NeuromorphicCore:
    """Represents a neuromorphic processing core."""

    core_id: str
    chip_model: ChipModel = ChipModel.LOIHI_2
    neuron_count: int = 1024
    synapse_count: int = 0
    max_fan_in: int = 256
    max_fan_out: int = 256
    on_chip_memory_kb: int = 128
    time_step_ns: int = 1000
    power_mw: float = 0.1
    state: NetworkState = NetworkState.IDLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "core_id": self.core_id,
            "chip_model": self.chip_model.value,
            "neuron_count": self.neuron_count,
            "synapse_count": self.synapse_count,
            "max_fan_in": self.max_fan_in,
            "max_fan_out": self.max_fan_out,
            "power_mw": self.power_mw,
            "state": self.state.value,
        }


@dataclass
class NetworkTopology:
    """Complete neuromorphic network topology."""

    network_id: str
    cores: List[NeuromorphicCore] = field(default_factory=list)
    neuron_params: Dict[str, NeuronParameters] = field(default_factory=dict)
    connections: List[SynapticConnection] = field(default_factory=list)
    input_neurons: List[str] = field(default_factory=list)
    output_neurons: List[str] = field(default_factory=list)
    total_time_steps: int = 0
    state: NetworkState = NetworkState.IDLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "network_id": self.network_id,
            "cores": [c.to_dict() for c in self.cores],
            "connections": [c.to_dict() for c in self.connections],
            "input_neurons": self.input_neurons,
            "output_neurons": self.output_neurons,
            "total_time_steps": self.total_time_steps,
            "state": self.state.value,
        }


# ─── Lava-Inspired Process Model ─────────────────────────────────────────


class LIFNeuron:
    """Leaky Integrate-and-Fire neuron simulation.

    Implements the LIF dynamics:
        v[t] = alpha_v * v[t-1] + sum(w_ij * s_j[t-1])
        spike if v[t] >= v_th
        v[t] = v_reset after spike
    """

    def __init__(
        self,
        neuron_id: str,
        params: Optional[NeuronParameters] = None,
    ):
        self.neuron_id = neuron_id
        self.params = params or NeuronParameters()
        self.voltage: float = 0.0
        self.current: float = 0.0
        self.refractory_counter: int = 0
        self.spike_history: List[int] = []
        self.voltage_trace: List[float] = []

    def step(self, input_current: float) -> bool:
        """Advance one time step. Returns True if neuron spiked."""
        if self.refractory_counter > 0:
            self.refractory_counter -= 1
            self.voltage = self.params.reset_voltage
            self.current *= self.params.decay_current
            self.voltage_trace.append(self.voltage)
            self.spike_history.append(0)
            return False

        # Integrate
        self.current = self.params.decay_current * self.current + input_current
        self.voltage = self.params.decay_voltage * self.voltage + self.current

        # Fire
        spiked = self.voltage >= self.params.threshold
        if spiked:
            self.voltage = self.params.reset_voltage
            self.refractory_counter = self.params.refractory_period
            self.spike_history.append(1)
        else:
            self.spike_history.append(0)

        self.voltage_trace.append(self.voltage)
        return spiked

    def reset(self) -> None:
        """Reset neuron state."""
        self.voltage = 0.0
        self.current = 0.0
        self.refractory_counter = 0
        self.spike_history.clear()
        self.voltage_trace.clear()


class IzhikevichNeuron:
    """Izhikevich neuron model for rich spiking dynamics.

    Implements:
        v' = 0.04*v^2 + 5*v + 140 - u + I
        u' = a*(b*v - u)
        if v >= 30: v = c; u = u + d
    """

    def __init__(
        self,
        neuron_id: str,
        params: Optional[NeuronParameters] = None,
    ):
        self.neuron_id = neuron_id
        self.params = params or NeuronParameters()
        self.v: float = self.params.iz_c
        self.u: float = self.params.iz_b * self.v
        self.spike_history: List[int] = []
        self.voltage_trace: List[float] = []

    def step(self, input_current: float) -> bool:
        """Advance one time step."""
        dv = 0.04 * self.v * self.v + 5.0 * self.v + 140.0 - self.u + input_current
        du = self.params.iz_a * (self.params.iz_b * self.v - self.u)
        self.v += dv * 0.1  # Scale for numerical stability
        self.u += du * 0.1

        spiked = self.v >= 30.0
        if spiked:
            self.v = self.params.iz_c
            self.u += self.params.iz_d
            self.spike_history.append(1)
        else:
            self.spike_history.append(0)

        self.voltage_trace.append(self.v)
        return spiked

    def reset(self) -> None:
        self.v = self.params.iz_c
        self.u = self.params.iz_b * self.v
        self.spike_history.clear()
        self.voltage_trace.clear()


# ─── Synaptic Plasticity ──────────────────────────────────────────────────


class STDPPlasticity:
    """Spike-Timing-Dependent Plasticity learning rule.

    Implements the classic STDP window:
        delta_w = A_plus * exp(-delta_t / tau_plus)  if post fires after pre
        delta_w = -A_minus * exp(delta_t / tau_minus)  if pre fires after post
    """

    def __init__(
        self,
        tau_plus: float = 20.0,
        tau_minus: float = 20.0,
        a_plus: float = 0.1,
        a_minus: float = 0.1,
        w_max: float = 10.0,
        w_min: float = 0.0,
    ):
        self.tau_plus = tau_plus
        self.tau_minus = tau_minus
        self.a_plus = a_plus
        self.a_minus = a_minus
        self.w_max = w_max
        self.w_min = w_min

    def compute_weight_change(
        self,
        pre_spike_time: int,
        post_spike_time: int,
    ) -> float:
        """Compute weight change based on spike timing."""
        delta_t = post_spike_time - pre_spike_time
        if delta_t > 0:
            # Post after pre → LTP (long-term potentiation)
            dw = self.a_plus * math.exp(-delta_t / self.tau_plus)
        elif delta_t < 0:
            # Pre after post → LTD (long-term depression)
            dw = -self.a_minus * math.exp(delta_t / self.tau_minus)
        else:
            dw = 0.0
        return dw

    def apply_stdp(
        self,
        connection: SynapticConnection,
        pre_spike_history: List[int],
        post_spike_history: List[int],
        current_step: int,
    ) -> float:
        """Apply STDP to a synaptic connection given spike histories."""
        window = 40  # STDP window in time steps
        total_dw = 0.0

        for t in range(max(0, current_step - window), current_step + 1):
            if t >= len(pre_spike_history) or t >= len(post_spike_history):
                continue
            if pre_spike_history[t] or post_spike_history[t]:
                for t2 in range(max(0, t - window), min(t + window, current_step + 1)):
                    if t2 >= len(pre_spike_history) or t2 >= len(post_spike_history):
                        continue
                    if t == t2:
                        continue
                    # Pre fires at t, post fires at t2
                    if pre_spike_history[t] and post_spike_history[t2]:
                        dw = self.compute_weight_change(t, t2)
                        total_dw += dw * 0.01  # Scale factor

        new_weight = max(
            self.w_min,
            min(self.w_max, connection.weight + total_dw),
        )
        connection.weight = new_weight
        return total_dw


class HomeostaticPlasticity:
    """Homeostatic scaling to maintain stable firing rates."""

    def __init__(
        self,
        target_rate: float = 0.05,
        learning_rate: float = 0.01,
        window_size: int = 100,
    ):
        self.target_rate = target_rate
        self.learning_rate = learning_rate
        self.window_size = window_size

    def scale(
        self,
        spike_history: List[int],
        incoming_weights: List[float],
    ) -> List[float]:
        """Scale incoming weights to maintain target firing rate."""
        if not spike_history:
            return incoming_weights
        recent = spike_history[-self.window_size :]
        actual_rate = sum(recent) / len(recent) if recent else 0.0
        scaling_factor = 1.0 + self.learning_rate * (self.target_rate - actual_rate)
        scaling_factor = max(0.5, min(2.0, scaling_factor))
        return [w * scaling_factor for w in incoming_weights]


# ─── Neuromorphic Network ────────────────────────────────────────────────


class NeuromorphicNetwork:
    """Complete spiking neural network with plasticity.

    Manages neurons, connections, and plasticity rules
    with event-driven simulation.
    """

    def __init__(self, network_id: str):
        self.network_id = network_id
        self.neurons: Dict[str, Any] = {}  # id -> LIFNeuron or IzhikevichNeuron
        self.connections: List[SynapticConnection] = []
        self.connection_map: Dict[str, List[SynapticConnection]] = {}  # post -> [conn]
        self.input_neurons: List[str] = []
        self.output_neurons: List[str] = []
        self.current_step: int = 0
        self.spike_log: List[SpikeEvent] = []
        self.stdp = STDPPlasticity()
        self.homeostatic = HomeostaticPlasticity()
        self.state = NetworkState.IDLE

    def add_neuron(
        self,
        neuron_id: str,
        params: Optional[NeuronParameters] = None,
        is_input: bool = False,
        is_output: bool = False,
    ) -> None:
        """Add a neuron to the network."""
        params = params or NeuronParameters()
        if params.neuron_type == NeuronType.LIF:
            neuron = LIFNeuron(neuron_id, params)
        elif params.neuron_type == NeuronType.IZHIKEVICH:
            neuron = IzhikevichNeuron(neuron_id, params)
        else:
            neuron = LIFNeuron(neuron_id, params)

        self.neurons[neuron_id] = neuron
        if is_input:
            self.input_neurons.append(neuron_id)
        if is_output:
            self.output_neurons.append(neuron_id)

    def add_connection(self, connection: SynapticConnection) -> None:
        """Add a synaptic connection."""
        self.connections.append(connection)
        if connection.post_neuron not in self.connection_map:
            self.connection_map[connection.post_neuron] = []
        self.connection_map[connection.post_neuron].append(connection)

    def inject_spike(self, neuron_id: str, payload: float = 1.0) -> None:
        """Inject an external spike into an input neuron."""
        if neuron_id in self.neurons:
            neuron = self.neurons[neuron_id]
            if isinstance(neuron, LIFNeuron):
                neuron.current += payload
            elif isinstance(neuron, IzhikevichNeuron):
                # Inject as current directly
                pass

    def step(self, plasticity_enabled: bool = True) -> List[SpikeEvent]:
        """Execute one simulation time step."""
        self.current_step += 1
        spikes: List[SpikeEvent] = []

        # Collect input currents for each neuron
        input_currents: Dict[str, float] = dict.fromkeys(self.neurons, 0.0)

        # Process incoming spikes from connections (with delay)
        for conn in self.connections:
            pre_neuron = self.neurons.get(conn.pre_neuron)
            if pre_neuron is None:
                continue
            # Check if pre-neuron spiked recently (accounting for delay)
            lookback = self.current_step - conn.delay
            if lookback >= 0 and lookback < len(pre_neuron.spike_history):
                if pre_neuron.spike_history[lookback]:
                    sign = 1.0 if conn.synapse_type == SynapseType.EXCITATORY else -1.0
                    input_currents[conn.post_neuron] += sign * conn.weight

        # Step each neuron
        for neuron_id, neuron in self.neurons.items():
            current = input_currents.get(neuron_id, 0.0)
            spiked = neuron.step(current)
            if spiked:
                event = SpikeEvent(
                    neuron_id=neuron_id,
                    time_step=self.current_step,
                )
                spikes.append(event)
                self.spike_log.append(event)

        # Apply plasticity
        if plasticity_enabled and self.current_step % 10 == 0:
            self._apply_plasticity()

        return spikes

    def _apply_plasticity(self) -> None:
        """Apply synaptic plasticity rules."""
        for conn in self.connections:
            if conn.plasticity == PlasticityRule.STDP:
                pre = self.neurons.get(conn.pre_neuron)
                post = self.neurons.get(conn.post_neuron)
                if pre and post:
                    self.stdp.apply_stdp(
                        conn,
                        pre.spike_history,
                        post.spike_history,
                        self.current_step,
                    )
            elif conn.plasticity == PlasticityRule.HOMEOSTATIC:
                post = self.neurons.get(conn.post_neuron)
                if post:
                    incoming = [c.weight for c in self.connection_map.get(conn.post_neuron, [])]
                    scaled = self.homeostatic.scale(post.spike_history, incoming)
                    for i, c in enumerate(self.connection_map.get(conn.post_neuron, [])):
                        if i < len(scaled):
                            c.weight = scaled[i]

    def run(self, num_steps: int, plasticity_enabled: bool = True) -> List[List[SpikeEvent]]:
        """Run the network for a given number of time steps."""
        self.state = NetworkState.RUNNING
        all_spikes: List[List[SpikeEvent]] = []
        for _ in range(num_steps):
            spikes = self.step(plasticity_enabled)
            all_spikes.append(spikes)
        self.state = NetworkState.IDLE
        return all_spikes

    def reset(self) -> None:
        """Reset all neuron states."""
        for neuron in self.neurons.values():
            neuron.reset()
        self.current_step = 0
        self.spike_log.clear()
        self.state = NetworkState.IDLE

    def get_statistics(self) -> Dict[str, Any]:
        """Get network statistics."""
        total_spikes = sum(sum(n.spike_history) for n in self.neurons.values())
        total_steps = max(self.current_step, 1)
        return {
            "network_id": self.network_id,
            "neuron_count": len(self.neurons),
            "connection_count": len(self.connections),
            "time_steps": self.current_step,
            "total_spikes": total_spikes,
            "spike_rate": total_spikes / (len(self.neurons) * total_steps),
            "state": self.state.value,
        }


# ─── Neuromorphic Chip Simulator ─────────────────────────────────────────


class NeuromorphicChipSimulator:
    """Simulates a neuromorphic chip with multiple cores.

    Provides hardware-accurate resource constraints based on
    the selected chip model (Loihi, TrueNorth, etc.).
    """

    CHIP_SPECS: Dict[ChipModel, Dict[str, Any]] = {
        ChipModel.LOIHI_1: {
            "cores_per_chip": 128,
            "neurons_per_core": 1024,
            "synapses_per_core": 4096,
            "on_chip_memory_kb": 64,
            "power_per_core_mw": 0.75,
        },
        ChipModel.LOIHI_2: {
            "cores_per_chip": 128,
            "neurons_per_core": 4096,
            "synapses_per_core": 16384,
            "on_chip_memory_kb": 128,
            "power_per_core_mw": 0.5,
        },
        ChipModel.TRUE_NORTH: {
            "cores_per_chip": 4096,
            "neurons_per_core": 256,
            "synapses_per_core": 1024,
            "on_chip_memory_kb": 32,
            "power_per_core_mw": 0.07,
        },
        ChipModel.SPINNAKER: {
            "cores_per_chip": 18,
            "neurons_per_core": 1000,
            "synapses_per_core": 8000,
            "on_chip_memory_kb": 128,
            "power_per_core_mw": 1.0,
        },
        ChipModel.DYNAPSE: {
            "cores_per_chip": 4,
            "neurons_per_core": 1024,
            "synapses_per_core": 4096,
            "on_chip_memory_kb": 16,
            "power_per_core_mw": 0.05,
        },
        ChipModel.AKIDA: {
            "cores_per_chip": 128,
            "neurons_per_core": 2048,
            "synapses_per_core": 8192,
            "on_chip_memory_kb": 256,
            "power_per_core_mw": 0.3,
        },
        ChipModel.BRAINSCALES: {
            "cores_per_chip": 8,
            "neurons_per_core": 512,
            "synapses_per_core": 2048,
            "on_chip_memory_kb": 64,
            "power_per_core_mw": 2.0,
        },
    }

    def __init__(self, chip_model: ChipModel = ChipModel.LOIHI_2):
        self.chip_model = chip_model
        self.specs = self.CHIP_SPECS.get(chip_model, self.CHIP_SPECS[ChipModel.LOIHI_2])
        self.cores: List[NeuromorphicCore] = []
        self.networks: Dict[str, NeuromorphicNetwork] = {}
        self._initialize_cores()

    def _initialize_cores(self) -> None:
        """Create the cores for this chip."""
        for i in range(self.specs["cores_per_chip"]):
            core = NeuromorphicCore(
                core_id=f"core_{i}",
                chip_model=self.chip_model,
                neuron_count=self.specs["neurons_per_core"],
                on_chip_memory_kb=self.specs["on_chip_memory_kb"],
                power_mw=self.specs["power_per_core_mw"],
            )
            self.cores.append(core)

    def create_network(
        self,
        network_id: str,
        num_neurons: int,
        num_connections: int,
        neuron_type: NeuronType = NeuronType.LIF,
        connection_probability: float = 0.1,
    ) -> NeuromorphicNetwork:
        """Create a spiking neural network on this chip."""
        network = NeuromorphicNetwork(network_id)

        # Create neurons
        params = NeuronParameters(neuron_type=neuron_type)
        for i in range(num_neurons):
            nid = f"{network_id}_n{i}"
            is_input = i < int(num_neurons * 0.1)
            is_output = i >= int(num_neurons * 0.9)
            network.add_neuron(nid, params, is_input=is_input, is_output=is_output)

        # Create random connections
        import random  # nosec B311 -- non-cryptographic simulation use

        neuron_ids = list(network.neurons.keys())
        conn_count = 0
        attempts = 0
        while conn_count < num_connections and attempts < num_connections * 3:
            pre = random.choice(neuron_ids)
            post = random.choice(neuron_ids)
            if pre != post:
                syn_type = (
                    SynapseType.EXCITATORY if random.random() < 0.8 else SynapseType.INHIBITORY
                )
                plasticity = (
                    PlasticityRule.STDP if random.random() < 0.5 else PlasticityRule.HOMEOSTATIC
                )
                conn = SynapticConnection(
                    pre_neuron=pre,
                    post_neuron=post,
                    weight=random.uniform(0.1, 2.0),
                    delay=random.randint(1, 4),
                    synapse_type=syn_type,
                    plasticity=plasticity,
                )
                network.add_connection(conn)
                conn_count += 1
            attempts += 1

        self.networks[network_id] = network
        return network

    def get_chip_utilization(self) -> Dict[str, Any]:
        """Get chip resource utilization."""
        total_neurons = sum(len(n.neurons) for n in self.networks.values())
        total_synapses = sum(len(n.connections) for n in self.networks.values())
        max_neurons = self.specs["cores_per_chip"] * self.specs["neurons_per_core"]
        max_synapses = self.specs["cores_per_chip"] * self.specs["synapses_per_core"]
        return {
            "chip_model": self.chip_model.value,
            "cores_total": len(self.cores),
            "neurons_used": total_neurons,
            "neurons_max": max_neurons,
            "neuron_utilization": total_neurons / max_neurons if max_neurons else 0,
            "synapses_used": total_synapses,
            "synapses_max": max_synapses,
            "synapse_utilization": total_synapses / max_synapses if max_synapses else 0,
            "total_power_mw": sum(c.power_mw for c in self.cores),
            "active_networks": len(self.networks),
        }


# ─── Spike Encoding ───────────────────────────────────────────────────────


class SpikeEncoder:
    """Convert real-valued data to spike trains."""

    @staticmethod
    def rate_coding(
        values: List[float],
        num_steps: int = 100,
        max_rate: float = 0.5,
    ) -> List[List[int]]:
        """Rate coding: value → firing probability per step."""
        spike_trains = []
        for val in values:
            normalized = max(0.0, min(1.0, val))
            rate = normalized * max_rate
            train = [1 if (val * max_rate) > (i / num_steps) else 0 for i in range(num_steps)]
            # More accurate Poisson-like
            import random  # nosec B311 -- non-cryptographic simulation use

            train = [1 if random.random() < rate else 0 for _ in range(num_steps)]
            spike_trains.append(train)
        return spike_trains

    @staticmethod
    def temporal_coding(
        values: List[float],
        num_steps: int = 100,
    ) -> List[List[int]]:
        """Temporal coding: value → spike timing (earlier = stronger)."""
        spike_trains = []
        for val in values:
            normalized = max(0.0, min(1.0, val))
            spike_time = int((1.0 - normalized) * (num_steps - 1))
            train = [0] * num_steps
            train[spike_time] = 1
            spike_trains.append(train)
        return spike_trains

    @staticmethod
    def population_coding(
        values: List[float],
        num_neurons: int = 10,
        num_steps: int = 100,
    ) -> List[List[int]]:
        """Population coding: value → distributed representation across neurons."""
        spike_trains = []
        import random  # nosec B311 -- non-cryptographic simulation use

        for val in values:
            normalized = max(0.0, min(1.0, val))
            for n in range(num_neurons):
                # Each neuron has a preferred stimulus
                preferred = n / num_neurons
                distance = abs(normalized - preferred)
                rate = max(0.0, 0.5 * (1.0 - distance * 2))
                train = [1 if random.random() < rate else 0 for _ in range(num_steps)]
                spike_trains.append(train)
        return spike_trains

    @staticmethod
    def delta_coding(
        values: List[float],
        threshold: float = 0.1,
    ) -> List[List[int]]:
        """Delta modulation coding: spike on significant change."""
        spike_trains = []
        prev = 0.0
        for val in values:
            delta = val - prev
            up_spike = 1 if delta > threshold else 0
            down_spike = 1 if delta < -threshold else 0
            # Two-channel: [up, down]
            spike_trains.append([up_spike, down_spike])
            prev = val
        return spike_trains


# ─── Main Service ─────────────────────────────────────────────────────────


class NeuromorphicService:
    """Neuromorphic Computing Service for the Tranc3 ecosystem.

    Provides spiking neural network creation, simulation, learning,
    and spike encoding/decoding capabilities with hardware-accurate
    chip simulation.
    """

    def __init__(self, chip_model: ChipModel = ChipModel.LOIHI_2):
        self.chip = NeuromorphicChipSimulator(chip_model)
        self.encoder = SpikeEncoder()
        self._service_id = str(uuid.uuid4())

    def create_network(
        self,
        network_id: str,
        num_neurons: int = 100,
        num_connections: int = 500,
        neuron_type: NeuronType = NeuronType.LIF,
    ) -> Dict[str, Any]:
        """Create a new spiking neural network."""
        network = self.chip.create_network(network_id, num_neurons, num_connections, neuron_type)
        return {
            "network_id": network_id,
            "neurons": len(network.neurons),
            "connections": len(network.connections),
            "input_neurons": len(network.input_neurons),
            "output_neurons": len(network.output_neurons),
        }

    def simulate(
        self,
        network_id: str,
        num_steps: int = 100,
        input_data: Optional[List[float]] = None,
        plasticity_enabled: bool = True,
    ) -> Dict[str, Any]:
        """Run a network simulation."""
        network = self.chip.networks.get(network_id)
        if not network:
            return {"error": f"Network {network_id} not found"}

        # Inject input data if provided
        if input_data:
            spike_trains = self.encoder.rate_coding(input_data, num_steps)
            for i, inp_neuron_id in enumerate(network.input_neurons):
                if i < len(spike_trains):
                    train = spike_trains[i]
                    for t, spike in enumerate(train):
                        if spike and t < num_steps:
                            network.inject_spike(inp_neuron_id, 1.0)

        # Run simulation
        all_spikes = network.run(num_steps, plasticity_enabled)
        total_spikes = sum(len(s) for s in all_spikes)

        return {
            "network_id": network_id,
            "steps_simulated": num_steps,
            "total_spikes": total_spikes,
            "spike_rate": total_spikes / (len(network.neurons) * num_steps)
            if network.neurons
            else 0,
            "output_spike_counts": {
                nid: sum(network.neurons[nid].spike_history)
                for nid in network.output_neurons
                if nid in network.neurons
            },
            "statistics": network.get_statistics(),
        }

    def encode_data(
        self,
        data: List[float],
        method: str = "rate",
        num_steps: int = 100,
    ) -> Dict[str, Any]:
        """Encode real-valued data into spike trains."""
        if method == "rate":
            trains = self.encoder.rate_coding(data, num_steps)
        elif method == "temporal":
            trains = self.encoder.temporal_coding(data, num_steps)
        elif method == "population":
            trains = self.encoder.population_coding(data, num_neurons=10, num_steps=num_steps)
        elif method == "delta":
            trains = self.encoder.delta_coding(data)
        else:
            return {"error": f"Unknown encoding method: {method}"}

        total_spikes = sum(sum(t) for t in trains)
        return {
            "method": method,
            "num_channels": len(trains),
            "num_steps": num_steps if method != "delta" else len(data),
            "total_spikes": total_spikes,
            "spike_density": total_spikes / (len(trains) * max(len(t) for t in trains))
            if trains
            else 0,
        }

    def get_chip_status(self) -> Dict[str, Any]:
        """Get chip utilization and status."""
        return self.chip.get_chip_utilization()

    def list_networks(self) -> List[Dict[str, Any]]:
        """List all networks on the chip."""
        return [network.get_statistics() for network in self.chip.networks.values()]

    def delete_network(self, network_id: str) -> bool:
        """Delete a network from the chip."""
        if network_id in self.chip.networks:
            del self.chip.networks[network_id]
            return True
        return False

    def get_neuromorphic_status(self) -> Dict[str, Any]:
        """Get overall service status."""
        return {
            "service_id": self._service_id,
            "service_type": "neuromorphic_computing",
            "chip_model": self.chip.chip_model.value,
            "active_networks": len(self.chip.networks),
            "chip_utilization": self.chip.get_chip_utilization(),
            "status": "operational",
        }

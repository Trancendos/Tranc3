"""Bio-Digital Neural Interface — Phase 10.5

Brian2-inspired spiking neural network simulation for bio-digital
neural interfacing. Implements biologically plausible neuron models,
synaptic dynamics, neural plasticity, and brain-computer interface
simulation patterns.

This module provides a Python-native simulation of bio-digital
neural interfaces with spike-based communication, neural encoding
strategies, and adaptive signal processing for bridging biological
and digital computation.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────

class BioNeuronType(Enum):
    """Biologically-inspired neuron types."""
    PYRAMIDAL = "pyramidal"
    INTERNEURON = "interneuron"
    PURKINJE = "purkinje"
    MOTOR = "motor"
    SENSORY = "sensory"
    DOPAMINERGIC = "dopaminergic"
    CHOLINERGIC = "cholinergic"


class ReceptorType(Enum):
    """Neurotransmitter receptor types."""
    AMPA = "ampa"
    NMDA = "nmda"
    GABA_A = "gaba_a"
    GABA_B = "gaba_b"
    NICOTINIC = "nicotinic"
    MUSCARINIC = "muscarinic"
    D1 = "dopamine_d1"
    D2 = "dopamine_d2"


class BCIState(Enum):
    """Brain-computer interface states."""
    DISCONNECTED = "disconnected"
    CALIBRATING = "calibrating"
    CONNECTED = "connected"
    STREAMING = "streaming"
    FEEDBACK = "feedback"
    ERROR = "error"


class NeuralModulation(Enum):
    """Neuromodulatory systems."""
    DOPAMINE = "dopamine"
    SEROTONIN = "serotonin"
    NORADRENALINE = "noradrenaline"
    ACETYLCHOLINE = "acetylcholine"
    GABA = "gaba"
    GLUTAMATE = "glutamate"


class InterfaceMode(Enum):
    """Bio-digital interface modes."""
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    BIDIRECTIONAL = "bidirectional"
    FEEDBACK_LOOP = "feedback_loop"
    ADAPTIVE = "adaptive"


# ─── Data Models ──────────────────────────────────────────────────────────

@dataclass
class BioNeuronParams:
    """Parameters for a bio-realistic neuron."""
    neuron_type: BioNeuronType = BioNeuronType.PYRAMIDAL
    membrane_resistance: float = 100.0  # MOhm
    membrane_capacitance: float = 200.0  # pF
    resting_potential: float = -70.0  # mV
    threshold_potential: float = -55.0  # mV
    reset_potential: float = -80.0  # mV
    refractory_period: float = 2.0  # ms
    tau_syn_exc: float = 5.0  # ms (excitatory synaptic time constant)
    tau_syn_inh: float = 10.0  # ms (inhibitory synaptic time constant)
    adaptation_rate: float = 0.01  # Spike-frequency adaptation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "neuron_type": self.neuron_type.value,
            "resting_potential": self.resting_potential,
            "threshold_potential": self.threshold_potential,
            "refractory_period": self.refractory_period,
        }


@dataclass
class SynapticReceptor:
    """A synaptic receptor with neurotransmitter dynamics."""
    receptor_type: ReceptorType
    conductance: float = 1.0  # nS
    reversal_potential: float = 0.0  # mV
    decay_tau: float = 5.0  # ms
    rise_tau: float = 0.5  # ms
    utilization: float = 0.5  # Release probability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receptor_type": self.receptor_type.value,
            "conductance": self.conductance,
            "reversal_potential": self.reversal_potential,
            "decay_tau": self.decay_tau,
        }


@dataclass
class NeuralSignal:
    """A neural signal with temporal dynamics."""
    signal_id: str
    source_neuron: str
    signal_type: str  # "spike", "lfp", "eeg", "ecog"
    amplitude: float = 1.0
    timestamp_ms: float = 0.0
    frequency_hz: float = 0.0
    phase: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "source_neuron": self.source_neuron,
            "signal_type": self.signal_type,
            "amplitude": self.amplitude,
            "timestamp_ms": self.timestamp_ms,
            "frequency_hz": self.frequency_hz,
        }


@dataclass
class BCISession:
    """A brain-computer interface session."""
    session_id: str
    interface_mode: InterfaceMode = InterfaceMode.BIDIRECTIONAL
    state: BCIState = BCIState.DISCONNECTED
    num_channels: int = 64
    sampling_rate_hz: float = 1000.0
    signals_read: int = 0
    signals_written: int = 0
    calibration_score: float = 0.0
    latency_ms: float = 5.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "interface_mode": self.interface_mode.value,
            "state": self.state.value,
            "num_channels": self.num_channels,
            "sampling_rate_hz": self.sampling_rate_hz,
            "signals_read": self.signals_read,
            "signals_written": self.signals_written,
            "calibration_score": self.calibration_score,
            "latency_ms": self.latency_ms,
        }


# ─── Bio-Digital Neuron Simulation ───────────────────────────────────────

class BioDigitalNeuron:
    """Bio-realistic neuron with conductance-based synapses.

    Implements the conductance-based model:
        C_m * dV/dt = g_L * (E_L - V) + g_exc * (E_exc - V) + g_inh * (E_inh - V) + I_ext
    """

    def __init__(
        self,
        neuron_id: str,
        params: Optional[BioNeuronParams] = None,
    ):
        self.neuron_id = neuron_id
        self.params = params or BioNeuronParams()
        self.voltage: float = self.params.resting_potential
        self.g_exc: float = 0.0  # Excitatory conductance
        self.g_inh: float = 0.0  # Inhibitory conductance
        self.adaptation_current: float = 0.0
        self.refractory_remaining: float = 0.0
        self.spike_times: List[float] = []
        self.voltage_trace: List[float] = []
        self.receptors: List[SynapticReceptor] = []

    def add_receptor(self, receptor: SynapticReceptor) -> None:
        """Add a synaptic receptor to this neuron."""
        self.receptors.append(receptor)

    def step(self, dt: float, input_current: float = 0.0) -> bool:
        """Advance by dt milliseconds. Returns True if spiked."""
        if self.refractory_remaining > 0:
            self.refractory_remaining -= dt
            self.voltage = self.params.reset_potential
            self._decay_conductances(dt)
            self.voltage_trace.append(self.voltage)
            return False

        # Membrane dynamics
        g_leak = 1.0 / self.params.membrane_resistance
        e_exc = 0.0  # Reversal potential for excitation
        e_inh = -80.0  # Reversal potential for inhibition
        e_leak = self.params.resting_potential

        dV = (
            g_leak * (e_leak - self.voltage)
            + self.g_exc * (e_exc - self.voltage)
            + self.g_inh * (e_inh - self.voltage)
            - self.adaptation_current
            + input_current
        ) / self.params.membrane_capacitance

        self.voltage += dV * dt

        # Spike check
        spiked = self.voltage >= self.params.threshold_potential
        if spiked:
            self.voltage = self.params.reset_potential
            self.refractory_remaining = self.params.refractory_period
            self.adaptation_current += self.params.adaptation_rate
            self.spike_times.append(len(self.voltage_trace) * dt)

        # Decay conductances
        self._decay_conductances(dt)
        # Adaptation decay
        self.adaptation_current *= 0.99

        self.voltage_trace.append(self.voltage)
        return spiked

    def _decay_conductances(self, dt: float) -> None:
        """Decay synaptic conductances."""
        tau_exc = self.params.tau_syn_exc
        tau_inh = self.params.tau_syn_inh
        self.g_exc *= math.exp(-dt / tau_exc)
        self.g_inh *= math.exp(-dt / tau_inh)

    def receive_excitatory(self, conductance: float) -> None:
        """Receive excitatory input."""
        self.g_exc += conductance

    def receive_inhibitory(self, conductance: float) -> None:
        """Receive inhibitory input."""
        self.g_inh += conductance


# ─── Neural Oscillator ────────────────────────────────────────────────────

class NeuralOscillator:
    """Simulates neural oscillations (brain rhythms).

    Supports generation of alpha, beta, gamma, theta, and delta
    rhythms with realistic frequency, amplitude, and phase dynamics.
    """

    RHYTHM_PARAMS: Dict[str, Dict[str, float]] = {
        "delta": {"freq": 2.0, "amplitude": 100.0, "phase_noise": 0.1},
        "theta": {"freq": 6.0, "amplitude": 50.0, "phase_noise": 0.15},
        "alpha": {"freq": 10.0, "amplitude": 30.0, "phase_noise": 0.1},
        "beta": {"freq": 20.0, "amplitude": 15.0, "phase_noise": 0.2},
        "gamma": {"freq": 40.0, "amplitude": 5.0, "phase_noise": 0.3},
    }

    def __init__(self, rhythm: str = "alpha"):
        params = self.RHYTHM_PARAMS.get(rhythm, self.RHYTHM_PARAMS["alpha"])
        self.rhythm = rhythm
        self.frequency = params["freq"]
        self.amplitude = params["amplitude"]
        self.phase_noise = params["phase_noise"]
        self.phase: float = 0.0
        self.noise_state: float = 0.0

    def step(self, dt: float) -> float:
        """Generate one sample of the oscillation."""
        self.phase += 2.0 * math.pi * self.frequency * dt / 1000.0
        # Add 1/f noise for realism
        self.noise_state += (hash(str(self.phase)) % 100 - 50) * 0.001
        self.noise_state *= 0.99
        signal = self.amplitude * math.sin(self.phase + self.noise_state)
        return signal

    def generate_eeg(self, duration_ms: float, sampling_rate: float = 250.0) -> List[float]:
        """Generate an EEG-like signal for the given duration."""
        num_samples = int(duration_ms * sampling_rate / 1000.0)
        dt = 1000.0 / sampling_rate
        return [self.step(dt) for _ in range(num_samples)]


# ─── Brain-Computer Interface ─────────────────────────────────────────────

class BrainComputerInterface:
    """Simulated brain-computer interface with signal processing.

    Implements signal acquisition, feature extraction, classification,
    and feedback generation for BCI paradigms.
    """

    def __init__(self, num_channels: int = 64, sampling_rate: float = 1000.0):
        self.num_channels = num_channels
        self.sampling_rate = sampling_rate
        self.session: Optional[BCISession] = None
        self.signal_buffer: List[List[float]] = [[] for _ in range(num_channels)]
        self.buffer_size = int(sampling_rate * 2)  # 2-second buffer
        self.feature_extractors: Dict[str, Any] = {}
        self.classifier_weights: Dict[str, List[float]] = {}
        self.calibration_data: List[Dict[str, Any]] = []

    def connect(self, session_id: Optional[str] = None) -> BCISession:
        """Establish a BCI session."""
        sid = session_id or str(uuid.uuid4())
        self.session = BCISession(
            session_id=sid,
            state=BCIState.CALIBRATING,
        )
        return self.session

    def calibrate(self, num_trials: int = 10) -> Dict[str, Any]:
        """Run calibration to tune signal processing."""
        if not self.session:
            return {"error": "No active session"}

        # Simulate calibration by generating synthetic data
        scores = []
        for trial in range(num_trials):
            # Generate calibration signal
            score = 0.5 + 0.5 * (1.0 - math.exp(-trial / 3.0))
            scores.append(score)

        avg_score = sum(scores) / len(scores)
        self.session.calibration_score = avg_score
        if avg_score > 0.6:
            self.session.state = BCIState.CONNECTED

        return {
            "calibration_score": avg_score,
            "num_trials": num_trials,
            "state": self.session.state.value,
            "ready": avg_score > 0.6,
        }

    def read_signals(self, duration_ms: float = 1000.0) -> Dict[str, Any]:
        """Read neural signals from the interface."""
        if not self.session or self.session.state == BCIState.DISCONNECTED:
            return {"error": "Not connected"}

        # Simulate signal acquisition
        import random
        signals = []
        for ch in range(self.num_channels):
            # Generate synthetic neural signal
            noise = [random.gauss(0, 1) for _ in range(int(self.sampling_rate * duration_ms / 1000))]
            # Add some oscillatory components
            for i, _ in enumerate(noise):
                t = i / self.sampling_rate
                noise[i] += 10.0 * math.sin(2 * math.pi * 10 * t)  # Alpha
                noise[i] += 5.0 * math.sin(2 * math.pi * 20 * t)   # Beta
            signals.append(noise)

        self.session.signals_read += 1
        self.session.state = BCIState.STREAMING

        return {
            "session_id": self.session.session_id,
            "channels": self.num_channels,
            "duration_ms": duration_ms,
            "sampling_rate": self.sampling_rate,
            "signal_power": sum(sum(s ** 2 for s in ch) / len(ch) for ch in signals) / self.num_channels,
        }

    def write_stimulation(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """Write stimulation pattern to the interface."""
        if not self.session:
            return {"error": "No active session"}

        stim_type = pattern.get("type", "single_pulse")
        amplitude = pattern.get("amplitude", 1.0)
        frequency = pattern.get("frequency", 10.0)
        duration_ms = pattern.get("duration_ms", 100.0)
        target_channels = pattern.get("channels", list(range(min(8, self.num_channels))))

        self.session.signals_written += 1

        return {
            "stimulation_applied": True,
            "type": stim_type,
            "amplitude": amplitude,
            "frequency": frequency,
            "duration_ms": duration_ms,
            "channels_stimulated": len(target_channels),
        }

    def extract_features(self, signals: List[List[float]]) -> Dict[str, Any]:
        """Extract features from neural signals."""
        features: Dict[str, List[float]] = {}

        # Band power features
        for band_name, (low, high) in [
            ("delta", (1, 4)), ("theta", (4, 8)), ("alpha", (8, 13)),
            ("beta", (13, 30)), ("gamma", (30, 100)),
        ]:
            powers = []
            for ch in signals:
                # Simplified band power estimation
                n = len(ch)
                power = sum(
                    x * x for x in ch[int(n * low / 250):int(n * high / 250)]
                ) / max(1, n * (high - low) / 250)
                powers.append(power)
            features[f"{band_name}_power"] = [sum(powers) / len(powers)]

        # Time-domain features
        for ch in signals[:1]:  # Just first channel
            features["variance"] = [sum(x * x for x in ch) / len(ch)]
            features["mean"] = [sum(ch) / len(ch)]

        return features

    def disconnect(self) -> Dict[str, Any]:
        """End the BCI session."""
        if self.session:
            result = self.session.to_dict()
            self.session = None
            return {"disconnected": True, "session": result}
        return {"disconnected": False, "error": "No active session"}


# ─── Main Service ─────────────────────────────────────────────────────────

class BioDigitalInterfaceService:
    """Bio-Digital Neural Interface Service for the Tranc3 ecosystem.

    Provides brain-computer interface simulation, bio-realistic neural
    network modeling, neural signal processing, and neuromodulatory
    system control for bridging biological and digital computation.
    """

    def __init__(self):
        self._service_id = str(uuid.uuid4())
        self.neurons: Dict[str, BioDigitalNeuron] = {}
        self.oscillators: Dict[str, NeuralOscillator] = {}
        self.bci_sessions: Dict[str, BrainComputerInterface] = {}

    def create_neuron(
        self,
        neuron_id: str,
        params: Optional[BioNeuronParams] = None,
    ) -> Dict[str, Any]:
        """Create a bio-digital neuron."""
        neuron = BioDigitalNeuron(neuron_id, params)
        self.neurons[neuron_id] = neuron
        return {"neuron_id": neuron_id, "created": True}

    def create_oscillator(self, oscillator_id: str, rhythm: str = "alpha") -> Dict[str, Any]:
        """Create a neural oscillator."""
        osc = NeuralOscillator(rhythm)
        self.oscillators[oscillator_id] = osc
        return {"oscillator_id": oscillator_id, "rhythm": rhythm}

    def create_bci_session(
        self,
        num_channels: int = 64,
        sampling_rate: float = 1000.0,
    ) -> Dict[str, Any]:
        """Create a new BCI session."""
        bci = BrainComputerInterface(num_channels, sampling_rate)
        session = bci.connect()
        self.bci_sessions[session.session_id] = bci
        return session.to_dict()

    def calibrate_bci(self, session_id: str) -> Dict[str, Any]:
        """Calibrate a BCI session."""
        bci = self.bci_sessions.get(session_id)
        if not bci:
            return {"error": f"Session {session_id} not found"}
        return bci.calibrate()

    def read_neural_signals(
        self,
        session_id: str,
        duration_ms: float = 1000.0,
    ) -> Dict[str, Any]:
        """Read neural signals from a BCI session."""
        bci = self.bci_sessions.get(session_id)
        if not bci:
            return {"error": f"Session {session_id} not found"}
        return bci.read_signals(duration_ms)

    def simulate_neural_circuit(
        self,
        num_neurons: int = 100,
        duration_ms: float = 1000.0,
        dt: float = 0.1,
    ) -> Dict[str, Any]:
        """Simulate a bio-digital neural circuit."""
        neurons = []
        for i in range(num_neurons):
            ntype = BioNeuronType.PYRAMIDAL if i % 5 != 0 else BioNeuronType.INTERNEURON
            params = BioNeuronParams(neuron_type=ntype)
            neuron = BioDigitalNeuron(f"bio_n{i}", params)
            neurons.append(neuron)

        total_spikes = 0
        num_steps = int(duration_ms / dt)

        for step in range(num_steps):
            for i, neuron in enumerate(neurons):
                # Random background input
                import random
                bg_input = random.gauss(0, 0.5)
                spiked = neuron.step(dt, bg_input)
                if spiked:
                    total_spikes += 1
                    # Send excitation to nearby neurons
                    for j in range(max(0, i - 3), min(len(neurons), i + 4)):
                        if j != i:
                            if neurons[j].params.neuron_type == BioNeuronType.INTERNEURON:
                                neurons[j].receive_inhibitory(0.1)
                            else:
                                neurons[j].receive_excitatory(0.05)

        return {
            "num_neurons": num_neurons,
            "duration_ms": duration_ms,
            "total_spikes": total_spikes,
            "spike_rate_hz": total_spikes / (num_neurons * duration_ms / 1000.0),
            "avg_membrane_voltage": sum(n.voltage for n in neurons) / len(neurons),
        }

    def get_bio_digital_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service_id": self._service_id,
            "service_type": "bio_digital_neural_interface",
            "neurons_created": len(self.neurons),
            "oscillators_created": len(self.oscillators),
            "active_bci_sessions": len(self.bci_sessions),
            "status": "operational",
        }

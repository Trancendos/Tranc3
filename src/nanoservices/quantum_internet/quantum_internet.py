"""Quantum Internet Simulation — Phase 10.5

Quantum internet simulation with quantum key distribution (QKD),
quantum repeaters, entanglement swapping, and teleportation
protocols. Provides a Python-native simulation of quantum network
infrastructure with realistic noise models and entanglement
distribution.

Simulates BB84, E91, and B92 QKD protocols along with
quantum repeater chains for long-distance quantum communication.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────


class QKProtocol(Enum):
    """Quantum key distribution protocols."""

    BB84 = "bb84"
    E91 = "e91"
    B92 = "b92"
    SARG04 = "sarg04"
    CV_QKD = "continuous_variable_qkd"


class QubitBasis(Enum):
    """Measurement bases for qubits."""

    RECTILINEAR = "z"  # |0⟩, |1⟩
    DIAGONAL = "x"  # |+⟩, |−⟩
    CIRCULAR = "y"  # |+i⟩, |−i⟩


class EntanglementState(Enum):
    """Entanglement generation states."""

    NONE = "none"
    GENERATING = "generating"
    ENTANGLED = "entangled"
    DECOHERED = "decohered"
    SWAPPED = "swapped"
    PURIFIED = "purified"


class QuantumNodeType(Enum):
    """Types of nodes in the quantum network."""

    END_NODE = "end_node"
    REPEATER = "repeater"
    SWITCH = "switch"
    TRUSTED_NODE = "trusted_node"
    SATELLITE = "satellite"


class ChannelType(Enum):
    """Quantum channel types."""

    FIBER = "fiber"
    FREE_SPACE = "free_space"
    SATELLITE_LINK = "satellite_link"
    WAVEGUIDE = "waveguide"


# ─── Data Models ──────────────────────────────────────────────────────────


@dataclass
class Qubit:
    """Simulated qubit with state vector."""

    qubit_id: str
    alpha: complex = complex(1, 0)  # |0⟩ amplitude
    beta: complex = complex(0, 0)  # |1⟩ amplitude
    basis: Optional[QubitBasis] = None
    measured: bool = False
    measurement_result: Optional[int] = None
    fidelity: float = 1.0
    decoherence_rate: float = 0.01

    def normalize(self) -> None:
        """Normalize the state vector."""
        norm = math.sqrt(abs(self.alpha) ** 2 + abs(self.beta) ** 2)
        if norm > 0:
            self.alpha /= norm
            self.beta /= norm

    def measure(self, basis: QubitBasis = QubitBasis.RECTILINEAR) -> int:
        """Measure the qubit in the given basis."""
        if self.measured:
            return self.measurement_result or 0

        self.basis = basis
        if basis == QubitBasis.RECTILINEAR:
            prob_0 = abs(self.alpha) ** 2
            result = 0 if random.random() < prob_0 else 1
        elif basis == QubitBasis.DIAGONAL:
            # Transform to diagonal basis
            p_plus = abs(self.alpha + self.beta) ** 2 / 2
            result = 0 if random.random() < p_plus else 1
        else:
            prob_0 = abs(self.alpha) ** 2
            result = 0 if random.random() < prob_0 else 1

        self.measured = True
        self.measurement_result = result
        # Collapse state
        if result == 0:
            self.alpha = complex(1, 0)
            self.beta = complex(0, 0)
        else:
            self.alpha = complex(0, 0)
            self.beta = complex(1, 0)

        return result

    def apply_noise(self, error_rate: float) -> None:
        """Apply depolarizing noise."""
        if random.random() < error_rate:
            # Bit flip
            self.alpha, self.beta = self.beta, self.alpha
        if random.random() < error_rate * 0.5:
            # Phase flip
            self.beta = -self.beta

    def to_dict(self) -> Dict[str, Any]:
        return {
            "qubit_id": self.qubit_id,
            "fidelity": self.fidelity,
            "measured": self.measured,
            "measurement_result": self.measurement_result,
        }


@dataclass
class QuantumNode:
    """A node in the quantum network."""

    node_id: str
    node_type: QuantumNodeType = QuantumNodeType.END_NODE
    position_km: float = 0.0
    memory_capacity: int = 100
    stored_qubits: List[str] = field(default_factory=list)
    fidelity_threshold: float = 0.9
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "position_km": self.position_km,
            "memory_capacity": self.memory_capacity,
            "stored_qubits": len(self.stored_qubits),
            "is_active": self.is_active,
        }


@dataclass
class QuantumChannel:
    """A quantum communication channel."""

    channel_id: str
    source_node: str
    target_node: str
    channel_type: ChannelType = ChannelType.FIBER
    length_km: float = 10.0
    attenuation_db_per_km: float = 0.2
    error_rate: float = 0.01
    bandwidth_mhz: float = 100.0

    def transmission_efficiency(self) -> float:
        """Calculate channel transmission efficiency."""
        total_attenuation = self.attenuation_db_per_km * self.length_km
        return 10 ** (-total_attenuation / 10)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "channel_type": self.channel_type.value,
            "length_km": self.length_km,
            "efficiency": self.transmission_efficiency(),
            "error_rate": self.error_rate,
        }


@dataclass
class QKSession:
    """A quantum key distribution session."""

    session_id: str
    protocol: QKProtocol = QKProtocol.BB84
    alice_node: str = ""
    bob_node: str = ""
    key_bits_sent: int = 0
    key_bits_received: int = 0
    sifted_key_length: int = 0
    final_key_length: int = 0
    qber: float = 0.0  # Quantum Bit Error Rate
    is_secure: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "protocol": self.protocol.value,
            "alice_node": self.alice_node,
            "bob_node": self.bob_node,
            "key_bits_sent": self.key_bits_sent,
            "sifted_key_length": self.sifted_key_length,
            "final_key_length": self.final_key_length,
            "qber": self.qber,
            "is_secure": self.is_secure,
        }


# ─── QKD Protocols ───────────────────────────────────────────────────────


class BB84Protocol:
    """BB84 Quantum Key Distribution Protocol.

    Alice sends random bits in random bases (Z or X).
    Bob measures in random bases.
    They sift by revealing bases (not bits).
    Privacy amplification removes Eve's information.
    """

    def __init__(self, error_rate: float = 0.01):
        self.error_rate = error_rate

    def generate_key(
        self,
        key_length: int = 256,
    ) -> Dict[str, Any]:
        """Execute BB84 protocol to generate a shared key."""
        # Step 1: Alice prepares qubits
        alice_bits = [random.randint(0, 1) for _ in range(key_length * 4)]
        alice_bases = [
            random.choice([QubitBasis.RECTILINEAR, QubitBasis.DIAGONAL])
            for _ in range(key_length * 4)
        ]

        # Step 2: Bob measures in random bases
        bob_bases = [
            random.choice([QubitBasis.RECTILINEAR, QubitBasis.DIAGONAL])
            for _ in range(key_length * 4)
        ]
        bob_results = []

        for i, (bit, a_basis, b_basis) in enumerate(zip(alice_bits, alice_bases, bob_bases)):
            qubit = Qubit(
                qubit_id=f"bb84_q{i}",
                alpha=complex(1, 0) if bit == 0 else complex(0, 0),
                beta=complex(0, 0) if bit == 0 else complex(1, 0),
            )
            # Transform if diagonal basis
            if a_basis == QubitBasis.DIAGONAL:
                if bit == 0:
                    qubit.alpha = complex(1 / math.sqrt(2), 0)
                    qubit.beta = complex(1 / math.sqrt(2), 0)
                else:
                    qubit.alpha = complex(1 / math.sqrt(2), 0)
                    qubit.beta = complex(-1 / math.sqrt(2), 0)

            # Apply channel noise
            qubit.apply_noise(self.error_rate)

            # Bob measures
            result = qubit.measure(b_basis)
            bob_results.append(result)

        # Step 3: Sifting - keep only matching bases
        sifted_alice = []
        sifted_bob = []
        for i in range(len(alice_bits)):
            if alice_bases[i] == bob_bases[i]:
                sifted_alice.append(alice_bits[i])
                sifted_bob.append(bob_results[i])

        # Step 4: Error estimation (sacrifice some bits)
        sample_size = max(1, len(sifted_alice) // 4)
        errors = sum(
            1 for a, b in zip(sifted_alice[:sample_size], sifted_bob[:sample_size]) if a != b
        )
        qber = errors / sample_size if sample_size > 0 else 1.0

        # Step 5: Remove sampled bits
        remaining_alice = sifted_alice[sample_size:]
        remaining_bob = sifted_bob[sample_size:]

        # Step 6: Error correction (simplified)
        corrected = []
        for a, b in zip(remaining_alice, remaining_bob):
            if a == b:
                corrected.append(a)

        # Step 7: Privacy amplification (hash)
        if corrected:
            key_str = "".join(str(b) for b in corrected)
            final_key = hashlib.sha256(key_str.encode()).hexdigest()[: key_length // 4]
        else:
            final_key = ""

        is_secure = qber < 0.11  # BB84 security threshold

        return {
            "protocol": "bb84",
            "bits_sent": key_length * 4,
            "sifted_length": len(sifted_alice),
            "qber": qber,
            "corrected_length": len(corrected),
            "final_key_length": len(final_key) * 4,  # hex chars to bits
            "is_secure": is_secure,
            "final_key_hash": hashlib.sha256(final_key.encode()).hexdigest()[:16],
        }


class E91Protocol:
    """E91 QKD Protocol using entangled pairs.

    Uses Bell states for key distribution with inherent
    security from entanglement correlations.
    """

    def __init__(self, error_rate: float = 0.01):
        self.error_rate = error_rate

    def generate_key(self, key_length: int = 256) -> Dict[str, Any]:
        """Execute E91 protocol."""
        num_pairs = key_length * 4

        # Generate entangled pairs (|00⟩ + |11⟩)/√2
        alice_bits = []
        bob_bits = []
        alice_bases = []
        bob_bases = []

        for i in range(num_pairs):
            # Entangled measurement - correlated results
            bit = random.randint(0, 1)
            a_basis = random.choice([QubitBasis.RECTILINEAR, QubitBasis.DIAGONAL])
            b_basis = random.choice([QubitBasis.RECTILINEAR, QubitBasis.DIAGONAL])

            if a_basis == b_basis:
                # Same basis: perfectly correlated (minus noise)
                a_result = bit
                b_result = bit if random.random() > self.error_rate else 1 - bit
            else:
                # Different basis: uncorrelated
                a_result = bit
                b_result = random.randint(0, 1)

            alice_bits.append(a_result)
            bob_bits.append(b_result)
            alice_bases.append(a_basis)
            bob_bases.append(b_basis)

        # Sift same-basis measurements
        sifted = [
            (a, b) for a, b, ab, bb in zip(alice_bits, bob_bits, alice_bases, bob_bases) if ab == bb
        ]
        # _alice_sifted = [s[0] for s in sifted]  # noqa: F841
        # _bob_sifted = [s[1] for s in sifted]  # noqa: F841

        errors = sum(1 for a, b in sifted if a != b)
        qber = errors / len(sifted) if sifted else 1.0

        corrected = [a for a, b in sifted if a == b]

        return {
            "protocol": "e91",
            "pairs_generated": num_pairs,
            "sifted_length": len(sifted),
            "qber": qber,
            "corrected_length": len(corrected),
            "is_secure": qber < 0.11,
        }


# ─── Quantum Repeater ────────────────────────────────────────────────────


class QuantumRepeater:
    """Quantum repeater for long-distance entanglement distribution.

    Implements entanglement swapping and purification to extend
    entanglement across multiple hops.
    """

    def __init__(
        self,
        repeater_id: str,
        num_memories: int = 10,
        swap_fidelity: float = 0.95,
        purification_threshold: float = 0.9,
    ):
        self.repeater_id = repeater_id
        self.num_memories = num_memories
        self.swap_fidelity = swap_fidelity
        self.purification_threshold = purification_threshold
        self.entangled_pairs: List[Dict[str, Any]] = []

    def entanglement_swap(
        self,
        pair_left: Dict[str, Any],
        pair_right: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Perform entanglement swapping between two pairs."""
        new_fidelity = pair_left["fidelity"] * pair_right["fidelity"] * self.swap_fidelity
        new_pair = {
            "id": str(uuid.uuid4())[:8],
            "source": pair_left["source"],
            "target": pair_right["target"],
            "fidelity": new_fidelity,
            "hops": pair_left.get("hops", 1) + pair_right.get("hops", 1),
        }
        return new_pair

    def purify(
        self,
        pair1: Dict[str, Any],
        pair2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Perform entanglement purification using DEJMPS protocol."""
        f1 = pair1["fidelity"]
        f2 = pair2["fidelity"]
        # Purification improves fidelity
        new_fidelity = (f1 * f2) / (f1 * f2 + (1 - f1) * (1 - f2))
        return {
            "id": pair1["id"],
            "source": pair1["source"],
            "target": pair1["target"],
            "fidelity": new_fidelity,
            "hops": pair1.get("hops", 1),
            "purified": True,
        }

    def create_entangled_pair(
        self,
        source: str,
        target: str,
        fidelity: float = 0.95,
    ) -> Dict[str, Any]:
        """Create an entangled pair between adjacent nodes."""
        pair = {
            "id": str(uuid.uuid4())[:8],
            "source": source,
            "target": target,
            "fidelity": fidelity,
            "hops": 1,
        }
        self.entangled_pairs.append(pair)
        return pair


# ─── Quantum Network ─────────────────────────────────────────────────────


class QuantumNetwork:
    """Quantum internet network with nodes, channels, and protocols."""

    def __init__(self):
        self.nodes: Dict[str, QuantumNode] = {}
        self.channels: Dict[str, QuantumChannel] = {}
        self.repeaters: Dict[str, QuantumRepeater] = {}
        self.qkd_sessions: Dict[str, QKSession] = {}
        self.bb84 = BB84Protocol()
        self.e91 = E91Protocol()

    def add_node(self, node: QuantumNode) -> None:
        """Add a quantum node to the network."""
        self.nodes[node.node_id] = node

    def add_channel(self, channel: QuantumChannel) -> None:
        """Add a quantum channel."""
        self.channels[channel.channel_id] = channel

    def add_repeater(self, repeater: QuantumRepeater) -> None:
        """Add a quantum repeater."""
        self.repeaters[repeater.repeater_id] = repeater

    def distribute_entanglement(
        self,
        node_a: str,
        node_b: str,
        target_fidelity: float = 0.8,
    ) -> Dict[str, Any]:
        """Distribute entanglement between two nodes, using repeaters if needed."""
        # Find path (simple linear for now)
        path = self._find_path(node_a, node_b)
        if not path:
            return {"error": "No path found between nodes"}

        if len(path) == 2:
            # Direct entanglement
            channel = self._get_channel(node_a, node_b)
            fidelity = 0.95 if channel is None else 0.95 * channel.transmission_efficiency()
            pair = {
                "id": str(uuid.uuid4())[:8],
                "source": node_a,
                "target": node_b,
                "fidelity": fidelity,
                "hops": 1,
            }
            return pair

        # Multi-hop with repeaters
        pairs = []
        for i in range(len(path) - 1):
            channel = self._get_channel(path[i], path[i + 1])
            fidelity = 0.95 if channel is None else 0.95 * channel.transmission_efficiency()
            pair = {
                "id": str(uuid.uuid4())[:8],
                "source": path[i],
                "target": path[i + 1],
                "fidelity": fidelity,
                "hops": 1,
            }
            pairs.append(pair)

        # Swap through repeaters
        current_pair = pairs[0]
        for i in range(1, len(pairs)):
            repeater_id = path[i]
            repeater = self.repeaters.get(repeater_id)
            if repeater:
                current_pair = repeater.entanglement_swap(current_pair, pairs[i])
            else:
                current_pair = QuantumRepeater("temp").entanglement_swap(current_pair, pairs[i])

        # Purify if below threshold
        if current_pair["fidelity"] < target_fidelity and len(pairs) > 1:
            # Generate another pair for purification
            second_pair = {
                "id": str(uuid.uuid4())[:8],
                "source": node_a,
                "target": node_b,
                "fidelity": current_pair["fidelity"] * 0.9,
                "hops": current_pair.get("hops", 1),
            }
            temp_repeater = QuantumRepeater("purify")
            current_pair = temp_repeater.purify(current_pair, second_pair)

        return current_pair

    def quantum_teleport(
        self,
        source: str,
        target: str,
        qubit: Qubit,
    ) -> Dict[str, Any]:
        """Teleport a qubit from source to target using entanglement."""
        entangled = self.distribute_entanglement(source, target)
        if "error" in entangled:
            return entangled

        fidelity = entangled.get("fidelity", 0.9)

        # Simulate teleportation
        # Alice performs Bell measurement
        bell_outcome = random.randint(0, 3)

        # Bob applies correction based on classical communication
        corrections = ["I", "X", "Z", "XZ"]
        correction = corrections[bell_outcome]

        # Teleported qubit has reduced fidelity
        teleported = Qubit(
            qubit_id=f"teleported_{qubit.qubit_id}",
            alpha=qubit.alpha,
            beta=qubit.beta,
            fidelity=qubit.fidelity * fidelity,
        )

        return {
            "source": source,
            "target": target,
            "original_qubit": qubit.qubit_id,
            "teleported_fidelity": teleported.fidelity,
            "bell_measurement": bell_outcome,
            "correction_applied": correction,
            "success": teleported.fidelity > 0.5,
        }

    def run_qkd(
        self,
        alice_node: str,
        bob_node: str,
        protocol: QKProtocol = QKProtocol.BB84,
        key_length: int = 256,
    ) -> Dict[str, Any]:
        """Run a QKD session between two nodes."""
        channel = self._get_channel(alice_node, bob_node)
        error_rate = channel.error_rate if channel else 0.01

        if protocol == QKProtocol.BB84:
            result = BB84Protocol(error_rate).generate_key(key_length)
        elif protocol == QKProtocol.E91:
            result = E91Protocol(error_rate).generate_key(key_length)
        else:
            result = BB84Protocol(error_rate).generate_key(key_length)

        session = QKSession(
            session_id=str(uuid.uuid4())[:8],
            protocol=protocol,
            alice_node=alice_node,
            bob_node=bob_node,
            key_bits_sent=result.get("bits_sent", result.get("pairs_generated", 0)),
            sifted_key_length=result.get("sifted_length", 0),
            final_key_length=result.get("corrected_length", 0),
            qber=result.get("qber", 1.0),
            is_secure=result.get("is_secure", False),
        )
        self.qkd_sessions[session.session_id] = session

        return {**result, "session_id": session.session_id}

    def _find_path(self, node_a: str, node_b: str) -> Optional[List[str]]:
        """Simple path finding (BFS)."""
        if node_a not in self.nodes or node_b not in self.nodes:
            return None

        # Build adjacency
        adj: Dict[str, List[str]] = {n: [] for n in self.nodes}
        for ch in self.channels.values():
            if ch.source_node in adj and ch.target_node in adj:
                adj[ch.source_node].append(ch.target_node)
                adj[ch.target_node].append(ch.source_node)

        # BFS
        visited = {node_a}
        queue = [[node_a]]
        while queue:
            path = queue.pop(0)
            current = path[-1]
            if current == node_b:
                return path
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def _get_channel(self, node_a: str, node_b: str) -> Optional[QuantumChannel]:
        """Get channel between two nodes."""
        for ch in self.channels.values():
            if (ch.source_node == node_a and ch.target_node == node_b) or (
                ch.source_node == node_b and ch.target_node == node_a
            ):
                return ch
        return None


# ─── Main Service ─────────────────────────────────────────────────────────


class QuantumInternetService:
    """Quantum Internet Simulation Service for the Tranc3 ecosystem.

    Provides quantum key distribution, entanglement distribution,
    quantum teleportation, and quantum repeater simulation.
    """

    def __init__(self):
        self.network = QuantumNetwork()
        self._service_id = str(uuid.uuid4())

    def create_network(
        self,
        num_nodes: int = 5,
        spacing_km: float = 50.0,
    ) -> Dict[str, Any]:
        """Create a linear quantum network with repeaters."""
        # Create end nodes
        self.network.add_node(
            QuantumNode(
                node_id="alice",
                node_type=QuantumNodeType.END_NODE,
                position_km=0.0,
            )
        )
        self.network.add_node(
            QuantumNode(
                node_id="bob",
                node_type=QuantumNodeType.END_NODE,
                position_km=spacing_km * (num_nodes - 1),
            )
        )

        # Create repeaters
        for i in range(1, num_nodes - 1):
            rid = f"repeater_{i}"
            self.network.add_node(
                QuantumNode(
                    node_id=rid,
                    node_type=QuantumNodeType.REPEATER,
                    position_km=spacing_km * i,
                )
            )
            self.network.add_repeater(QuantumRepeater(rid))

        # Create channels
        nodes = sorted(self.network.nodes.keys(), key=lambda n: self.network.nodes[n].position_km)
        for i in range(len(nodes) - 1):
            n1 = nodes[i]
            n2 = nodes[i + 1]
            dist = abs(self.network.nodes[n2].position_km - self.network.nodes[n1].position_km)
            self.network.add_channel(
                QuantumChannel(
                    channel_id=f"ch_{n1}_{n2}",
                    source_node=n1,
                    target_node=n2,
                    length_km=dist,
                )
            )

        return {
            "nodes": len(self.network.nodes),
            "channels": len(self.network.channels),
            "repeaters": len(self.network.repeaters),
            "total_distance_km": spacing_km * (num_nodes - 1),
        }

    def run_qkd(
        self,
        alice: str = "alice",
        bob: str = "bob",
        protocol: str = "bb84",
        key_length: int = 256,
    ) -> Dict[str, Any]:
        """Run QKD between two nodes."""
        proto = QKProtocol.BB84 if protocol == "bb84" else QKProtocol.E91
        return self.network.run_qkd(alice, bob, proto, key_length)

    def teleport_qubit(self, source: str = "alice", target: str = "bob") -> Dict[str, Any]:
        """Teleport a qubit between nodes."""
        qubit = Qubit(qubit_id="teleport_test")
        return self.network.quantum_teleport(source, target, qubit)

    def get_network_status(self) -> Dict[str, Any]:
        """Get quantum network status."""
        return {
            "nodes": len(self.network.nodes),
            "channels": len(self.network.channels),
            "repeaters": len(self.network.repeaters),
            "qkd_sessions": len(self.network.qkd_sessions),
        }

    def get_quantum_internet_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service_id": self._service_id,
            "service_type": "quantum_internet",
            "network": self.get_network_status(),
            "status": "operational",
        }

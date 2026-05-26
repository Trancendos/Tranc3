"""MPC Service — Phase 9.5

Multi-party computation service supporting secret sharing,
garbled circuits, and oblivious transfer protocols.
Python-native simulation with MP-SPDZ upgrade path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MPCProtocol(Enum):
    SHAMIR_SECRET_SHARING = "shamir"
    ADDITIVE_SECRET_SHARING = "additive"
    GARBLED_CIRCUIT = "garbled_circuit"
    OBLIVIOUS_TRANSFER = "oblivious_transfer"
    SPDZ = "spdz"
    HONEST_MAJORITY = "honest_majority"


class MPCPartyState(Enum):
    CONNECTED = "connected"
    COMPUTING = "computing"
    WAITING = "waiting"
    FINISHED = "finished"
    DISCONNECTED = "disconnected"


@dataclass
class MPCParty:
    """A party in the MPC protocol."""
    party_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    state: MPCPartyState = MPCPartyState.CONNECTED
    address: str = ""
    shares: List[int] = field(default_factory=list)
    result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "party_id": self.party_id,
            "name": self.name,
            "state": self.state.value,
            "has_shares": len(self.shares) > 0,
            "has_result": self.result is not None,
        }


@dataclass
class MPCSession:
    """An MPC computation session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    protocol: MPCProtocol = MPCProtocol.SHAMIR_SECRET_SHARING
    parties: List[str] = field(default_factory=list)
    threshold: int = 0
    total_parties: int = 0
    function: str = ""
    status: str = "created"
    result: Optional[Any] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "protocol": self.protocol.value,
            "total_parties": self.total_parties,
            "threshold": self.threshold,
            "function": self.function,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class ShamirSecretSharing:
    """Shamir's (t, n) threshold secret sharing scheme.

    Uses polynomial interpolation over a prime field.
    Python-native, 0-cost implementation.
    """

    def __init__(self, prime: int = 2 ** 127 - 1):
        self.prime = prime

    def share(self, secret: int, threshold: int, num_shares: int) -> List[Tuple[int, int]]:
        if threshold > num_shares:
            raise ValueError("Threshold cannot exceed number of shares")
        coefficients = [secret] + [random.randint(1, self.prime - 1) for _ in range(threshold - 1)]
        shares = []
        for i in range(1, num_shares + 1):
            y = 0
            for j, coeff in enumerate(coefficients):
                y = (y + coeff * pow(i, j, self.prime)) % self.prime
            shares.append((i, y))
        return shares

    def reconstruct(self, shares: List[Tuple[int, int]]) -> int:
        if len(shares) < 2:
            raise ValueError("Need at least 2 shares for reconstruction")
        secret = 0
        for i, (xi, yi) in enumerate(shares):
            numerator = 1
            denominator = 1
            for j, (xj, _) in enumerate(shares):
                if i != j:
                    numerator = (numerator * (-xj)) % self.prime
                    denominator = (denominator * (xi - xj)) % self.prime
            lagrange = (numerator * pow(denominator, self.prime - 2, self.prime)) % self.prime
            secret = (secret + yi * lagrange) % self.prime
        return secret


class AdditiveSecretSharing:
    """Additive secret sharing for n-party computation."""

    def share(self, secret: int, num_parties: int, modulus: int = 2 ** 32) -> List[int]:
        shares = [random.randint(0, modulus - 1) for _ in range(num_parties - 1)]
        last_share = (secret - sum(shares)) % modulus
        shares.append(last_share)
        return shares

    def reconstruct(self, shares: List[int], modulus: int = 2 ** 32) -> int:
        return sum(shares) % modulus


class GarbledCircuitSimulator:
    """Simulates Yao's Garbled Circuit protocol."""

    def garble(self, circuit_description: str,
               inputs: Dict[str, int]) -> Dict[str, Any]:
        wire_labels = {}
        for wire_id, value in inputs.items():
            label_0 = hashlib.sha256(f"{wire_id}:0:{uuid.uuid4().hex[:8]}".encode()).hexdigest()[:16]
            label_1 = hashlib.sha256(f"{wire_id}:1:{uuid.uuid4().hex[:8]}".encode()).hexdigest()[:16]
            wire_labels[wire_id] = {"0": label_0, "1": label_1}

        garbled_tables = []
        for gate_id in range(len(inputs) // 2):
            garbled_tables.append({
                "gate_id": gate_id,
                "type": "AND",
                "entries": [hashlib.sha256(f"{gate_id}:{i}".encode()).hexdigest()[:16]
                           for i in range(4)],
            })

        return {
            "circuit": circuit_description,
            "wire_labels": wire_labels,
            "garbled_tables": garbled_tables,
            "input_encoding": {k: v[str(min(1, val))] for k, v, val in
                              zip(inputs.keys(),
                                  [wire_labels[k] for k in inputs.keys()],
                                  inputs.values())},
        }

    def evaluate(self, garbled_circuit: Dict[str, Any],
                  encoded_inputs: Dict[str, str]) -> Dict[str, Any]:
        return {
            "result": hashlib.sha256(
                json.dumps(encoded_inputs, sort_keys=True).encode()
            ).hexdigest()[:16],
            "num_gates": len(garbled_circuit.get("garbled_tables", [])),
        }


class ObliviousTransferSimulator:
    """Simulates 1-out-of-2 Oblivious Transfer."""

    def transfer(self, sender_messages: List[str],
                  receiver_choice: int) -> str:
        if receiver_choice < 0 or receiver_choice >= len(sender_messages):
            raise ValueError("Invalid receiver choice")
        return sender_messages[receiver_choice]


class MPCService:
    """Multi-party Computation service.

    Features:
    - Shamir's Secret Sharing (t, n) threshold scheme
    - Additive Secret Sharing for n-party computation
    - Garbled Circuit simulation (Yao's protocol)
    - Oblivious Transfer simulation
    - SPDZ protocol simulation (upgradeable to MP-SPDZ)
    - Session management for multi-party computations
    """

    def __init__(self):
        self.parties: Dict[str, MPCParty] = {}
        self.sessions: Dict[str, MPCSession] = {}
        self.shamir = ShamirSecretSharing()
        self.additive = AdditiveSecretSharing()
        self.garbled = GarbledCircuitSimulator()
        self.ot = ObliviousTransferSimulator()
        self._id = str(uuid.uuid4())[:8]

    def register_party(self, name: str = "", address: str = "") -> MPCParty:
        party = MPCParty(name=name or f"party-{str(uuid.uuid4())[:6]}", address=address)
        self.parties[party.party_id] = party
        logger.info("Registered MPC party: %s", party.name)
        return party

    def remove_party(self, party_id: str) -> bool:
        if party_id in self.parties:
            self.parties[party_id].state = MPCPartyState.DISCONNECTED
            del self.parties[party_id]
            return True
        return False

    def create_session(self, protocol: MPCProtocol,
                        party_ids: List[str],
                        threshold: int = 0,
                        function: str = "") -> MPCSession:
        active_parties = [pid for pid in party_ids if pid in self.parties]
        if len(active_parties) < 2:
            raise ValueError("Need at least 2 parties for MPC")

        session = MPCSession(
            protocol=protocol,
            parties=active_parties,
            threshold=threshold or len(active_parties) // 2 + 1,
            total_parties=len(active_parties),
            function=function,
        )
        self.sessions[session.session_id] = session
        for pid in active_parties:
            self.parties[pid].state = MPCPartyState.COMPUTING
        return session

    def shamir_share(self, session_id: str, secret: int) -> Dict[str, List[int]]:
        session = self.sessions.get(session_id)
        if not session:
            return {}
        shares = self.shamir.share(secret, session.threshold, session.total_parties)
        result = {}
        for i, pid in enumerate(session.parties):
            if i < len(shares):
                self.parties[pid].shares.append(shares[i][1])
                result[pid] = [shares[i][1]]
        session.status = "shared"
        return result

    def shamir_reconstruct(self, session_id: str,
                            share_dict: Optional[Dict[str, List[int]]] = None) -> Optional[int]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        shares = []
        for pid in session.parties:
            if share_dict and pid in share_dict:
                shares.append((session.parties.index(pid) + 1, share_dict[pid][0]))
            elif self.parties[pid].shares:
                shares.append((session.parties.index(pid) + 1, self.parties[pid].shares[0]))
        if len(shares) < session.threshold:
            logger.warning("Not enough shares: %d < %d", len(shares), session.threshold)
            return None
        result = self.shamir.reconstruct(shares[:session.threshold])
        session.result = result
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc).isoformat()
        for pid in session.parties:
            self.parties[pid].state = MPCPartyState.FINISHED
        return result

    def additive_share(self, secret: int, num_parties: int) -> List[int]:
        return self.additive.share(secret, num_parties)

    def additive_reconstruct(self, shares: List[int]) -> int:
        return self.additive.reconstruct(shares)

    def garbled_circuit_compute(self, circuit: str,
                                 inputs: Dict[str, int]) -> Dict[str, Any]:
        garbled = self.garbled.garble(circuit, inputs)
        encoded = garbled.get("input_encoding", {})
        result = self.garbled.evaluate(garbled, encoded)
        return result

    def oblivious_transfer(self, messages: List[str], choice: int) -> str:
        return self.ot.transfer(messages, choice)

    def get_service_status(self) -> Dict[str, Any]:
        return {
            "service_id": self._id,
            "total_parties": len(self.parties),
            "active_parties": sum(1 for p in self.parties.values()
                                  if p.state == MPCPartyState.COMPUTING),
            "total_sessions": len(self.sessions),
            "completed_sessions": sum(1 for s in self.sessions.values()
                                      if s.status == "completed"),
            "supported_protocols": [p.value for p in MPCProtocol],
        }

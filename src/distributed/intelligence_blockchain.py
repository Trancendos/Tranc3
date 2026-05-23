# src/distributed/intelligence_blockchain.py
# Simplified IntelligenceBlockchain — 5 Whys #8 root cause fix
# Production-grade simplified version; swap for full crypto when needed

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class Block:
    index: int
    timestamp: float
    computations: List[Dict]
    proof: int
    previous_hash: str
    hash: str = ""

    def compute_hash(self) -> str:
        block_str = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "computations": self.computations,
                "proof": self.proof,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(block_str.encode()).hexdigest()


class IntelligenceBlockchain:
    """
    Simplified blockchain for recording AI computations.
    Provides trust, auditability, and reproducibility for distributed inference.
    Root cause fix: was referenced but never implemented.
    """

    def __init__(self):
        self.chain: List[Block] = []
        self.pending: List[Dict] = []
        self._create_genesis()
        logger.info("IntelligenceBlockchain initialised")

    def _create_genesis(self):
        genesis = Block(index=0, timestamp=time.time(), computations=[], proof=1, previous_hash="0")
        genesis.hash = genesis.compute_hash()
        self.chain.append(genesis)

    def add_computation(self, problem: Dict, result: Any, participants: List[str]) -> int:
        computation = {
            "problem_hash": self._hash_dict(problem),
            "result_hash": self._hash_dict(result)
            if isinstance(result, dict)
            else str(result)[:64],
            "participants": participants,
            "timestamp": time.time(),
        }
        self.pending.append(computation)

        if len(self.pending) >= 10:
            self._mine_block()

        return len(self.chain) - 1

    def _mine_block(self):
        last = self.chain[-1]
        proof = self._proof_of_work(last.proof)
        block = Block(
            index=len(self.chain),
            timestamp=time.time(),
            computations=self.pending.copy(),
            proof=proof,
            previous_hash=last.hash,
        )
        block.hash = block.compute_hash()
        self.chain.append(block)
        self.pending.clear()
        logger.info(
            "Block mined: #%s, hash=%s...",
            sanitize_for_log(block.index),
            sanitize_for_log(block.hash[:16]),
        )  # codeql[py/cleartext-logging]

    def _proof_of_work(self, last_proof: int, difficulty: int = 2) -> int:
        proof = 0
        target = "0" * difficulty
        while not hashlib.sha256(f"{last_proof}{proof}".encode()).hexdigest().startswith(target):
            proof += 1
        return proof

    def _hash_dict(self, d: Dict) -> str:
        return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:32]

    def is_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            curr, prev = self.chain[i], self.chain[i - 1]
            if curr.previous_hash != prev.hash:
                return False
            if curr.hash != curr.compute_hash():
                return False
        return True

    def get_stats(self) -> Dict:
        return {
            "blocks": len(self.chain),
            "pending_computations": len(self.pending),
            "is_valid": self.is_valid(),
            "total_computations": sum(len(b.computations) for b in self.chain),
        }


class HomomorphicCrypto:
    """
    Simplified privacy-preserving computation layer.
    Uses additive noise (differential privacy) as a practical substitute
    for full homomorphic encryption until hardware supports it.
    """

    def __init__(self, epsilon: float = 1.0):
        self.epsilon = epsilon  # Privacy budget
        logger.info(
            "HomomorphicCrypto initialised (ε=%s)", sanitize_for_log(epsilon)
        )  # codeql[py/cleartext-logging]

    def encrypt_gradients(self, model) -> Dict:
        """Add Gaussian noise to gradients (differential privacy)."""
        import torch

        noisy = {}
        for name, param in model.named_parameters():
            if param.grad is not None:
                sensitivity = param.grad.norm().item()
                noise_scale = sensitivity / self.epsilon
                noisy[name] = param.grad + torch.randn_like(param.grad) * noise_scale
        return noisy

    def secure_aggregation(self, encrypted_list: List[Dict]) -> Dict:
        """Aggregate noisy gradients — noise cancels out in expectation."""
        import torch

        if not encrypted_list:
            return {}
        aggregated = {}
        for key in encrypted_list[0]:
            tensors = [e[key] for e in encrypted_list if key in e]
            aggregated[key] = torch.stack(tensors).mean(dim=0)
        return aggregated

    def add_differential_privacy(self, gradients: Dict) -> Dict:
        """Clip and add calibrated noise."""
        import torch

        private = {}
        for key, grad in gradients.items():
            clipped = grad / max(1.0, grad.norm().item())
            noise = torch.randn_like(clipped) * (1.0 / self.epsilon)
            private[key] = clipped + noise
        return private

"""
DNA/Genome encoding for config mutation and A/B evolution.

Encodes arbitrary config dicts as nucleotide strings (ACGT),
enabling genetic crossover, point mutation, and config versioning.
All operations are pure Python — zero external dependencies.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, Tuple

_NUCLEOTIDES = "ACGT"
_NMAP: Dict[str, int] = {"A": 0, "C": 1, "G": 2, "T": 3}


def config_to_genome(config: Dict[str, Any]) -> str:
    """Encode a config dict as a DNA nucleotide string."""
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    bits = "".join(f"{b:08b}" for b in payload.encode())
    # Pad to multiple of 2
    if len(bits) % 2:
        bits += "0"
    return "".join(_NUCLEOTIDES[int(bits[i : i + 2], 2)] for i in range(0, len(bits), 2))


def genome_to_config(genome: str) -> Dict[str, Any]:
    """Decode a nucleotide string back to a config dict."""
    bits = "".join(f"{_NMAP[n]:02b}" for n in genome)
    # Recover bytes
    n_bytes = len(bits) // 8
    raw = bytes(int(bits[i : i + 8], 2) for i in range(0, n_bytes * 8, 8))
    # Strip padding nulls
    raw = raw.rstrip(b"\x00")
    return json.loads(raw.decode())


def mutate_genome(
    genome: str, mutation_rate: float = 0.01, rng: random.Random | None = None
) -> str:
    """Apply random point mutations (SNP-style) to a genome string."""
    r = rng or random
    return "".join(r.choice(_NUCLEOTIDES) if r.random() < mutation_rate else n for n in genome)


def crossover_genomes(
    parent_a: str, parent_b: str, rng: random.Random | None = None
) -> Tuple[str, str]:
    """Single-point crossover — produces two offspring genomes."""
    r = rng or random
    if len(parent_a) != len(parent_b):
        # Truncate to shorter
        length = min(len(parent_a), len(parent_b))
        parent_a, parent_b = parent_a[:length], parent_b[:length]
    cut = r.randint(0, len(parent_a))
    child_a = parent_a[:cut] + parent_b[cut:]
    child_b = parent_b[:cut] + parent_a[cut:]
    return child_a, child_b


def genome_hash(genome: str) -> str:
    """Stable SHA-256 fingerprint of a genome — use as config version ID."""
    return hashlib.sha256(genome.encode()).hexdigest()[:16]


class GenomeConfig:
    """
    Wraps a config dict with genome encoding for evolutionary mutation.

    Usage::

        gc = GenomeConfig({"batch_size": 16, "cache_ttl": 300, "concurrency": 4})
        mutated = gc.mutate(rate=0.005)
        child_a, child_b = gc.crossover(other_gc)
        version_id = gc.version_id   # stable 16-char hash
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._genome = config_to_genome(config)

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @property
    def genome(self) -> str:
        return self._genome

    @property
    def version_id(self) -> str:
        return genome_hash(self._genome)

    def mutate(self, rate: float = 0.005, rng: random.Random | None = None) -> "GenomeConfig":
        new_genome = mutate_genome(self._genome, mutation_rate=rate, rng=rng)
        try:
            new_config = genome_to_config(new_genome)
        except Exception:
            # Mutation produced invalid JSON — return self unchanged
            return self
        return GenomeConfig(new_config)

    def crossover(
        self, other: "GenomeConfig", rng: random.Random | None = None
    ) -> Tuple["GenomeConfig", "GenomeConfig"]:
        child_a_genome, child_b_genome = crossover_genomes(self._genome, other._genome, rng=rng)
        results = []
        for g in (child_a_genome, child_b_genome):
            try:
                results.append(GenomeConfig(genome_to_config(g)))
            except Exception:
                results.append(GenomeConfig(self._config.copy()))
        return results[0], results[1]

    def __repr__(self) -> str:
        return f"GenomeConfig(version={self.version_id}, keys={list(self._config.keys())})"

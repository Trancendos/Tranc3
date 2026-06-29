"""Bio-Synthetic Evolution — Phase 11

Synthetic biology simulation for the Tranc3 ecosystem.
Implements in-silico evolution of synthetic organisms with
genetic circuits, metabolic networks, protein folding
simulation, and population-level evolutionary dynamics.

Provides a computational framework for designing, simulating,
and evolving synthetic biological systems with configurable
fitness landscapes, mutation operators, and selection pressures
for bio-digital convergence applications.
"""

from __future__ import annotations

import logging
import random  # nosec B311 -- non-cryptographic simulation use
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────


class Nucleotide(Enum):
    """DNA/RNA nucleotides."""

    A = "adenine"
    T = "thymine"
    G = "guanine"
    C = "cytosine"
    U = "uracil"


class AminoAcid(Enum):
    """Standard amino acids."""

    ALA = "alanine"
    ARG = "arginine"
    ASN = "asparagine"
    ASP = "aspartate"
    CYS = "cysteine"
    GLN = "glutamine"
    GLU = "glutamate"
    GLY = "glycine"
    HIS = "histidine"
    ILE = "isoleucine"
    LEU = "leucine"
    LYS = "lysine"
    MET = "methionine"
    PHE = "phenylalanine"
    PRO = "proline"
    SER = "serine"
    THR = "threonine"
    TRP = "tryptophan"
    TYR = "tyrosine"
    VAL = "valine"


class GeneFunction(Enum):
    """Types of gene functions."""

    STRUCTURAL = "structural"
    ENZYMATIC = "enzymatic"
    REGULATORY = "regulatory"
    TRANSPORT = "transport"
    SIGNALING = "signaling"
    DEFENSE = "defense"
    METABOLIC = "metabolic"
    REPLICATION = "replication"


class CircuitType(Enum):
    """Genetic circuit types."""

    REPRESSILATOR = "repressilator"
    TOGGLE_SWITCH = "toggle_switch"
    OSCILLATOR = "oscillator"
    AND_GATE = "and_gate"
    OR_GATE = "or_gate"
    NOT_GATE = "not_gate"
    NAND_GATE = "nand_gate"
    FEEDBACK = "feedback"


class MutationType(Enum):
    """Types of genetic mutations."""

    POINT = "point"
    INSERTION = "insertion"
    DELETION = "deletion"
    DUPLICATION = "duplication"
    INVERSION = "inversion"
    TRANSLOCATION = "translocation"
    FRAMESHIFT = "frameshift"


class SelectionPressure(Enum):
    """Types of selection pressure."""

    FITNESS = "fitness"
    NEUTRAL = "neutral"
    TOURNAMENT = "tournament"
    DIVERSIFYING = "diversifying"
    STABILIZING = "stabilizing"
    DISRUPTIVE = "disruptive"
    FREQUENCY_DEPENDENT = "frequency_dependent"


class OrganismState(Enum):
    """States of a synthetic organism."""

    EMBRYONIC = "embryonic"
    GROWING = "growing"
    MATURE = "mature"
    REPRODUCING = "reproducing"
    SENESCING = "senescing"
    DEAD = "dead"


# ─── Data Models ────────────────────────────────────────────────────────


@dataclass
class Gene:
    """A synthetic gene."""

    id: str = ""
    name: str = ""
    sequence: str = ""
    function: GeneFunction = GeneFunction.STRUCTURAL
    expression_level: float = 1.0
    regulatory_sites: List[str] = field(default_factory=list)
    promoter_strength: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.sequence:
            self.sequence = self._random_sequence(random.randint(30, 300))

    def _random_sequence(self, length: int) -> str:
        return "".join(random.choice("ATGC") for _ in range(length))

    def mutate(self, mutation_type: MutationType = MutationType.POINT) -> "Gene":
        """Apply a mutation to this gene."""
        seq = list(self.sequence)
        if mutation_type == MutationType.POINT and seq:
            idx = random.randint(0, len(seq) - 1)
            seq[idx] = random.choice("ATGC")
        elif mutation_type == MutationType.INSERTION:
            idx = random.randint(0, len(seq))
            seq.insert(idx, random.choice("ATGC"))
        elif mutation_type == MutationType.DELETION and len(seq) > 10:
            idx = random.randint(0, len(seq) - 1)
            seq.pop(idx)
        elif mutation_type == MutationType.DUPLICATION and seq:
            idx = random.randint(0, len(seq) - 1)
            length = min(random.randint(1, 10), len(seq) - idx)
            dup = seq[idx : idx + length]
            seq[idx:idx] = dup
        elif mutation_type == MutationType.INVERSION and len(seq) > 2:
            idx = random.randint(0, len(seq) - 2)
            length = min(random.randint(2, 10), len(seq) - idx)
            seq[idx : idx + length] = reversed(seq[idx : idx + length])

        return Gene(
            name=self.name + "'",
            sequence="".join(seq),
            function=self.function,
            expression_level=self.expression_level * random.uniform(0.8, 1.2),
            promoter_strength=self.promoter_strength * random.uniform(0.9, 1.1),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sequence_length": len(self.sequence),
            "function": self.function.value,
            "expression_level": self.expression_level,
            "promoter_strength": self.promoter_strength,
        }


@dataclass
class GeneticCircuit:
    """A synthetic genetic circuit."""

    id: str = ""
    name: str = ""
    circuit_type: CircuitType = CircuitType.TOGGLE_SWITCH
    genes: List[Gene] = field(default_factory=list)
    connections: List[Dict[str, Any]] = field(default_factory=list)
    output_species: List[str] = field(default_factory=list)
    input_species: List[str] = field(default_factory=list)
    steady_state: Dict[str, float] = field(default_factory=dict)
    period: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def simulate(self, steps: int = 100, dt: float = 0.1) -> List[Dict[str, float]]:
        """Simulate the genetic circuit dynamics."""
        if self.circuit_type == CircuitType.REPRESSILATOR:
            return self._simulate_repressilator(steps, dt)
        elif self.circuit_type == CircuitType.TOGGLE_SWITCH:
            return self._simulate_toggle(steps, dt)
        elif self.circuit_type == CircuitType.OSCILLATOR:
            return self._simulate_oscillator(steps, dt)
        else:
            return self._simulate_generic(steps, dt)

    def _simulate_repressilator(self, steps: int, dt: float) -> List[Dict[str, float]]:
        """Repressilator: 3-gene ring oscillator."""
        a, b, c = 5.0, 2.0, 8.0
        alpha, beta = 50.0, 2.0
        results = []
        for _ in range(steps):
            da = -a + alpha / (1 + c**beta)
            db = -b + alpha / (1 + a**beta)
            dc = -c + alpha / (1 + b**beta)
            a = max(0.0, a + da * dt)
            b = max(0.0, b + db * dt)
            c = max(0.0, c + dc * dt)
            results.append({"lacI": a, "tetR": b, "cI": c})
        return results

    def _simulate_toggle(self, steps: int, dt: float) -> List[Dict[str, float]]:
        """Toggle switch: bistable mutual repression."""
        u, v = 3.0, 1.0
        alpha1, alpha2, beta, gamma = 10.0, 10.0, 2.0, 2.0
        results = []
        for _ in range(steps):
            du = alpha1 / (1 + v**beta) - u
            dv = alpha2 / (1 + u**gamma) - v
            u = max(0.0, u + du * dt)
            v = max(0.0, v + dv * dt)
            results.append({"geneA": u, "geneB": v})
        return results

    def _simulate_oscillator(self, steps: int, dt: float) -> List[Dict[str, float]]:
        """Simple negative feedback oscillator."""
        x = 1.0
        k_prod, k_deg, k_act, n = 2.0, 1.0, 5.0, 3
        results = []
        for i in range(steps):
            inhibition = k_act / (1 + x**n)
            dx = (k_prod * inhibition - k_deg * x) * dt
            x = max(0.0, x + dx)
            results.append({"output": x})
        return results

    def _simulate_generic(self, steps: int, dt: float) -> List[Dict[str, float]]:
        """Generic circuit simulation with mass-action kinetics."""
        species: Dict[str, float] = {
            f"s{i}": random.uniform(0.1, 5.0) for i in range(min(3, len(self.genes)))
        }
        if not species:
            species = {"s0": 1.0}
        results = []
        for _ in range(steps):
            new_species = {}
            for name, conc in species.items():
                d = (random.uniform(0.5, 2.0) - 0.5 * conc) * dt
                new_species[name] = max(0.0, conc + d)
            species = new_species
            results.append(dict(species))
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "circuit_type": self.circuit_type.value,
            "gene_count": len(self.genes),
            "input_species": self.input_species,
            "output_species": self.output_species,
        }


@dataclass
class MetabolicNetwork:
    """A simplified metabolic network."""

    id: str = ""
    metabolites: List[str] = field(default_factory=list)
    reactions: List[Dict[str, Any]] = field(default_factory=list)
    fluxes: Dict[str, float] = field(default_factory=dict)
    biomass_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def add_reaction(
        self,
        name: str,
        substrates: Dict[str, float],
        products: Dict[str, float],
        reversible: bool = True,
        max_flux: float = 10.0,
    ) -> None:
        """Add a reaction to the network."""
        self.reactions.append(
            {
                "name": name,
                "substrates": substrates,
                "products": products,
                "reversible": reversible,
                "max_flux": max_flux,
            }
        )
        for m in list(substrates.keys()) + list(products.keys()):
            if m not in self.metabolites:
                self.metabolites.append(m)

    def simulate_flux(self, steps: int = 100) -> Dict[str, float]:
        """Simulate metabolic flux analysis."""
        self.fluxes = {}
        for rxn in self.reactions:
            base_flux = rxn["max_flux"] * random.uniform(0.3, 0.9)
            substrate_limit = min(
                1.0 / abs(s) if s != 0 else 10.0 for s in rxn["substrates"].values()
            )
            self.fluxes[rxn["name"]] = min(base_flux, substrate_limit * rxn["max_flux"])

        self.biomass_rate = sum(self.fluxes.values()) / max(len(self.fluxes), 1) * 0.1
        return self.fluxes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "metabolite_count": len(self.metabolites),
            "reaction_count": len(self.reactions),
            "biomass_rate": self.biomass_rate,
            "fluxes": self.fluxes,
        }


@dataclass
class SyntheticOrganism:
    """A synthetic organism with genome and phenotype."""

    id: str = ""
    name: str = ""
    genome: List[Gene] = field(default_factory=list)
    circuits: List[GeneticCircuit] = field(default_factory=list)
    metabolism: Optional[MetabolicNetwork] = None
    state: OrganismState = OrganismState.EMBRYONIC
    fitness: float = 0.0
    age: int = 0
    generation: int = 0
    phenotype: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def evaluate_fitness(self) -> float:
        """Evaluate organism fitness based on phenotype."""
        circuit_score = sum(
            len(c.genes) * c.genes[0].expression_level if c.genes else 0.5 for c in self.circuits
        )
        gene_score = sum(g.expression_level * g.promoter_strength for g in self.genome)
        metabolic_score = self.metabolism.biomass_rate if self.metabolism else 0.5
        stability = 1.0 / (1.0 + abs(circuit_score - gene_score) * 0.01)

        self.fitness = (gene_score + circuit_score * 0.5 + metabolic_score * 10.0) * stability
        self.phenotype = {
            "circuit_score": circuit_score,
            "gene_score": gene_score,
            "metabolic_score": metabolic_score,
            "stability": stability,
            "total_fitness": self.fitness,
        }
        return self.fitness

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "fitness": self.fitness,
            "age": self.age,
            "generation": self.generation,
            "gene_count": len(self.genome),
            "circuit_count": len(self.circuits),
            "phenotype": self.phenotype,
        }


@dataclass
class Population:
    """A population of synthetic organisms."""

    id: str = ""
    organisms: List[SyntheticOrganism] = field(default_factory=list)
    generation: int = 0
    selection_pressure: SelectionPressure = SelectionPressure.FITNESS
    mutation_rate: float = 0.01
    crossover_rate: float = 0.7
    carrying_capacity: int = 100
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def select(self) -> List[SyntheticOrganism]:
        """Selection based on configured pressure."""
        if not self.organisms:
            return []

        if self.selection_pressure == SelectionPressure.FITNESS:
            total = sum(o.fitness for o in self.organisms)
            if total == 0:
                return random.sample(self.organisms, min(2, len(self.organisms)))
            weights = [o.fitness / total for o in self.organisms]
            return random.choices(self.organisms, weights=weights, k=min(2, len(self.organisms)))

        elif self.selection_pressure == SelectionPressure.TOURNAMENT:
            k = min(3, len(self.organisms))
            tournament = random.sample(self.organisms, k)
            tournament.sort(key=lambda o: o.fitness, reverse=True)
            return tournament[:2]

        elif self.selection_pressure == SelectionPressure.NEUTRAL:
            return random.sample(self.organisms, min(2, len(self.organisms)))

        else:
            return random.sample(self.organisms, min(2, len(self.organisms)))

    def crossover(
        self, parent1: SyntheticOrganism, parent2: SyntheticOrganism
    ) -> SyntheticOrganism:
        """Genetic crossover between two organisms."""
        child_genome = []
        min_genes = min(len(parent1.genome), len(parent2.genome))
        for i in range(min_genes):
            child_genome.append(parent1.genome[i] if random.random() < 0.5 else parent2.genome[i])

        for i in range(min_genes, len(parent1.genome)):
            if random.random() < 0.5:
                child_genome.append(parent1.genome[i])
        for i in range(min_genes, len(parent2.genome)):
            if random.random() < 0.5:
                child_genome.append(parent2.genome[i])

        child_circuits = parent1.circuits if random.random() < 0.5 else parent2.circuits

        child = SyntheticOrganism(
            name=f"org_gen{self.generation + 1}_{len(self.organisms)}",
            genome=child_genome,
            circuits=child_circuits,
            metabolism=parent1.metabolism if random.random() < 0.5 else parent2.metabolism,
            state=OrganismState.EMBRYONIC,
            generation=self.generation + 1,
        )

        if random.random() < self.mutation_rate:
            for gene in child.genome:
                if random.random() < self.mutation_rate:
                    mut_type = random.choice(list(MutationType))
                    idx = child.genome.index(gene)
                    child.genome[idx] = gene.mutate(mut_type)

        child.evaluate_fitness()
        return child

    def evolve(self, generations: int = 10) -> Dict[str, Any]:
        """Evolve the population for given generations."""
        history = []
        for gen in range(generations):
            self.generation += 1

            for org in self.organisms:
                org.evaluate_fitness()
                org.age += 1
                if org.state == OrganismState.EMBRYONIC:
                    org.state = OrganismState.GROWING
                elif org.state == OrganismState.GROWING:
                    org.state = OrganismState.MATURE
                elif org.age > 50:
                    org.state = OrganismState.SENESCING

            self.organisms.sort(key=lambda o: o.fitness, reverse=True)
            survivors = self.organisms[: self.carrying_capacity]

            new_organisms = list(survivors[: max(2, self.carrying_capacity // 4)])
            while len(new_organisms) < self.carrying_capacity:
                parents = self.select()
                if len(parents) >= 2 and random.random() < self.crossover_rate:
                    child = self.crossover(parents[0], parents[1])
                    new_organisms.append(child)
                elif parents:
                    clone_genome = [
                        g.mutate(MutationType.POINT) if random.random() < self.mutation_rate else g
                        for g in parents[0].genome
                    ]
                    clone = SyntheticOrganism(
                        name=f"org_gen{self.generation}_{len(new_organisms)}",
                        genome=clone_genome,
                        circuits=parents[0].circuits,
                        generation=self.generation,
                    )
                    clone.evaluate_fitness()
                    new_organisms.append(clone)

            self.organisms = new_organisms

            fitnesses = [o.fitness for o in self.organisms]
            history.append(
                {
                    "generation": self.generation,
                    "avg_fitness": sum(fitnesses) / len(fitnesses) if fitnesses else 0,
                    "max_fitness": max(fitnesses) if fitnesses else 0,
                    "min_fitness": min(fitnesses) if fitnesses else 0,
                    "population_size": len(self.organisms),
                }
            )

        return {
            "final_generation": self.generation,
            "history": history,
            "population_size": len(self.organisms),
        }

    def to_dict(self) -> Dict[str, Any]:
        fitnesses = [o.fitness for o in self.organisms]
        return {
            "id": self.id,
            "generation": self.generation,
            "population_size": len(self.organisms),
            "avg_fitness": sum(fitnesses) / len(fitnesses) if fitnesses else 0,
            "max_fitness": max(fitnesses) if fitnesses else 0,
            "selection_pressure": self.selection_pressure.value,
        }


# ─── Service ────────────────────────────────────────────────────────────


class BioSyntheticEvolutionService:
    """Main service for bio-synthetic evolution."""

    def __init__(self, default_dimension: int = 10000):
        self.default_dimension = default_dimension
        self.organisms: Dict[str, SyntheticOrganism] = {}
        self.populations: Dict[str, Population] = {}
        self._initialized = False

    def initialize(self) -> Dict[str, Any]:
        """Initialize the service with a default population."""
        genes = [
            Gene(
                name=f"gene_{i}",
                function=random.choice(list(GeneFunction)),
                expression_level=random.uniform(0.5, 2.0),
                promoter_strength=random.uniform(0.3, 1.0),
            )
            for i in range(10)
        ]

        # circuits = [  # noqa: F841
        #     GeneticCircuit(name="repressilator", circuit_type=CircuitType.REPRESSILATOR, genes=genes[:3]),
        #     GeneticCircuit(name="toggle_switch", circuit_type=CircuitType.TOGGLE_SWITCH, genes=genes[3:5]),
        # ]

        metabolism = MetabolicNetwork()
        metabolism.add_reaction("glycolysis", {"glucose": -1.0}, {"pyruvate": 2.0, "ATP": 2.0})
        metabolism.add_reaction(
            "tca_cycle", {"pyruvate": -1.0}, {"CO2": 3.0, "ATP": 1.0, "NADH": 4.0}
        )
        metabolism.add_reaction(
            "oxidative_phosphorylation", {"NADH": -1.0, "O2": -0.5}, {"ATP": 2.5, "H2O": 1.0}
        )
        metabolism.simulate_flux()

        organisms = []
        for i in range(20):
            org = SyntheticOrganism(
                name=f"ancestor_{i}",
                genome=[
                    Gene(
                        name=f"gene_{j}_{i}",
                        function=random.choice(list(GeneFunction)),
                        expression_level=random.uniform(0.5, 2.0),
                        promoter_strength=random.uniform(0.3, 1.0),
                    )
                    for j in range(random.randint(5, 15))
                ],
                circuits=[
                    GeneticCircuit(
                        name=f"circuit_{i}_{k}",
                        circuit_type=random.choice(list(CircuitType)),
                        genes=genes[: random.randint(2, 5)],
                    )
                    for k in range(random.randint(1, 3))
                ],
                metabolism=MetabolicNetwork(),
                generation=0,
            )
            if org.metabolism is not None:
                org.metabolism.add_reaction(
                    "glycolysis", {"glucose": -1.0}, {"pyruvate": 2.0, "ATP": 2.0}
                )
                org.metabolism.simulate_flux()
            org.evaluate_fitness()
            org.state = OrganismState.MATURE
            organisms.append(org)
            self.organisms[org.id] = org

        pop = Population(
            organisms=organisms,
            generation=0,
            carrying_capacity=50,
            mutation_rate=0.02,
        )
        self.populations[pop.id] = pop
        self._initialized = True

        return {
            "status": "initialized",
            "initial_organisms": len(organisms),
            "population_id": pop.id,
        }

    def create_organism(
        self, name: str, gene_count: int = 10, circuit_count: int = 1
    ) -> Dict[str, Any]:
        """Create a new synthetic organism."""
        genes = [
            Gene(
                name=f"{name}_gene_{i}",
                function=random.choice(list(GeneFunction)),
                expression_level=random.uniform(0.5, 2.0),
                promoter_strength=random.uniform(0.3, 1.0),
            )
            for i in range(gene_count)
        ]
        circuits = [
            GeneticCircuit(
                name=f"{name}_circuit_{i}",
                circuit_type=random.choice(list(CircuitType)),
                genes=genes[: random.randint(2, min(5, gene_count))],
            )
            for i in range(circuit_count)
        ]
        org = SyntheticOrganism(name=name, genome=genes, circuits=circuits)
        org.evaluate_fitness()
        self.organisms[org.id] = org
        return org.to_dict()

    def evolve_population(self, population_id: str, generations: int = 10) -> Dict[str, Any]:
        """Evolve a population for given generations."""
        pop = self.populations.get(population_id)
        if not pop:
            return {"error": f"Population {population_id} not found"}
        result = pop.evolve(generations)
        return result

    def simulate_circuit(self, circuit_type: str, steps: int = 100) -> List[Dict[str, float]]:
        """Simulate a genetic circuit."""
        ct = CircuitType(circuit_type)
        circuit = GeneticCircuit(circuit_type=ct)
        return circuit.simulate(steps)

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service": "bio_synthetic_evolution",
            "initialized": self._initialized,
            "total_organisms": len(self.organisms),
            "total_populations": len(self.populations),
            "population_ids": list(self.populations.keys()),
        }

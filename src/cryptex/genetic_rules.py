"""Genetic algorithm for evolving Cryptex threat detection rules."""

import copy
import random
import re
from dataclasses import dataclass

# Attack token vocabulary for pattern generation
_VOCAB: list[str] = [
    # SQL injection
    "union", "select", "insert", "drop", "delete", "update", "from", "where",
    "or", "and", "1=1", "--", ";--", "sleep(", "benchmark(", "xp_cmdshell",
    # XSS
    "<script", "alert(", "onerror=", "onload=", "javascript:", "eval(",
    "document.cookie", "innerHTML", "<iframe", "src=",
    # Path traversal
    "../", "..\\", "%2e%2e", "%2f", "/etc/passwd", "c:\\windows",
    "..%2f", "%252e",
    # Command injection
    ";ls", "|cat", "&&id", "`whoami`", "$(cmd)", "/bin/sh", "cmd.exe",
    "ping -c", "wget http", "curl http",
    # JWT attacks
    "alg:none", "hs256", "rs256", "eyj", "none\"", "algorithm\":\"none",
    # SSRF
    "169.254.169.254", "metadata.google", "localhost:", "127.0.0.1:",
    "file://", "dict://", "gopher://", "0x7f",
]

_MUTATE_OPS = ("insert", "delete", "replace")


@dataclass
class Rule:
    pattern: str
    weight: float
    tags: list[str]
    fitness: float = 0.0
    generation: int = 0


class GeneticRuleEvolver:
    def __init__(
        self,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
        elite_fraction: float = 0.1,
    ) -> None:
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_fraction = elite_fraction
        self._population: list[Rule] = []
        self._generation: int = 0

    def _random_pattern(self) -> str:
        n_tokens = random.randint(1, 4)
        tokens = random.choices(_VOCAB, k=n_tokens)
        # Build a simple alternation pattern from the tokens
        escaped = [re.escape(t) for t in tokens]
        if len(escaped) == 1:
            return escaped[0]
        return "(?:" + "|".join(escaped) + ")"

    def _fitness(
        self,
        rule: Rule,
        benign_samples: list[str],
        malicious_samples: list[str],
    ) -> float:
        try:
            rx = re.compile(rule.pattern, re.IGNORECASE)
        except re.error:
            return -1.0

        true_positives = sum(1 for s in malicious_samples if rx.search(s))
        false_positives = sum(1 for s in benign_samples if rx.search(s))

        score = (true_positives / max(1, len(malicious_samples))) - 0.5 * (
            false_positives / max(1, len(benign_samples))
        )
        return round(score * rule.weight, 6)

    def _crossover(self, r1: Rule, r2: Rule) -> Rule:
        p1, p2 = r1.pattern, r2.pattern
        mid1 = max(1, len(p1) // 2)
        mid2 = max(1, len(p2) // 2)
        new_pattern = p1[:mid1] + p2[mid2:]
        new_weight = (r1.weight + r2.weight) / 2.0
        combined_tags = list(set(r1.tags) | set(r2.tags))
        return Rule(
            pattern=new_pattern,
            weight=new_weight,
            tags=combined_tags,
            generation=self._generation,
        )

    def _mutate(self, rule: Rule) -> Rule:
        mutated = copy.deepcopy(rule)
        op = random.choice(_MUTATE_OPS)
        tokens = _VOCAB

        if op == "insert":
            new_token = re.escape(random.choice(tokens))
            pos = random.randint(0, len(mutated.pattern))
            mutated.pattern = (
                mutated.pattern[:pos] + new_token + mutated.pattern[pos:]
            )
        elif op == "delete" and len(mutated.pattern) > 3:
            pos = random.randint(0, max(0, len(mutated.pattern) - 2))
            length = random.randint(1, min(5, len(mutated.pattern) - pos))
            mutated.pattern = (
                mutated.pattern[:pos] + mutated.pattern[pos + length:]
            )
        elif op == "replace":
            new_pattern = self._random_pattern()
            mutated.pattern = new_pattern

        mutated.generation = self._generation
        return mutated

    def _initialise_population(self) -> list[Rule]:
        pop: list[Rule] = []
        for _ in range(self.population_size):
            pattern = self._random_pattern()
            weight = random.uniform(0.5, 2.0)
            tag_sample = random.sample(
                ["sqli", "xss", "traversal", "cmdinj", "jwt", "ssrf"],
                k=random.randint(1, 3),
            )
            pop.append(
                Rule(pattern=pattern, weight=weight, tags=tag_sample, generation=0)
            )
        return pop

    def _select_parents(self, population: list[Rule]) -> tuple[Rule, Rule]:
        # Tournament selection (k=3)
        def tournament(k: int = 3) -> Rule:
            contestants = random.sample(population, min(k, len(population)))
            return max(contestants, key=lambda r: r.fitness)

        return tournament(), tournament()

    def evolve(
        self,
        benign: list[str],
        malicious: list[str],
        generations: int = 20,
    ) -> list[Rule]:
        if not self._population:
            self._population = self._initialise_population()

        for gen in range(generations):
            self._generation = gen

            # Evaluate fitness
            for rule in self._population:
                rule.fitness = self._fitness(rule, benign, malicious)

            # Sort descending by fitness
            self._population.sort(key=lambda r: r.fitness, reverse=True)

            elite_count = max(1, int(self.population_size * self.elite_fraction))
            new_population: list[Rule] = self._population[:elite_count]

            while len(new_population) < self.population_size:
                p1, p2 = self._select_parents(self._population)

                if random.random() < self.crossover_rate:
                    child = self._crossover(p1, p2)
                else:
                    child = copy.deepcopy(random.choice([p1, p2]))

                if random.random() < self.mutation_rate:
                    child = self._mutate(child)

                child.fitness = self._fitness(child, benign, malicious)
                new_population.append(child)

            self._population = new_population

        self._population.sort(key=lambda r: r.fitness, reverse=True)
        return list(self._population)

    def seed_from_cve(self, cve_id: str, payload_samples: list[str]) -> None:
        """Add initial rules seeded from CVE payload samples."""
        tag = cve_id.lower().replace("-", "_")
        for sample in payload_samples:
            # Extract up to 3-token subsequences from the sample as patterns
            words = sample.split()
            for i in range(min(len(words), 5)):
                token = words[i].strip()
                if not token:
                    continue
                pattern = re.escape(token[:40])
                rule = Rule(
                    pattern=pattern,
                    weight=1.5,
                    tags=[tag, "cve_seeded"],
                    generation=0,
                )
                self._population.append(rule)

        # Trim to population_size if overgrown
        if len(self._population) > self.population_size * 2:
            self._population = self._population[: self.population_size * 2]

    def export_rules(self) -> list[dict]:
        """Export current population as a list of dicts for JSON serialisation."""
        return [
            {
                "pattern": r.pattern,
                "weight": r.weight,
                "tags": r.tags,
                "fitness": r.fitness,
                "generation": r.generation,
            }
            for r in self._population
        ]

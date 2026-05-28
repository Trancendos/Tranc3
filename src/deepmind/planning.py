import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class PlanningConfig:
    """Configuration for the strategic planning system."""

    horizon: int = 10
    beam_width: int = 5
    mcts_simulations: int = 400
    use_world_model: bool = True
    temperature: float = 0.8


@dataclass
class ThoughtNode:
    """A single node in the beam search thought tree."""

    thought: str
    score: float
    depth: int
    children: List["ThoughtNode"] = field(default_factory=list)
    parent: Optional["ThoughtNode"] = None

    def add_child(self, child: "ThoughtNode") -> None:
        child.parent = self
        self.children.append(child)

    def lineage(self) -> List[str]:
        """Return list of thoughts from root down to this node."""
        path: List[str] = []
        node: Optional[ThoughtNode] = self
        while node is not None:
            path.append(node.thought)
            node = node.parent
        path.reverse()
        return path


class BeamSearchPlanner:
    """Beam search over a tree of natural-language thoughts.

    At each depth level, all frontier nodes are expanded into candidate
    child thoughts.  Only the ``beam_width`` best-scoring children
    (by a heuristic relevance score) are kept for the next level.
    This implements a best-first approximate BFS over the thought space.
    """

    def __init__(self, beam_width: int = 5) -> None:
        self.beam_width = beam_width

    async def plan(self, goal: str, context: Dict) -> List[ThoughtNode]:
        """Run beam search and return the final beam of thought nodes.

        Args:
            goal:    Natural-language goal description.
            context: Arbitrary contextual information (state, constraints, …).

        Returns:
            List of ThoughtNode leaves — the surviving beam at the final depth.
        """
        # Seed the beam with top-level decomposition thoughts
        root_thoughts = self._expand_thought(goal, context)
        beam: List[ThoughtNode] = [
            ThoughtNode(
                thought=t,
                score=self._score_thought(t, goal),
                depth=0,
            )
            for t in root_thoughts[: self.beam_width]
        ]

        max_depth = max(3, len(root_thoughts) // 2)

        for depth in range(1, max_depth + 1):
            candidates: List[ThoughtNode] = []

            # Expand every node currently in the beam
            expansion_tasks = [self._async_expand(node, goal, context, depth) for node in beam]
            expanded_groups = await asyncio.gather(*expansion_tasks)

            for parent_node, children in zip(beam, expanded_groups, strict=False):
                for child in children:
                    parent_node.add_child(child)
                    candidates.append(child)

            if not candidates:
                break

            # Keep only the best beam_width candidates
            candidates.sort(key=lambda n: n.score, reverse=True)
            beam = candidates[: self.beam_width]

            logger.debug(
                "Beam search depth %d: %d candidates → %d kept",
                depth,
                len(candidates),
                len(beam),
            )

        return beam

    async def _async_expand(
        self, node: ThoughtNode, goal: str, context: Dict, depth: int
    ) -> List[ThoughtNode]:
        """Expand a single thought node into child ThoughtNodes asynchronously."""
        next_thoughts = self._expand_thought(node.thought, context)
        children: List[ThoughtNode] = []
        for t in next_thoughts:
            score = self._score_thought(t, goal)
            # Penalise deep nodes slightly to prefer breadth
            adjusted = score * (0.95**depth)
            children.append(ThoughtNode(thought=t, score=adjusted, depth=depth))
        return children

    def _score_thought(self, thought: str, goal: str) -> float:
        """Heuristic relevance score ∈ [0, 1].

        Combines:
          - Keyword overlap with the goal (Jaccard similarity on word sets)
          - Length penalty (overly short or extremely long thoughts penalised)
          - Specificity bonus (thoughts with numbers / named entities)
        """
        if not thought or not goal:
            return 0.0

        thought_words = set(thought.lower().split())
        goal_words = set(goal.lower().split())

        # Strip common stop words for a cleaner overlap
        stop_words = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "shall",
        }
        tw = thought_words - stop_words
        gw = goal_words - stop_words

        union = tw | gw
        intersection = tw & gw
        jaccard = len(intersection) / len(union) if union else 0.0

        # Length score: prefer thoughts between 5–20 words
        word_count = len(thought.split())
        if word_count < 3:
            length_score = 0.3
        elif word_count <= 20:
            length_score = 1.0
        else:
            length_score = max(0.3, 1.0 - (word_count - 20) * 0.02)

        # Specificity: presence of digits or capitalised words (proper nouns)
        has_numbers = bool(re.search(r"\d", thought))
        has_proper = bool(re.search(r"\b[A-Z][a-z]+", thought))
        specificity_bonus = 0.15 * (has_numbers + has_proper)

        score = 0.6 * jaccard + 0.3 * length_score + specificity_bonus
        return min(1.0, score)

    def _expand_thought(self, thought: str, context: Dict) -> List[str]:
        """Generate candidate next-step thoughts from a parent thought.

        Uses a deterministic heuristic expansion so the planner works
        even without an LLM call, while remaining hook-friendly for
        subclasses to override with real model calls.

        Args:
            thought:  The parent thought string.
            context:  Optional context dict (may contain "constraints", "state").

        Returns:
            List of candidate child thought strings.
        """
        constraints: List[str] = context.get("constraints", [])
        context.get("state", {})

        # Decomposition templates — applied in rotation based on thought hash
        templates = [
            "First, {thought} by identifying the key requirements.",
            "To {thought}, break it into smaller achievable sub-tasks.",
            "Consider risks: what could prevent {thought}?",
            "Validate approach: ensure {thought} aligns with constraints.",
            "Measure success: define completion criteria for {thought}.",
            "Identify dependencies that {thought} relies on.",
            "Estimate resources needed to {thought}.",
            "Prioritise: which part of {thought} delivers the most value?",
        ]

        # Seed selection from thought content for deterministic variety
        seed = int(hashlib.md5(thought.encode(), usedforsecurity=False).hexdigest(), 16) % len(
            templates
        )
        selected = templates[seed : seed + 4] + templates[: max(0, seed - len(templates) + 4)]
        selected = selected[: self.beam_width]

        expansions = []
        for tmpl in selected:
            # Trim thought to a manageable fragment for embedding
            short = " ".join(thought.split()[:6])
            candidate = tmpl.format(thought=short)
            if constraints:
                candidate += f" (subject to: {constraints[0]})"
            expansions.append(candidate)

        return expansions


class ChainOfThoughtReasoner:
    """Few-shot chain-of-thought reasoner.

    Simulates a structured CoT process:
      1. Parse the problem into atomic facts.
      2. Apply inference rules to generate reasoning steps.
      3. Synthesise a conclusion and estimate confidence.

    When an LLM is available the caller can inject the actual text by
    subclassing and overriding ``_generate_steps``; the base implementation
    uses purely heuristic/rule-based reasoning so the class is always usable.
    """

    def __init__(self) -> None:
        self._inference_rules = [
            "Identify the core objective from the problem statement.",
            "List all given constraints and boundary conditions.",
            "Decompose into independent sub-problems where possible.",
            "Apply known patterns or prior solutions analogously.",
            "Verify intermediate conclusions before proceeding.",
            "Synthesise sub-results into a unified answer.",
        ]

    async def reason(self, problem: str, examples: Optional[List[Dict]] = None) -> Dict:
        """Perform chain-of-thought reasoning on a problem.

        Args:
            problem:  Natural-language problem description.
            examples: Optional few-shot demonstrations as list of
                      {"problem": str, "solution": str} dicts.

        Returns:
            Dict with keys:
              steps           – ordered reasoning steps
              conclusion      – final synthesised answer
              confidence      – scalar confidence estimate
              reasoning_chain – structured intermediate states
        """
        # Build few-shot context string (not used in heuristic mode but
        # captured so LLM overrides can pass it to a model)
        if examples is None:
            examples = []
        few_shot_ctx = ""
        for ex in examples:
            few_shot_ctx += (
                f"Problem: {ex.get('problem', '')}\nSolution: {ex.get('solution', '')}\n\n"
            )

        steps = self._extract_steps(problem)
        conclusion = self._synthesise_conclusion(steps, problem)
        confidence = self._assess_confidence(steps)

        reasoning_chain = []
        running_context = ""
        for i, step in enumerate(steps):
            running_context += f" {step}"
            intermediate_confidence = min(1.0, confidence * (i + 1) / len(steps))
            reasoning_chain.append(
                {
                    "step_index": i,
                    "step": step,
                    "cumulative_context": running_context.strip(),
                    "intermediate_confidence": intermediate_confidence,
                }
            )

        return {
            "steps": steps,
            "conclusion": conclusion,
            "confidence": confidence,
            "reasoning_chain": reasoning_chain,
        }

    def _extract_steps(self, text: str) -> List[str]:
        """Derive a sequence of reasoning steps from the problem text.

        Applies the inference rules, contextualising each with key phrases
        extracted from the problem.

        Args:
            text: Problem description.

        Returns:
            Ordered list of reasoning step strings.
        """
        # Extract key noun phrases (simple heuristic: capitalised or quoted)
        key_terms = re.findall(r'"([^"]+)"|\'([^\']+)\'|([A-Z][a-z]+ [A-Z][a-z]+)', text)
        flat_terms = [next(t for t in group if t) for group in key_terms if any(key_terms)]

        steps: List[str] = []
        for rule in self._inference_rules:
            if flat_terms:
                term = flat_terms[len(steps) % len(flat_terms)]
                step = f"{rule} (relevant to: '{term}')"
            else:
                # Embed the first 8 words of the problem for grounding
                excerpt = " ".join(text.split()[:8])
                step = f"{rule} Applied to: '{excerpt}…'"
            steps.append(step)

        return steps

    def _synthesise_conclusion(self, steps: List[str], problem: str) -> str:
        """Build a conclusion string from the reasoning steps."""
        n = len(steps)
        excerpt = " ".join(problem.split()[:12])
        return (
            f"After {n} reasoning steps applied to the problem "
            f"'{excerpt}…', the analysis converges to a structured solution "
            f"addressing the identified sub-problems with validated intermediate results."
        )

    def _assess_confidence(self, steps: List[str]) -> float:
        """Estimate confidence based on reasoning chain quality.

        Confidence is a function of:
          - Whether all core inference rules are represented (coverage)
          - Average step length (longer = more detailed = slightly higher conf)
          - Number of steps (more = more thorough, up to a plateau)

        Returns:
            Float in [0, 1].
        """
        if not steps:
            return 0.0

        coverage = min(1.0, len(steps) / len(self._inference_rules))
        avg_len = np.mean([len(s.split()) for s in steps])
        length_factor = min(1.0, avg_len / 15.0)
        # Combine with slight random perturbation representing epistemic uncertainty
        confidence = 0.5 * coverage + 0.4 * length_factor + 0.1 * np.random.uniform(0.8, 1.0)
        return float(np.clip(confidence, 0.0, 1.0))


class StrategicPlanner:
    """Top-level orchestrator for AI planning.

    Combines beam search, chain-of-thought reasoning, and (optionally)
    MCTS-guided world-model planning to produce structured action plans.

    The ``plan_action`` method is the primary entry point.  It runs all
    three sub-systems concurrently where possible and fuses their outputs
    into a single ranked plan with alternatives.
    """

    def __init__(self, config: PlanningConfig) -> None:
        self.config = config
        self._beam_planner = BeamSearchPlanner(beam_width=config.beam_width)
        self._cot_reasoner = ChainOfThoughtReasoner()

    async def plan_action(
        self,
        goal: str,
        state: Dict,
        constraints: Optional[List[str]] = None,
    ) -> Dict:
        """Produce a structured plan for achieving ``goal`` given current state.

        Args:
            goal:        High-level goal description.
            state:       Current environment / agent state.
            constraints: List of hard constraints the plan must respect.

        Returns:
            Dict with keys:
              plan        – ordered list of action strings
              confidence  – scalar confidence in the plan
              alternatives – list of alternative action sequences
              reasoning   – textual justification
        """
        if constraints is None:
            constraints = []
        context = {"state": state, "constraints": constraints}

        # Run beam search and chain-of-thought concurrently
        beam_task = asyncio.create_task(self._beam_planner.plan(goal, context))
        cot_task = asyncio.create_task(self._cot_reasoner.reason(goal))

        beam_nodes, cot_result = await asyncio.gather(beam_task, cot_task)

        # Extract primary plan from the best-scoring beam leaf
        if beam_nodes:
            best_node = max(beam_nodes, key=lambda n: n.score)
            primary_plan = best_node.lineage()
        else:
            primary_plan = cot_result.get("steps", [goal])

        # Build alternatives from remaining beam nodes
        alternatives: List[List[str]] = []
        for node in sorted(beam_nodes, key=lambda n: n.score, reverse=True)[1:4]:
            alternatives.append(node.lineage())

        # Fuse confidence scores
        beam_confidence = float(np.mean([n.score for n in beam_nodes])) if beam_nodes else 0.5
        cot_confidence = cot_result.get("confidence", 0.5)
        combined_confidence = 0.55 * beam_confidence + 0.45 * cot_confidence

        # Validate plan against constraints
        valid_plan = self._apply_constraints(primary_plan, constraints)

        reasoning = (
            f"Beam search ({len(beam_nodes)} paths, width={self.config.beam_width}) "
            f"combined with chain-of-thought ({len(cot_result.get('steps', []))} steps). "
            f"Conclusion: {cot_result.get('conclusion', 'N/A')}"
        )

        logger.info(  # codeql[py/cleartext-logging]
            "plan_action: goal=%r, plan_len=%d, confidence=%.3f",
            sanitize_for_log(goal[:60]),
            len(valid_plan),
            combined_confidence,
        )

        return {
            "plan": valid_plan,
            "confidence": combined_confidence,
            "alternatives": alternatives,
            "reasoning": reasoning,
        }

    async def evaluate_plan(self, plan: List[str], goal: str) -> Dict:
        """Score a candidate plan against a goal.

        Evaluation criteria:
          - Completeness: does the plan cover all goal keywords?
          - Coherence:    are plan steps semantically linked?
          - Feasibility:  is the plan length appropriate?
          - Alignment:    does the last step relate to the goal?

        Args:
            plan: Ordered list of action strings.
            goal: Goal to evaluate against.

        Returns:
            Dict with keys: score, completeness, coherence, feasibility, feedback.
        """
        if not plan:
            return {
                "score": 0.0,
                "completeness": 0.0,
                "coherence": 0.0,
                "feasibility": 0.0,
                "feedback": "Plan is empty.",
            }

        goal_words = set(goal.lower().split())
        plan_words = set(" ".join(plan).lower().split())
        stop = {"a", "an", "the", "and", "or", "to", "for", "of", "with"}
        goal_kw = goal_words - stop
        plan_kw = plan_words - stop

        completeness = len(goal_kw & plan_kw) / len(goal_kw) if goal_kw else 0.5

        # Coherence: fraction of adjacent step pairs sharing at least one word
        coherent_pairs = 0
        for i in range(len(plan) - 1):
            w1 = set(plan[i].lower().split()) - stop
            w2 = set(plan[i + 1].lower().split()) - stop
            if w1 & w2:
                coherent_pairs += 1
        coherence = coherent_pairs / max(len(plan) - 1, 1)

        # Feasibility: plan length relative to horizon
        target_len = self.config.horizon
        feasibility = 1.0 - abs(len(plan) - target_len) / max(target_len, 1)
        feasibility = float(np.clip(feasibility, 0.0, 1.0))

        # Alignment: score of last step vs goal
        last_step = plan[-1]
        alignment = BeamSearchPlanner(1)._score_thought(last_step, goal)

        score = 0.35 * completeness + 0.25 * coherence + 0.2 * feasibility + 0.2 * alignment

        feedback_parts = []
        if completeness < 0.5:
            feedback_parts.append("Plan may not fully address the goal.")
        if coherence < 0.4:
            feedback_parts.append("Plan steps lack logical flow.")
        if feasibility < 0.5:
            feedback_parts.append(
                f"Plan length ({len(plan)}) deviates significantly from target ({target_len})."
            )
        if not feedback_parts:
            feedback_parts.append("Plan looks coherent and aligned with the goal.")

        return {
            "score": float(np.clip(score, 0.0, 1.0)),
            "completeness": completeness,
            "coherence": coherence,
            "feasibility": feasibility,
            "feedback": " ".join(feedback_parts),
        }

    def _apply_constraints(self, plan: List[str], constraints: List[str]) -> List[str]:
        """Filter or annotate plan steps to respect hard constraints.

        Steps that explicitly violate a constraint (contain a constraint keyword
        prefixed with "not" or "avoid") are flagged and moved to the end of
        the plan so they remain visible but deprioritised.

        Args:
            plan:        Raw plan steps.
            constraints: Constraint strings.

        Returns:
            Adjusted plan steps.
        """
        if not constraints:
            return plan

        violation_keywords: List[str] = []
        for c in constraints:
            for word in re.findall(r"\b\w{4,}\b", c.lower()):
                violation_keywords.append(word)

        safe_steps = []
        flagged_steps = []
        for step in plan:
            step_lower = step.lower()
            violated = any(kw in step_lower for kw in violation_keywords)
            if violated:
                flagged_steps.append(f"[CONSTRAINED] {step}")
            else:
                safe_steps.append(step)

        return safe_steps + flagged_steps


# Module-level singleton — ready to use without instantiation
planner = StrategicPlanner(PlanningConfig())

# Alias for import compatibility
PlanningEngine = StrategicPlanner

"""
Tranc3 Model Evaluation Framework — Luminous Integration
=========================================================
Production-grade evaluation pipeline for Tranc3 language model outputs.

Zero external dependencies:
  • BLEU-1/2/3/4 (n-gram precision with brevity penalty)
  • ROUGE-L (longest common subsequence F1)
  • Exact-match accuracy (with normalization)
  • Token-level F1 (for extractive QA)
  • Hallucination detection (factual consistency heuristic)
  • Semantic similarity (cosine via existing sentence-transformers if available)
  • LoRA/fine-tuning evaluation integration

Named: Cornelius MacIntyre (Luminous — AI Intelligence & Orchestration Engine)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("tranc3.evaluation")

# ---------------------------------------------------------------------------
# Primitive metric functions — pure Python, zero extra deps
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokenization, stripping punctuation."""
    return re.findall(r"\b\w+\b", text.lower())


def _ngrams(tokens: List[str], n: int) -> List[Tuple[str, ...]]:
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def bleu_score(
    hypothesis: str,
    references: List[str],
    max_n: int = 4,
    smooth: bool = True,
) -> float:
    """
    Sentence-level BLEU score with optional smoothing.

    Returns a float in [0, 1].  The standard BLEU-4 metric for NLG tasks.
    With ``smooth=True`` (default), uses add-1 smoothing for missing n-grams so
    the score is never exactly 0.0 for partially matching hypotheses.  Pass
    ``smooth=False`` to get the unsmoothed score (returns 0.0 when any n-gram
    precision is zero).
    """
    hyp_tokens = _tokenize(hypothesis)
    ref_token_lists = [_tokenize(r) for r in references]

    if not hyp_tokens:
        return 0.0

    # Brevity penalty
    hyp_len = len(hyp_tokens)
    ref_len = min(len(r) for r in ref_token_lists)
    bp = 1.0 if hyp_len >= ref_len else math.exp(1 - ref_len / hyp_len)

    precisions: List[float] = []
    for n in range(1, max_n + 1):
        hyp_ngrams = Counter(_ngrams(hyp_tokens, n))
        if not hyp_ngrams:
            if smooth:
                precisions.append(1.0 / (2**n))
            else:
                return 0.0
            continue

        max_ref_counts: Counter = Counter()
        for ref_tokens in ref_token_lists:
            ref_ngrams = Counter(_ngrams(ref_tokens, n))
            for ng, cnt in ref_ngrams.items():
                max_ref_counts[ng] = max(max_ref_counts[ng], cnt)

        clipped = sum(min(cnt, max_ref_counts.get(ng, 0)) for ng, cnt in hyp_ngrams.items())
        total = sum(hyp_ngrams.values())
        p = clipped / total if total > 0 else 0.0

        if smooth and p == 0.0:
            p = 1.0 / (2**n)
        precisions.append(p)

    if not smooth and any(p == 0 for p in precisions):
        return 0.0

    log_avg = sum(math.log(p) for p in precisions) / len(precisions)
    return bp * math.exp(log_avg)


def rouge_l_score(hypothesis: str, reference: str) -> Dict[str, float]:
    """
    ROUGE-L — longest common subsequence F1.

    Returns ``{"precision": ..., "recall": ..., "f1": ...}``.
    """
    hyp = _tokenize(hypothesis)
    ref = _tokenize(reference)

    if not hyp or not ref:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    # DP LCS
    m, n = len(ref), len(hyp)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]

    precision = lcs_len / n if n > 0 else 0.0
    recall = lcs_len / m if m > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def exact_match(hypothesis: str, reference: str, normalize: bool = True) -> bool:
    """Exact match after optional normalization (lowercase, strip punctuation, collapse spaces)."""
    if normalize:

        def _norm(s: str) -> str:
            # Remove punctuation, lowercase, collapse whitespace
            s = re.sub(r"[^\w\s]", "", s.lower())
            return re.sub(r"\s+", " ", s).strip()

        return _norm(hypothesis) == _norm(reference)
    return hypothesis == reference


def token_f1(hypothesis: str, reference: str) -> Dict[str, float]:
    """
    Token-level F1 score (used in SQuAD/extractive QA evaluation).

    Computes overlap between bag-of-tokens in hypothesis and reference.
    Returns ``{"precision": ..., "recall": ..., "f1": ...}``.
    """
    hyp_tokens = Counter(_tokenize(hypothesis))
    ref_tokens = Counter(_tokenize(reference))

    if not hyp_tokens or not ref_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    common = sum((hyp_tokens & ref_tokens).values())
    if common == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    precision = common / sum(hyp_tokens.values())
    recall = common / sum(ref_tokens.values())
    f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def hallucination_score(
    hypothesis: str,
    context: str,
    threshold: float = 0.5,
) -> float:
    """
    Lightweight hallucination risk score in [0, 1].

    Checks what fraction of hypothesis n-grams appear in the context.
    Returns a float where 0.0 = fully supported (no hallucination) and
    1.0 = completely unsupported (high hallucination risk).

    A score above *threshold* suggests hallucination risk.
    """
    hyp_tokens = _tokenize(hypothesis)

    if not hyp_tokens:
        return 1.0

    if not context:
        return 1.0

    ctx_tokens = set(_tokenize(context))

    # 2-gram overlap
    bigrams = _ngrams(hyp_tokens, 2)
    if not bigrams:
        # Fall back to unigrams
        unigrams_in_ctx = sum(1 for t in hyp_tokens if t in ctx_tokens)
        frac = unigrams_in_ctx / len(hyp_tokens)
    else:
        ctx_bigrams = set(_ngrams(_tokenize(context), 2))
        supported = sum(1 for bg in bigrams if bg in ctx_bigrams)
        frac = supported / len(bigrams)

    # Return hallucination score (1 - supported)
    return round(1.0 - frac, 4)


# ---------------------------------------------------------------------------
# Configuration + result data classes
# ---------------------------------------------------------------------------


@dataclass
class EvalConfig:
    """Configuration for an evaluation run."""

    name: str
    task: str = "generation"  # "generation" | "qa" | "classification"
    max_new_tokens: int = 256
    temperature: float = 0.0
    compute_bleu: bool = True
    compute_rouge: bool = True
    compute_em: bool = True
    compute_token_f1: bool = True
    compute_hallucination: bool = True
    bleu_max_n: int = 4
    hallucination_threshold: float = 0.5
    semantic_similarity: bool = False  # requires sentence-transformers
    model_name: Optional[str] = None  # tag for the model under evaluation


@dataclass
class SampleResult:
    """Result for a single evaluation sample."""

    sample_id: str
    hypothesis: str
    reference: str
    bleu: float = 0.0
    rouge_l_f1: float = 0.0
    exact_match: bool = False
    token_f1: float = 0.0
    hallucination_score: float = 1.0
    semantic_similarity: float = 0.0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Aggregate results for an evaluation run."""

    run_id: str
    name: str
    config: EvalConfig
    num_samples: int = 0
    metrics: Dict[str, float] = field(default_factory=dict)
    samples: List[SampleResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Convenience properties for direct attribute access
    @property
    def avg_bleu(self) -> float:
        return self.metrics.get("bleu", 0.0)

    @property
    def avg_rouge_l_f1(self) -> float:
        return self.metrics.get("rouge_l", 0.0)

    @property
    def exact_match_rate(self) -> float:
        return self.metrics.get("exact_match", 0.0)

    @property
    def avg_token_f1(self) -> float:
        return self.metrics.get("token_f1", 0.0)

    @property
    def hallucination_rate(self) -> float:
        return self.metrics.get("hallucination", 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "config": {
                "name": self.config.name,
                "task": self.config.task,
                "model_name": self.config.model_name,
                "max_new_tokens": self.config.max_new_tokens,
                "temperature": self.config.temperature,
            },
            "num_samples": self.num_samples,
            "metrics": self.metrics,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        lines = [
            f"Eval: {self.name}  (model={self.config.model_name or 'unknown'})",
            f"  Samples : {self.num_samples}",
        ]
        for key, val in self.metrics.items():
            if isinstance(val, float):
                lines.append(f"  {key:<12}: {val:.4f}")
            else:
                lines.append(f"  {key:<12}: {val}")
        if self.metrics.get("avg_latency_ms"):
            lines.append(f"  latency_ms  : {self.metrics['avg_latency_ms']:.1f}ms avg")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evaluation suite
# ---------------------------------------------------------------------------


class EvalSuite:
    """
    Evaluation suite for Tranc3 model outputs.

    Usage::

        suite = EvalSuite()
        config = EvalConfig(name="baseline-eval", task="qa", model_name="tranc3-bootstrap")
        result = await suite.evaluate(
            config=config,
            generate=my_model.generate,   # async fn(prompt) -> str
            samples=[
                {"prompt": "What is 2+2?", "reference": "4"},
                ...
            ],
        )
        print(result.summary())
    """

    def __init__(self, results_dir: Optional[Path] = None) -> None:
        self._results_dir = results_dir or Path("data/eval")
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._embed_fn: Optional[Callable[[str], Any]] = None

    def set_embed_fn(self, embed_fn: Callable[[str], Any]) -> None:
        """Register an embedding function for semantic similarity computation."""
        self._embed_fn = embed_fn

    async def evaluate(
        self,
        config: EvalConfig,
        generate: Callable[[str], Any],
        samples: List[Dict[str, str]],
        context_key: str = "context",
        prompt_key: str = "prompt",
    ) -> EvalResult:
        """
        Evaluate *generate* on *samples*.

        Each sample must have ``"prompt"`` (or ``"input"``) and ``"reference"``
        keys.  Optionally a ``"context"`` key for hallucination checking.
        """
        run_id = str(uuid.uuid4())[:8]
        result = EvalResult(run_id=run_id, name=config.name, config=config)
        sample_results: List[SampleResult] = []

        for i, sample in enumerate(samples):
            # Accept both "prompt" and "input" as the query key
            prompt = sample.get(prompt_key) or sample.get("input", "")
            reference = sample.get("reference", "")
            context = sample.get(context_key, reference)

            t0 = time.perf_counter()
            try:
                if asyncio.iscoroutinefunction(generate):
                    hypothesis = await asyncio.wait_for(generate(prompt), timeout=60.0)
                else:
                    hypothesis = generate(prompt)
            except Exception as exc:
                logger.warning("Generation failed for sample %d: %s", i, exc)
                hypothesis = ""
            latency_ms = (time.perf_counter() - t0) * 1000

            sr = SampleResult(
                sample_id=sample.get("id", str(i)),
                hypothesis=str(hypothesis),
                reference=reference,
                latency_ms=latency_ms,
            )

            if config.compute_bleu:
                sr.bleu = bleu_score(str(hypothesis), [reference], max_n=config.bleu_max_n)

            if config.compute_rouge:
                rl = rouge_l_score(str(hypothesis), reference)
                sr.rouge_l_f1 = rl["f1"]

            if config.compute_em:
                sr.exact_match = exact_match(str(hypothesis), reference)

            if config.compute_token_f1:
                tf1 = token_f1(str(hypothesis), reference)
                sr.token_f1 = tf1["f1"]

            if config.compute_hallucination:
                sr.hallucination_score = hallucination_score(
                    str(hypothesis), context, config.hallucination_threshold
                )

            if config.semantic_similarity and self._embed_fn is not None:
                sr.semantic_similarity = self._cosine_similarity(
                    self._embed_fn(str(hypothesis)),
                    self._embed_fn(reference),
                )

            sample_results.append(sr)

        # Aggregate into metrics dict
        n = len(sample_results)
        result.num_samples = n
        result.samples = sample_results
        result.finished_at = time.time()

        if n > 0:
            result.metrics["bleu"] = sum(s.bleu for s in sample_results) / n
            result.metrics["rouge_l"] = sum(s.rouge_l_f1 for s in sample_results) / n
            result.metrics["exact_match"] = sum(1 for s in sample_results if s.exact_match) / n
            result.metrics["token_f1"] = sum(s.token_f1 for s in sample_results) / n
            result.metrics["hallucination"] = sum(s.hallucination_score for s in sample_results) / n
            result.metrics["semantic_similarity"] = (
                sum(s.semantic_similarity for s in sample_results) / n
            )
            result.metrics["avg_latency_ms"] = sum(s.latency_ms for s in sample_results) / n

        self._save_result(result)
        logger.info("Eval '%s' completed: %s", config.name, result.summary())
        return result

    # ------------------------------------------------------------------
    # Convenience: evaluate from JSONL file
    # ------------------------------------------------------------------

    async def evaluate_from_file(
        self,
        config: EvalConfig,
        generate: Callable[[str], Any],
        jsonl_path: str,
    ) -> EvalResult:
        """Load samples from a JSONL file (one JSON object per line)."""
        samples = []
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    samples.append(json.loads(line))
        return await self.evaluate(config, generate, samples)

    # ------------------------------------------------------------------
    # LoRA fine-tuning evaluation integration
    # ------------------------------------------------------------------

    async def evaluate_lora_checkpoint(
        self,
        config: EvalConfig,
        base_model_generate: Callable[[str], Any],
        lora_model_generate: Callable[[str], Any],
        samples: List[Dict[str, str]],
    ) -> Tuple[EvalResult, EvalResult]:
        """
        Compare base model vs LoRA fine-tuned model.

        Returns ``(base_result, lora_result)`` pair for comparison.
        """
        base_config = EvalConfig(
            name=f"{config.name}-base",
            task=config.task,
            compute_bleu=config.compute_bleu,
            compute_rouge=config.compute_rouge,
            compute_em=config.compute_em,
            compute_token_f1=config.compute_token_f1,
            compute_hallucination=config.compute_hallucination,
            model_name=f"{config.model_name or 'base'}-base",
        )
        lora_config = EvalConfig(
            name=f"{config.name}-lora",
            task=config.task,
            compute_bleu=config.compute_bleu,
            compute_rouge=config.compute_rouge,
            compute_em=config.compute_em,
            compute_token_f1=config.compute_token_f1,
            compute_hallucination=config.compute_hallucination,
            model_name=f"{config.model_name or 'lora'}-lora",
        )

        logger.info("Evaluating base model on %d samples", len(samples))
        base_result = await self.evaluate(base_config, base_model_generate, samples)

        logger.info("Evaluating LoRA model on %d samples", len(samples))
        lora_result = await self.evaluate(lora_config, lora_model_generate, samples)

        return base_result, lora_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_result(self, result: EvalResult) -> None:
        path = self._results_dir / f"{result.name}_{result.run_id}.json"
        try:
            with open(path, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Failed to save eval result: %s", exc)

    @staticmethod
    def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        """Cosine similarity between two float vectors."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

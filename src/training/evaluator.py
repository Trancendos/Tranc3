"""
evaluator.py — Model evaluation and benchmarking for Tranc3 custom transformer.

Provides:
  - ModelEvaluator: comprehensive eval (perplexity, token accuracy, repetition rate,
    avg response length, generation diversity via distinct-n)
  - BenchmarkSuite: runnable benchmark set with JSON output
  - CLI: `python -m src.training.evaluator --checkpoint path/to/ckpt.pt`

Zero-cost: uses only stdlib + torch (no paid eval services).
All metrics follow open standards:
  - Perplexity: exp(cross-entropy loss)
  - Token accuracy: fraction of argmax predictions matching target
  - Distinct-1 / Distinct-2: diversity metrics (Li et al. 2016)
  - Repetition rate: fraction of output tokens already seen in the same generation
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metric dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EvalMetrics:
    """Metrics produced by a single evaluation pass."""

    # Core language-model metrics
    avg_loss: float = 0.0
    perplexity: float = 0.0
    token_accuracy: float = 0.0

    # Generation quality
    avg_response_length: float = 0.0
    repetition_rate: float = 0.0  # fraction of repeated tokens per generation
    distinct_1: float = 0.0  # unique unigrams / total unigrams
    distinct_2: float = 0.0  # unique bigrams / total bigrams

    # Meta
    num_batches: int = 0
    num_samples: int = 0
    eval_time_seconds: float = 0.0
    timestamp: str = ""


@dataclass
class BenchmarkResult:
    """Result of one named benchmark task."""

    name: str
    prompt: str
    output: str
    tokens_generated: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class BenchmarkReport:
    """Complete benchmark report."""

    model_path: str
    checkpoint_step: int = 0
    eval_metrics: Optional[EvalMetrics] = None
    benchmark_results: List[BenchmarkResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class ModelEvaluator:
    """
    Comprehensive evaluator for the Tranc3 custom transformer.

    Usage::

        evaluator = ModelEvaluator(model, val_loader, device)
        metrics = evaluator.run()
        print(f"PPL={metrics.perplexity:.2f}  Acc={metrics.token_accuracy:.3f}")
    """

    def __init__(
        self,
        model: Any,
        val_loader: Any,
        device: Any,
        max_batches: int = 100,
    ) -> None:
        self.model = model
        self.val_loader = val_loader
        self.device = device
        self.max_batches = max_batches

    def run(self) -> EvalMetrics:
        """Run full evaluation pass. Returns EvalMetrics."""
        try:
            import torch  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("torch not available — returning stub EvalMetrics")
            return EvalMetrics(timestamp=_now())

        metrics = EvalMetrics(timestamp=_now())
        start = time.monotonic()

        self.model.eval()
        total_loss = 0.0
        total_correct = 0
        total_tokens = 0
        n_batches = 0

        # For generation-quality metrics we collect tokens across all outputs
        all_output_tokens: List[List[int]] = []

        with torch.no_grad():
            for batch in self.val_loader:
                if n_batches >= self.max_batches:
                    break

                input_ids = batch["input_ids"].to(self.device)
                targets = batch["targets"].to(self.device)

                try:
                    logits, loss = self.model(input_ids, targets)
                except Exception as exc:
                    logger.warning("eval batch %d failed: %s", n_batches, exc)
                    continue

                total_loss += loss.item()

                # Token accuracy
                preds = logits.argmax(dim=-1)
                mask = targets != -100  # ignore padding / masked positions
                correct = (preds == targets)[mask].sum().item()
                tokens = mask.sum().item()
                total_correct += correct
                total_tokens += tokens

                # Collect predicted token sequences for diversity metrics
                for seq in preds.cpu().tolist():
                    all_output_tokens.append(seq)

                n_batches += 1

        self.model.train()
        metrics.num_batches = n_batches
        metrics.eval_time_seconds = round(time.monotonic() - start, 3)

        if n_batches == 0:
            return metrics

        metrics.avg_loss = total_loss / n_batches
        metrics.perplexity = round(math.exp(min(metrics.avg_loss, 20)), 4)
        metrics.token_accuracy = round(total_correct / max(total_tokens, 1), 4)

        # Generation-quality metrics from collected sequences
        if all_output_tokens:
            gq = _generation_quality(all_output_tokens)
            metrics.avg_response_length = gq["avg_length"]
            metrics.repetition_rate = gq["repetition_rate"]
            metrics.distinct_1 = gq["distinct_1"]
            metrics.distinct_2 = gq["distinct_2"]
            metrics.num_samples = len(all_output_tokens)

        return metrics


# ---------------------------------------------------------------------------
# Benchmark suite
# ---------------------------------------------------------------------------

# Default benchmark prompts covering core Tranc3 capabilities
DEFAULT_PROMPTS: List[Tuple[str, str]] = [
    ("greeting", "Hello, how are you?"),
    ("instruction_follow", "List three benefits of exercise."),
    ("code_gen", "Write a Python function that reverses a string."),
    ("reasoning", "If all cats are mammals and Whiskers is a cat, is Whiskers a mammal?"),
    ("summarisation", "Summarise: The Tranc3 platform is a zero-cost self-hosted AI system."),
    ("multilingual", "Translate 'good morning' to French."),
    ("factual", "What is the capital of France?"),
    ("creative", "Write a haiku about technology."),
]


class BenchmarkSuite:
    """
    Runs a set of generation benchmarks against a Tranc3 model.

    Usage::

        suite = BenchmarkSuite(model, tokenizer, device)
        report = suite.run(model_path="checkpoints/model_latest.pt", step=1000)
        suite.save(report, "logs/benchmark_report.json")
    """

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        device: Any,
        max_new_tokens: int = 128,
        prompts: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.prompts = prompts or DEFAULT_PROMPTS

    def run(
        self,
        model_path: str = "",
        step: int = 0,
        eval_metrics: Optional[EvalMetrics] = None,
    ) -> BenchmarkReport:
        """Run all benchmark prompts. Returns BenchmarkReport."""
        results: List[BenchmarkResult] = []

        for name, prompt in self.prompts:
            result = self._run_single(name, prompt)
            results.append(result)
            logger.info(
                "benchmark task=%s tokens=%d latency=%.0fms",
                name,
                result.tokens_generated,
                result.latency_ms,
            )

        report = BenchmarkReport(
            model_path=model_path,
            checkpoint_step=step,
            eval_metrics=eval_metrics,
            benchmark_results=results,
            generated_at=_now(),
        )
        report.summary = _summarise(report)
        return report

    def _run_single(self, name: str, prompt: str) -> BenchmarkResult:
        """Generate a response for one prompt and time it."""
        try:
            import torch  # type: ignore[import-untyped]
        except ImportError:
            return BenchmarkResult(name=name, prompt=prompt, output="", error="torch not available")

        t0 = time.monotonic()
        try:
            tokens = self.tokenizer.encode(prompt) if hasattr(self.tokenizer, "encode") else []
            if not tokens:
                tokens = [0]  # fallback single token

            input_ids = torch.tensor([tokens], dtype=torch.long, device=self.device)

            self.model.eval()
            with torch.no_grad():
                output_ids = self._greedy_generate(input_ids)
            self.model.train()

            output_tokens = output_ids[0].tolist()
            output_text = (
                self.tokenizer.decode(output_tokens)
                if hasattr(self.tokenizer, "decode")
                else str(output_tokens)
            )
            latency_ms = (time.monotonic() - t0) * 1000
            return BenchmarkResult(
                name=name,
                prompt=prompt,
                output=output_text,
                tokens_generated=len(output_tokens),
                latency_ms=round(latency_ms, 1),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning("benchmark %s failed: %s", name, exc)
            return BenchmarkResult(
                name=name,
                prompt=prompt,
                output="",
                latency_ms=round(latency_ms, 1),
                error=str(exc),
            )

    def _greedy_generate(self, input_ids: Any) -> Any:
        """Simple greedy decoding loop."""
        import torch  # type: ignore[import-untyped]

        generated = input_ids
        for _ in range(self.max_new_tokens):
            logits, _ = self.model(generated, None)
            next_token = logits[:, -1, :].argmax(dim=-1, keepdim=True)
            generated = torch.cat([generated, next_token], dim=1)
            # Stop on EOS token (id=2 by convention) or if model returns it
            if next_token.item() == 2:
                break
        return generated[:, input_ids.shape[1] :]  # return only generated tokens

    @staticmethod
    def save(report: BenchmarkReport, path: str) -> None:
        """Serialise report to JSON."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(report)
        out.write_text(json.dumps(data, indent=2, default=str))
        logger.info("benchmark report saved → %s", out)
        print(f"[Benchmark] Report saved → {out}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generation_quality(seqs: List[List[int]]) -> Dict[str, float]:
    """Compute diversity and repetition metrics over a batch of token sequences."""
    all_unigrams: List[int] = []
    all_bigrams: List[Tuple[int, int]] = []
    rep_rates: List[float] = []

    for seq in seqs:
        if not seq:
            continue
        all_unigrams.extend(seq)
        all_bigrams.extend(zip(seq, seq[1:], strict=False))

        # Repetition: tokens already seen earlier in this sequence
        seen: set = set()
        repeated = 0
        for tok in seq:
            if tok in seen:
                repeated += 1
            seen.add(tok)
        rep_rates.append(repeated / len(seq) if seq else 0.0)

    total_u = len(all_unigrams)
    total_b = len(all_bigrams)
    lengths = [len(s) for s in seqs]

    return {
        "avg_length": round(sum(lengths) / len(lengths), 2) if lengths else 0.0,
        "repetition_rate": round(sum(rep_rates) / len(rep_rates), 4) if rep_rates else 0.0,
        "distinct_1": round(len(set(all_unigrams)) / max(total_u, 1), 4),
        "distinct_2": round(len(set(all_bigrams)) / max(total_b, 1), 4),
    }


def _summarise(report: BenchmarkReport) -> Dict[str, Any]:
    """Build a human-readable summary from a BenchmarkReport."""
    successful = [r for r in report.benchmark_results if not r.error]
    failed = [r for r in report.benchmark_results if r.error]
    avg_latency = (
        sum(r.latency_ms for r in successful) / len(successful) if successful else 0.0
    )
    avg_tokens = (
        sum(r.tokens_generated for r in successful) / len(successful) if successful else 0.0
    )
    summary: Dict[str, Any] = {
        "tasks_run": len(report.benchmark_results),
        "tasks_passed": len(successful),
        "tasks_failed": len(failed),
        "avg_latency_ms": round(avg_latency, 1),
        "avg_tokens_generated": round(avg_tokens, 1),
    }
    if report.eval_metrics:
        summary["perplexity"] = report.eval_metrics.perplexity
        summary["token_accuracy"] = report.eval_metrics.token_accuracy
        summary["distinct_1"] = report.eval_metrics.distinct_1
        summary["distinct_2"] = report.eval_metrics.distinct_2
    return summary


def _now() -> str:
    import datetime

    return datetime.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Tranc3 model evaluation & benchmark CLI")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to .pt checkpoint")
    parser.add_argument(
        "--output",
        type=str,
        default="logs/benchmark_report.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--max-new-tokens", type=int, default=128, help="Max tokens to generate per benchmark"
    )
    parser.add_argument(
        "--max-batches", type=int, default=50, help="Max validation batches for eval metrics"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        import torch

        from src.core.advanced_model import AdvancedTransformerModel
        from src.training.dataset import ConversationDataset as TranscDataset
        from src.training.trainer import TrainingConfig, get_device
    except ImportError as exc:
        print(f"[Error] Missing dependency: {exc}")
        print("Ensure torch and Tranc3 modules are installed.")
        raise SystemExit(1) from exc

    cfg = TrainingConfig()
    device = get_device(cfg)

    # Load model
    model = AdvancedTransformerModel(cfg)
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=True)
    if "model_state" in ckpt:
        model.load_state_dict(ckpt["model_state"])
        step = ckpt.get("step", 0)
    else:
        model.load_state_dict(ckpt)
        step = 0
    model = model.to(device)
    model.eval()
    print(f"[Evaluator] Checkpoint loaded (step={step})")

    # Validation loader (if data available)
    eval_metrics: Optional[EvalMetrics] = None
    try:
        val_ds = TranscDataset(split="val")  # type: ignore[call-arg]
        val_loader = torch.utils.data.DataLoader(
            val_ds, batch_size=cfg.batch_size, shuffle=False
        )
        evaluator = ModelEvaluator(model, val_loader, device, max_batches=args.max_batches)
        eval_metrics = evaluator.run()
        print(
            f"[Eval] Loss={eval_metrics.avg_loss:.4f}  PPL={eval_metrics.perplexity:.2f}"
            f"  Acc={eval_metrics.token_accuracy:.4f}"
            f"  D1={eval_metrics.distinct_1:.4f}  D2={eval_metrics.distinct_2:.4f}"
        )
    except Exception as exc:
        print(f"[Eval] Validation data unavailable: {exc} — skipping eval metrics")

    # Benchmark suite (uses a minimal stub tokenizer if none available)
    class _StubTokenizer:
        def encode(self, text: str) -> List[int]:
            return [ord(c) % 256 for c in text[:64]]

        def decode(self, tokens: List[int]) -> str:
            return "".join(chr(t + 32) for t in tokens if 32 <= t + 32 <= 126)

    suite = BenchmarkSuite(
        model,
        _StubTokenizer(),
        device,
        max_new_tokens=args.max_new_tokens,
    )
    report = suite.run(
        model_path=args.checkpoint,
        step=step,
        eval_metrics=eval_metrics,
    )
    suite.save(report, args.output)

    print("\n[Benchmark Summary]")
    for k, v in report.summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()

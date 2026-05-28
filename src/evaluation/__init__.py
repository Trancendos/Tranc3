"""
Tranc3 Model Evaluation Framework
===================================
Metrics-driven evaluation for language model outputs.
Powered by Luminous (Cornelius MacIntyre) — AI Intelligence & Orchestration.
"""

from .model_eval import (
    EvalConfig,
    EvalResult,
    EvalSuite,
    bleu_score,
    rouge_l_score,
)

__all__ = ["EvalSuite", "EvalConfig", "EvalResult", "bleu_score", "rouge_l_score"]

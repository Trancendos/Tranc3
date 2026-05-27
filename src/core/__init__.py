# src/core/__init__.py
# Lazy imports — only pull in what's available at runtime.
# multilingual_tokenizer wraps BERT (requires `transformers`) and is
# superseded by src.core.tranc3_tokenizer. Import it only on demand.

__all__ = [
    "AdvancedTransformerModel",
    "Tranc3Tokenizer",
    "get_tranc3_engine",
    "MultilingualDataset",
    "FeatureFlag",
    "FeatureFlagManager",
    "compressor",
    "MultilingualTokenizer",
    "MLPipeline",
    "PipelineRequest",
    "PipelineResponse",
    "get_pipeline",
]

try:
    from src.core.advanced_model import AdvancedTransformerModel
except ImportError:
    AdvancedTransformerModel = None  # type: ignore[assignment,misc]
try:
    from src.core.tranc3_tokenizer import Tranc3Tokenizer
except Exception:
    Tranc3Tokenizer = None  # type: ignore[assignment,misc]
try:
    from src.core.tranc3_inference import get_engine as get_tranc3_engine
except Exception:
    get_tranc3_engine = None  # type: ignore[assignment,misc]
try:
    from src.core.dataset import MultilingualDataset
except Exception:
    MultilingualDataset = None  # type: ignore[assignment,misc]

try:
    from src.core.feature_flags import FeatureFlag, FeatureFlagManager
except Exception:  # noqa: S110
    pass  # nosec B110 — graceful degradation; error logged upstream


try:
    from src.core.context_compressor import compressor
except Exception:  # noqa: S110
    pass  # nosec B110 — graceful degradation; error logged upstream


# Legacy BERT-based tokenizer — only available when `transformers` is installed.
try:
    from src.core.multilingual_tokenizer import MultilingualTokenizer
except ImportError:
    MultilingualTokenizer = None  # type: ignore[assignment,misc]

# Phase 4 ML Pipeline -- unified inference with Neural & Intelligence integration
try:
    from src.core.ml_pipeline import MLPipeline, PipelineRequest, PipelineResponse, get_pipeline
except Exception:  # noqa: S110
    pass  # nosec B110 — graceful degradation; error logged upstream

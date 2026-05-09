# src/core/__init__.py
# Lazy imports — only pull in what's available at runtime.
# Modules that depend on torch/transformers are imported lazily
# so the package can be used in environments without GPU/ML deps.

# ── Always-available modules ──
try:
    from src.core.startup import StartupValidator, get_validator, ServiceStatus
except Exception:
    pass

try:
    from src.core.feature_flags import FeatureFlag, FeatureFlagManager
except Exception:
    pass

try:
    from src.core.context_compressor import compressor
except Exception:
    pass

# ── ML-dependent modules (require torch) ──
try:
    from src.core.advanced_model import AdvancedTransformerModel
except ImportError:
    AdvancedTransformerModel = None  # type: ignore[assignment,misc]

try:
    from src.core.tranc3_tokenizer import Tranc3Tokenizer
except ImportError:
    Tranc3Tokenizer = None  # type: ignore[assignment,misc]

try:
    from src.core.tranc3_inference import get_engine as get_tranc3_engine
except ImportError:
    get_tranc3_engine = None  # type: ignore[assignment,misc]

try:
    from src.core.dataset import MultilingualDataset
except ImportError:
    MultilingualDataset = None  # type: ignore[assignment,misc]

# Legacy BERT-based tokenizer — only available when `transformers` is installed.
try:
    from src.core.multilingual_tokenizer import MultilingualTokenizer
except ImportError:
    MultilingualTokenizer = None  # type: ignore[assignment,misc]

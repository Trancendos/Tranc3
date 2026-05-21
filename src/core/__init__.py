# src/core/__init__.py
# Lazy imports — only pull in what's available at runtime.
# multilingual_tokenizer wraps BERT (requires `transformers`) and is
# superseded by src.core.tranc3_tokenizer. Import it only on demand.

from src.core.advanced_model import AdvancedTransformerModel
from src.core.tranc3_tokenizer import Tranc3Tokenizer
from src.core.tranc3_inference import get_engine as get_tranc3_engine
from src.core.dataset import MultilingualDataset

try:
    from src.core.feature_flags import FeatureFlag, FeatureFlagManager
except Exception:
    pass

try:
    from src.core.context_compressor import compressor
except Exception:
    pass

# Legacy BERT-based tokenizer — only available when `transformers` is installed.
try:
    from src.core.multilingual_tokenizer import MultilingualTokenizer
except ImportError:
    MultilingualTokenizer = None  # type: ignore[assignment,misc]

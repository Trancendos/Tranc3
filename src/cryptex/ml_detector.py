"""ML threat detection: IsolationForest anomaly detection with Z-score fallback."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

try:
    from sklearn.ensemble import IsolationForest  # type: ignore
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

# Pre-compiled patterns for feature extraction
_SQL_PATTERN = re.compile(
    r"\b(select|union|insert|update|delete|drop|from|where|or\s+1=1|sleep\(|benchmark\()\b",
    re.IGNORECASE,
)
_XSS_PATTERN = re.compile(
    r"(<script|javascript:|onerror=|onload=|alert\(|document\.cookie|innerHTML|<iframe)",
    re.IGNORECASE,
)
_TRAVERSAL_PATTERN = re.compile(
    r"(\.\./|\.\.\\|%2e%2e|%252e|/etc/passwd|c:\\\\windows)",
    re.IGNORECASE,
)

_RETRAIN_INTERVAL = 1000


@dataclass
class RequestFeatures:
    path_length: int
    param_count: int
    body_size: int
    has_sql_keywords: bool
    has_xss_markers: bool
    has_path_traversal: bool
    response_time_ms: float
    status_code: int


class MLThreatDetector:
    def __init__(self, contamination: float = 0.05) -> None:
        self.contamination = contamination
        self._sklearn_available: bool = _SKLEARN_AVAILABLE
        self._model: object = None
        self._training_data: list[list[float]] = []
        # Z-score baseline storage: list of (mean, std) per feature index
        self._zscore_means: list[float] = []
        self._zscore_stds: list[float] = []
        self._is_trained: bool = False
        self._model_type: str = "untrained"
        self._samples_since_last_train: int = 0

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def extract_features(
        self,
        path: str,
        params: dict,
        body: str,
        response_time_ms: float,
        status_code: int,
    ) -> RequestFeatures:
        combined = path + str(params) + body
        return RequestFeatures(
            path_length=len(path),
            param_count=len(params),
            body_size=len(body),
            has_sql_keywords=bool(_SQL_PATTERN.search(combined)),
            has_xss_markers=bool(_XSS_PATTERN.search(combined)),
            has_path_traversal=bool(_TRAVERSAL_PATTERN.search(combined)),
            response_time_ms=response_time_ms,
            status_code=status_code,
        )

    def _features_to_vector(self, f: RequestFeatures) -> list[float]:
        return [
            float(f.path_length),
            float(f.param_count),
            float(f.body_size),
            float(f.has_sql_keywords),
            float(f.has_xss_markers),
            float(f.has_path_traversal),
            float(f.response_time_ms),
            float(f.status_code),
        ]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, samples: list[RequestFeatures]) -> None:
        """Fit the model on a list of RequestFeatures samples."""
        if not samples:
            return

        vectors = [self._features_to_vector(s) for s in samples]
        self._training_data.extend(vectors)

        if self._sklearn_available:
            self._model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=100,
            )
            self._model.fit(vectors)  # type: ignore[union-attr]
            self._model_type = "isolation_forest"
        else:
            self._fit_zscore(vectors)
            self._model_type = "zscore"

        self._is_trained = True
        self._samples_since_last_train = 0

    def _fit_zscore(self, vectors: list[list[float]]) -> None:
        """Compute per-feature mean and std from training vectors."""
        n_features = len(vectors[0]) if vectors else 8
        n = len(vectors)
        means = [sum(v[i] for v in vectors) / n for i in range(n_features)]
        variances = [
            sum((v[i] - means[i]) ** 2 for v in vectors) / max(1, n)
            for i in range(n_features)
        ]
        stds = [math.sqrt(var) for var in variances]
        self._zscore_means = means
        self._zscore_stds = stds

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, f: RequestFeatures) -> dict:
        """Return anomaly verdict, score, and method used."""
        if not self._is_trained:
            # Heuristic: flag obviously malicious features immediately
            vec = self._features_to_vector(f)
            heuristic_score = (
                float(f.has_sql_keywords) * 0.4
                + float(f.has_xss_markers) * 0.4
                + float(f.has_path_traversal) * 0.4
            )
            return {
                "anomaly": heuristic_score > 0.3,
                "score": round(heuristic_score, 4),
                "method": "untrained",
            }

        if self._sklearn_available and self._model is not None:
            vec = self._features_to_vector(f)
            raw_pred = self._model.predict([vec])[0]  # type: ignore[union-attr]
            raw_score = self._model.score_samples([vec])[0]  # type: ignore[union-attr]
            # IsolationForest returns -1 for anomaly, 1 for normal
            # score_samples returns negative values; more negative = more anomalous
            anomaly = bool(raw_pred == -1)
            # Normalise score to [0, 1]; more anomalous = higher value
            norm_score = max(0.0, min(1.0, -raw_score))
            return {
                "anomaly": anomaly,
                "score": round(norm_score, 4),
                "method": "isolation_forest",
            }

        return self._zscore_predict(self._features_to_vector(f))

    def _zscore_predict(self, vec: list[float]) -> dict:
        """Compute Z-score across features; anomaly if max |z| > 3."""
        if not self._zscore_means:
            return {"anomaly": False, "score": 0.0, "method": "zscore"}

        zscores = []
        for i, val in enumerate(vec):
            std = self._zscore_stds[i] if i < len(self._zscore_stds) else 0.0
            mean = self._zscore_means[i] if i < len(self._zscore_means) else 0.0
            if std < 1e-9:
                z = 0.0
            else:
                z = abs((val - mean) / std)
            zscores.append(z)

        max_z = max(zscores) if zscores else 0.0
        anomaly = max_z > 3.0
        # Normalise score: cap at z=10 → score 1.0
        norm_score = min(1.0, max_z / 10.0)
        return {
            "anomaly": anomaly,
            "score": round(norm_score, 4),
            "method": "zscore",
        }

    # ------------------------------------------------------------------
    # Online update
    # ------------------------------------------------------------------

    def online_update(self, f: RequestFeatures) -> None:
        """Append to training data and re-train every 1000 samples."""
        vec = self._features_to_vector(f)
        self._training_data.append(vec)
        self._samples_since_last_train += 1

        if self._samples_since_last_train >= _RETRAIN_INTERVAL:
            # Re-train on the full accumulated dataset
            if self._sklearn_available:
                model = IsolationForest(
                    contamination=self.contamination,
                    random_state=42,
                    n_estimators=100,
                )
                model.fit(self._training_data)
                self._model = model
                self._model_type = "isolation_forest"
            else:
                self._fit_zscore(self._training_data)
                self._model_type = "zscore"

            self._is_trained = True
            self._samples_since_last_train = 0

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "training_samples": len(self._training_data),
            "model_type": self._model_type,
            "contamination": self.contamination,
            "is_trained": self._is_trained,
            "sklearn_available": self._sklearn_available,
        }

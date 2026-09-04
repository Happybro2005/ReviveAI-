"""Shared ML plumbing: artifact persistence, risk bucketing, metric computation."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LOW, MEDIUM, HIGH = "LOW", "MEDIUM", "HIGH"

# Shared thresholds so every pillar buckets risk the same way.
RISK_THRESHOLDS = {"medium": 0.35, "high": 0.60}


def risk_level(probability: float) -> str:
    if probability >= RISK_THRESHOLDS["high"]:
        return HIGH
    if probability >= RISK_THRESHOLDS["medium"]:
        return MEDIUM
    return LOW


@dataclass
class ModelArtifact:
    """A trained model plus everything needed to reproduce and audit it."""

    name: str
    version: str
    algorithm: str
    feature_names: list[str]
    categorical_features: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    training_rows: int = 0
    trained_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_version(name: str) -> str:
    return f"{name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def save_model(
    artifact_dir: Path,
    name: str,
    estimator: Any,
    meta: ModelArtifact,
) -> tuple[Path, Path]:
    """Persist estimator + metadata side by side."""
    import joblib

    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / f"{name}.joblib"
    meta_path = artifact_dir / f"{name}.json"
    joblib.dump(estimator, model_path)
    meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
    return model_path, meta_path


class ModelStore:
    """Process-wide cache of loaded models.

    Models are loaded once on first use and reused; they are never retrained at
    API start-up.
    """

    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._cache: dict[str, tuple[Any, ModelArtifact]] = {}
        self._lock = threading.Lock()

    def available(self, name: str) -> bool:
        return (self.artifact_dir / f"{name}.joblib").exists()

    def load(self, name: str) -> tuple[Any, ModelArtifact] | tuple[None, None]:
        if name in self._cache:
            return self._cache[name]
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            model_path = self.artifact_dir / f"{name}.joblib"
            meta_path = self.artifact_dir / f"{name}.json"
            if not model_path.exists():
                return None, None
            import joblib

            estimator = joblib.load(model_path)
            meta_dict = (
                json.loads(meta_path.read_text(encoding="utf-8"))
                if meta_path.exists()
                else {}
            )
            meta = ModelArtifact(
                name=meta_dict.get("name", name),
                version=meta_dict.get("version", "unknown"),
                algorithm=meta_dict.get("algorithm", "unknown"),
                feature_names=meta_dict.get("feature_names", []),
                categorical_features=meta_dict.get("categorical_features", []),
                metrics=meta_dict.get("metrics", {}),
                training_rows=meta_dict.get("training_rows", 0),
                trained_at=meta_dict.get("trained_at", ""),
                notes=meta_dict.get("notes", ""),
            )
            self._cache[name] = (estimator, meta)
            return estimator, meta

    def require(self, name: str) -> tuple[Any, ModelArtifact]:
        estimator, meta = self.load(name)
        if estimator is None:
            raise ModelNotTrained(
                f"Model '{name}' has not been trained. "
                f"Run: python scripts/train_models.py"
            )
        return estimator, meta  # type: ignore[return-value]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def status(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.artifact_dir.glob("*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return out


class ModelNotTrained(RuntimeError):
    """Raised when inference is requested before a model artifact exists."""


def classification_metrics(y_true, y_prob, threshold: float = 0.5) -> dict[str, Any]:
    """ROC-AUC, PR-AUC, precision/recall/F1 and the confusion matrix."""
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob >= threshold).astype(int)

    metrics: dict[str, Any] = {
        "positive_rate": float(y_true.mean()),
        "threshold": threshold,
        "n": int(len(y_true)),
    }
    # ROC-AUC is undefined when only one class is present.
    if len(np.unique(y_true)) > 1:
        metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
        metrics["pr_auc"] = round(float(average_precision_score(y_true, y_prob)), 4)
    metrics["precision"] = round(float(precision_score(y_true, y_pred, zero_division=0)), 4)
    metrics["recall"] = round(float(recall_score(y_true, y_pred, zero_division=0)), 4)
    metrics["f1"] = round(float(f1_score(y_true, y_pred, zero_division=0)), 4)
    metrics["brier"] = round(float(brier_score_loss(y_true, y_prob)), 4)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    metrics["confusion_matrix"] = {
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)
    }
    return metrics

"""Train and register every ReviveAI model.

Usage:
    python scripts/train_models.py [--only abandonment,recovery,...] [--skip-importance]

Design notes
------------
* Splits are **time-based**, not random. A random split would let a model train
  on a customer's later behaviour and be tested on their earlier behaviour,
  which flatters the score and is not how the model runs in production.
* `assert_no_leakage` runs before every fit. A leaky feature set raises here and
  no artifact is written.
* Metrics are computed on the held-out later period only.
* Every artifact records its version, feature list and metrics, and is written
  to the model registry table so /api/models/metrics can serve them.

DISCLOSURE: these models are trained on synthetic demo data. The reported
metrics describe performance on that synthetic distribution and are not
production performance figures.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.models import ModelRegistry  # noqa: E402
from ml import datasets  # noqa: E402
from ml.common import (  # noqa: E402
    ModelArtifact,
    classification_metrics,
    make_version,
    save_model,
)
from ml.explainability.explainer import global_importance  # noqa: E402
from ml.leakage import assert_no_leakage  # noqa: E402
from ml.pipeline_builder import build_classifier  # noqa: E402

TEST_FRACTION = 0.20


def time_split(df: pd.DataFrame, date_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Earliest 80% trains, latest 20% tests."""
    df = df.sort_values(date_col).reset_index(drop=True)
    cut = int(len(df) * (1 - TEST_FRACTION))
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def register(name: str, meta: ModelArtifact, artifact_path: Path) -> None:
    with session_scope() as s:
        s.add(
            ModelRegistry(
                name=name,
                version=meta.version,
                algorithm=meta.algorithm,
                trained_at=datetime.now(timezone.utc),
                artifact_path=str(artifact_path),
                feature_names=json.dumps(meta.feature_names),
                metrics=json.dumps(meta.metrics),
                training_rows=str(meta.training_rows),
                notes=meta.notes,
            )
        )


def _train_binary(
    name: str,
    df: pd.DataFrame,
    target: str,
    numeric: list[str],
    categorical: list[str],
    date_col: str,
    artifact_dir: Path,
    notes: str,
    compute_importance: bool,
) -> dict:
    features = numeric + categorical
    assert_no_leakage(features, name)

    train, test = time_split(df, date_col)
    X_train, y_train = train[features], train[target].astype(int)
    X_test, y_test = test[features], test[target].astype(int)

    if y_train.nunique() < 2 or y_test.nunique() < 2:
        raise RuntimeError(
            f"[{name}] target '{target}' does not have both classes in the split "
            f"(train={y_train.nunique()}, test={y_test.nunique()}). "
            f"Regenerate data with more rows."
        )

    t0 = time.time()
    pipeline = build_classifier(numeric, categorical)
    pipeline.fit(X_train, y_train)
    fit_seconds = time.time() - t0

    y_prob = pipeline.predict_proba(X_test)[:, 1]
    metrics = classification_metrics(y_test, y_prob)
    metrics["fit_seconds"] = round(fit_seconds, 2)
    metrics["train_rows"] = int(len(train))
    metrics["test_rows"] = int(len(test))
    metrics["split"] = "time-based (earliest 80% train / latest 20% test)"
    metrics["data"] = "synthetic"

    if compute_importance:
        try:
            metrics["permutation_importance"] = global_importance(
                pipeline, X_test, y_test, features
            )
        except Exception as exc:
            metrics["permutation_importance_error"] = str(exc)

    meta = ModelArtifact(
        name=name,
        version=make_version(name),
        algorithm="HistGradientBoostingClassifier + OneHot/Impute",
        feature_names=features,
        categorical_features=categorical,
        metrics=metrics,
        training_rows=int(len(train)),
        trained_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )
    model_path, _ = save_model(artifact_dir, name, pipeline, meta)
    register(name, meta, model_path)

    auc = metrics.get("roc_auc", float("nan"))
    print(f"  {name:<14} ROC-AUC={auc:.4f}  PR-AUC={metrics.get('pr_auc', 0):.4f}  "
          f"rows={len(train):,}/{len(test):,}  ({fit_seconds:.1f}s)")
    return metrics


# --------------------------------------------------------------------------
def train_abandonment(engine, artifact_dir, importance) -> dict:
    df = datasets.load_abandonment(engine)
    return _train_binary(
        "abandonment", df, "abandoned",
        datasets.ABANDONMENT_NUMERIC + datasets.ABANDONMENT_BOOL,
        datasets.ABANDONMENT_CATEGORICAL,
        "started_at", artifact_dir,
        "Predicts whether a checkout session will be abandoned, using only "
        "signals observable during the session.",
        importance,
    )


def train_recovery(engine, artifact_dir, importance) -> dict:
    df = datasets.load_recovery(engine)
    return _train_binary(
        "recovery", df, "recovered",
        datasets.RECOVERY_NUMERIC + datasets.RECOVERY_BOOL,
        datasets.RECOVERY_CATEGORICAL,
        "abandoned_at", artifact_dir,
        "Predicts whether an abandoned cart is recovered given the action taken. "
        "The action is an input so the decision engine can compare candidates; "
        "carts with no outreach are included as NO_ACTION.",
        importance,
    )


def train_return(engine, artifact_dir, importance) -> dict:
    df = datasets.load_return_risk(engine)
    return _train_binary(
        "return_risk", df, "returned",
        datasets.RETURN_NUMERIC + datasets.RETURN_BOOL,
        datasets.RETURN_CATEGORICAL,
        "order_date", artifact_dir,
        "Predicts return probability for a delivered order line. Product review "
        "signals are joined as-of the order date so later reviews cannot leak in.",
        importance,
    )


def train_rto(engine, artifact_dir, importance) -> dict:
    df = datasets.load_rto_risk(engine)
    return _train_binary(
        "rto_risk", df, "is_rto",
        datasets.RTO_NUMERIC + datasets.RTO_BOOL,
        datasets.RTO_CATEGORICAL,
        "order_date", artifact_dir,
        "Predicts RTO probability at order placement. Post-dispatch facts "
        "(actual transit days, delivery attempts, measured weight) are excluded.",
        importance,
    )


def train_anomaly(engine, artifact_dir) -> dict:
    """Unsupervised IsolationForest over customer behaviour."""
    from sklearn.ensemble import IsolationForest
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    df = datasets.load_customer_behaviour(engine)
    if df.empty or len(df) < 50:
        print("  anomaly        skipped (not enough customers with orders)")
        return {}

    features = datasets.ANOMALY_FEATURES
    X = df[features].astype(float)

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("iso", IsolationForest(
            n_estimators=250, contamination=0.03, random_state=42, n_jobs=1
        )),
    ])
    pipeline.fit(X)
    scores = pipeline.decision_function(X)
    flagged = int((pipeline.predict(X) == -1).sum())

    metrics = {
        "n_customers": int(len(df)),
        "contamination": 0.03,
        "flagged": flagged,
        "flagged_share": round(flagged / len(df), 4),
        "score_min": round(float(scores.min()), 4),
        "score_max": round(float(scores.max()), 4),
        "score_mean": round(float(scores.mean()), 4),
        "supervised": False,
        "note": (
            "Unsupervised: no labelled fraud exists in the data, so there is no "
            "ROC-AUC to report. The detector supplies a second opinion alongside "
            "deterministic business rules; it is never used alone."
        ),
        "data": "synthetic",
    }
    meta = ModelArtifact(
        name="anomaly", version=make_version("anomaly"),
        algorithm="IsolationForest + StandardScaler",
        feature_names=features, metrics=metrics, training_rows=int(len(df)),
        trained_at=datetime.now(timezone.utc).isoformat(),
        notes="Behavioural outlier detection. Pairs with the rule engine in ml/protection/fraud_model.py.",
    )
    path, _ = save_model(artifact_dir, "anomaly", pipeline, meta)
    register("anomaly", meta, path)
    print(f"  anomaly        flagged {flagged}/{len(df)} customers "
          f"({flagged / len(df) * 100:.1f}%)")
    return metrics


def train_sentiment(engine, artifact_dir) -> dict:
    """TF-IDF + LogisticRegression sentiment classifier.

    Labels come from the star rating supplied with each review (1-2 NEGATIVE,
    3 NEUTRAL, 4-5 POSITIVE). The rating is a real human label that ships with
    the review, so this is ordinary supervised text classification.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report
    from sklearn.pipeline import Pipeline

    df = pd.read_sql(
        "SELECT review_text, rating, review_date FROM reviews "
        "WHERE review_text IS NOT NULL AND length(review_text) > 5",
        engine,
    )
    if len(df) < 500:
        print("  sentiment      skipped (need at least 500 reviews)")
        return {}

    def label(r: int) -> str:
        return "NEGATIVE" if r <= 2 else ("NEUTRAL" if r == 3 else "POSITIVE")

    df["label"] = df["rating"].map(label)
    df["review_date"] = pd.to_datetime(df["review_date"], utc=True)
    train, test = time_split(df, "review_date")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2), min_df=3, max_features=60000,
            sublinear_tf=True, strip_accents="unicode", lowercase=True,
        )),
        ("clf", LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")),
    ])
    t0 = time.time()
    pipeline.fit(train["review_text"], train["label"])
    fit_seconds = time.time() - t0

    y_pred = pipeline.predict(test["review_text"])
    report = classification_report(
        test["label"], y_pred, output_dict=True, zero_division=0
    )
    metrics = {
        "accuracy": round(float(report["accuracy"]), 4),
        "macro_f1": round(float(report["macro avg"]["f1-score"]), 4),
        "per_class": {
            k: {m: round(float(v[m]), 4) for m in ("precision", "recall", "f1-score")}
            for k, v in report.items()
            if k in ("NEGATIVE", "NEUTRAL", "POSITIVE")
        },
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "labels_from": "star rating (1-2 NEGATIVE, 3 NEUTRAL, 4-5 POSITIVE)",
        "split": "time-based (earliest 80% train / latest 20% test)",
        "fit_seconds": round(fit_seconds, 2),
        "data": "synthetic",
        "note": (
            "This classifier is a second opinion alongside the lexicon scorer. "
            "It has no MIXED class; MIXED is decided structurally from clause "
            "polarity, so the classifier never overrides a MIXED verdict."
        ),
    }
    meta = ModelArtifact(
        name="sentiment_clf", version=make_version("sentiment"),
        algorithm="TfidfVectorizer(1,2) + LogisticRegression",
        feature_names=["review_text"], metrics=metrics,
        training_rows=int(len(train)),
        trained_at=datetime.now(timezone.utc).isoformat(),
        notes="Rating-supervised sentiment classifier for the Voice of Customer pipeline.",
    )
    path, _ = save_model(artifact_dir, "sentiment_clf", pipeline, meta)
    register("sentiment_clf", meta, path)
    print(f"  sentiment_clf  accuracy={metrics['accuracy']:.4f}  "
          f"macro-F1={metrics['macro_f1']:.4f}  ({fit_seconds:.1f}s)")
    return metrics


TRAINERS = {
    "abandonment": lambda e, a, i: train_abandonment(e, a, i),
    "recovery": lambda e, a, i: train_recovery(e, a, i),
    "return_risk": lambda e, a, i: train_return(e, a, i),
    "rto_risk": lambda e, a, i: train_rto(e, a, i),
    "anomaly": lambda e, a, i: train_anomaly(e, a),
    "sentiment_clf": lambda e, a, i: train_sentiment(e, a),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Train ReviveAI models")
    ap.add_argument("--only", type=str, default=None,
                    help="comma-separated subset: " + ",".join(TRAINERS))
    ap.add_argument("--skip-importance", action="store_true",
                    help="skip permutation importance (much faster)")
    args = ap.parse_args()

    settings = get_settings()
    engine = get_engine()
    artifact_dir = settings.artifact_path
    importance = not args.skip_importance

    selected = list(TRAINERS)
    if args.only:
        selected = [s.strip() for s in args.only.split(",") if s.strip()]
        unknown = set(selected) - set(TRAINERS)
        if unknown:
            print(f"Unknown model(s): {', '.join(sorted(unknown))}")
            return 1

    print("Training ReviveAI models")
    print("  DISCLOSURE: trained on synthetic demo data; metrics are not "
          "production performance.")
    print(f"  artifacts -> {artifact_dir}")

    failures: list[str] = []
    for name in selected:
        try:
            TRAINERS[name](engine, artifact_dir, importance)
        except Exception as exc:
            failures.append(name)
            print(f"  {name:<14} FAILED: {type(exc).__name__}: {exc}")

    if failures:
        print(f"\n{len(failures)} model(s) failed: {', '.join(failures)}")
        return 1
    print("\nAll models trained. Next: start the API with uvicorn app.main:app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared sklearn pipeline construction.

One place defines how categorical and numeric columns are handled, so training
and inference cannot drift apart: the fitted preprocessing travels inside the
saved artifact.
"""
from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def build_classifier(
    numeric: list[str],
    categorical: list[str],
    *,
    random_state: int = 42,
    max_iter: int = 300,
    learning_rate: float = 0.08,
    max_leaf_nodes: int = 31,
) -> Pipeline:
    """HistGradientBoostingClassifier behind a one-hot/impute preprocessor."""
    pre = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", min_frequency=20,
                              sparse_output=False),
                categorical,
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    model = HistGradientBoostingClassifier(
        random_state=random_state,
        max_iter=max_iter,
        learning_rate=learning_rate,
        max_leaf_nodes=max_leaf_nodes,
        early_stopping=True,
        validation_fraction=0.12,
        n_iter_no_change=25,
    )
    return Pipeline([("pre", pre), ("clf", model)])


def expanded_feature_names(pipeline: Pipeline) -> list[str]:
    """Post-transform feature names, used for SHAP and importance reporting."""
    return list(pipeline.named_steps["pre"].get_feature_names_out())


def frame_for(features: list[str], payload: dict) -> pd.DataFrame:
    """Build a single-row frame with every expected column present.

    Missing keys become NA so the fitted imputer handles them, rather than the
    request failing or silently scoring against a different column order.
    """
    row = {f: payload.get(f, None) for f in features}
    return pd.DataFrame([row], columns=features)

"""Training-set builders.

Point-in-time correctness
-------------------------
Every "prior_*" feature counts only events that had already happened when the
row's event occurred. Customer aggregates stored on the `customers` table are
current-as-of-now and would leak the future, so they are never read here;
history is recomputed by replaying events in date order instead.

Product review signals are joined with `merge_asof`, which matches each order to
the product's review statistics *as of just before the order date*. A product's
later reviews can therefore never influence a prediction about an earlier order.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

# --------------------------------------------------------------------------
# Abandonment
# --------------------------------------------------------------------------
ABANDONMENT_NUMERIC = [
    "cart_value", "item_count", "shipping_cost", "shipping_cart_ratio",
    "payment_attempts", "session_duration_sec", "address_edits", "page_errors",
    "hour_of_day", "prior_order_count", "prior_abandonment_count",
    "prior_return_count", "prior_rto_count",
]
ABANDONMENT_BOOL = ["payment_failed", "coupon_applied", "coupon_failed", "is_weekend"]
ABANDONMENT_CATEGORICAL = ["payment_method", "device_type", "checkout_stage"]
ABANDONMENT_FEATURES = ABANDONMENT_NUMERIC + ABANDONMENT_BOOL + ABANDONMENT_CATEGORICAL


def load_abandonment(engine: Engine) -> pd.DataFrame:
    """Checkout sessions with pre-outcome features only, plus the target."""
    cols = ", ".join(ABANDONMENT_FEATURES)
    sql = f"SELECT id, started_at, {cols}, abandoned FROM checkout_sessions"
    df = pd.read_sql(sql, engine)
    for c in ABANDONMENT_BOOL + ["abandoned"]:
        df[c] = df[c].astype(int)
    for c in ABANDONMENT_CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------
RECOVERY_NUMERIC = [
    "cart_value", "item_count", "shipping_cost", "shipping_cart_ratio",
    "payment_attempts", "session_duration_sec", "page_errors",
    "prior_order_count", "prior_abandonment_count", "prior_return_count",
]
RECOVERY_BOOL = ["payment_failed", "coupon_failed"]
RECOVERY_CATEGORICAL = ["payment_method", "device_type", "primary_reason", "action"]
RECOVERY_FEATURES = RECOVERY_NUMERIC + RECOVERY_BOOL + RECOVERY_CATEGORICAL


def load_recovery(engine: Engine) -> pd.DataFrame:
    """Abandoned carts joined to the action that was actually taken.

    `action` is a legitimate input: this model answers "will THIS action recover
    THIS cart?", which is exactly what the decision engine needs to compare
    candidate actions. Carts that received no outreach are included with
    action = 'NO_ACTION' so the model learns the untreated baseline.
    """
    sql = """
        SELECT ac.id AS cart_id,
               ac.abandoned_at,
               ac.cart_value,
               ac.primary_reason,
               ac.recovered,
               cs.item_count, cs.shipping_cost, cs.shipping_cart_ratio,
               cs.payment_attempts, cs.session_duration_sec, cs.page_errors,
               cs.payment_failed, cs.coupon_failed,
               cs.payment_method, cs.device_type,
               cs.prior_order_count, cs.prior_abandonment_count, cs.prior_return_count,
               COALESCE(iv.action, 'NO_ACTION') AS action
        FROM abandoned_carts ac
        JOIN checkout_sessions cs ON cs.id = ac.checkout_session_id
        LEFT JOIN LATERAL (
            SELECT action FROM interventions i
            WHERE i.abandoned_cart_id = ac.id
            ORDER BY i.sent_at ASC LIMIT 1
        ) iv ON TRUE
    """
    df = pd.read_sql(sql, engine)
    for c in RECOVERY_BOOL + ["recovered"]:
        df[c] = df[c].astype(int)
    for c in RECOVERY_CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


# --------------------------------------------------------------------------
# Product review signals as-of a date
# --------------------------------------------------------------------------
def load_product_review_timeline(engine: Engine) -> pd.DataFrame:
    """Running per-product review statistics, one row per review, in date order.

    Used with merge_asof so each order sees only reviews that predate it.
    """
    sql = """
        SELECT r.product_id, r.review_date, r.rating,
               MAX(CASE WHEN ra.aspect = 'SIZE_FIT'        AND ra.sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS neg_size,
               MAX(CASE WHEN ra.aspect = 'PRODUCT_QUALITY' AND ra.sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS neg_quality,
               MAX(CASE WHEN ra.aspect = 'DELIVERY'        AND ra.sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS neg_delivery,
               MAX(CASE WHEN ra.aspect = 'PACKAGING'       AND ra.sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS neg_packaging
        FROM reviews r
        LEFT JOIN review_aspects ra ON ra.review_id = r.id
        WHERE r.product_id IS NOT NULL
        GROUP BY r.id, r.product_id, r.review_date, r.rating
        ORDER BY r.product_id, r.review_date
    """
    df = pd.read_sql(sql, engine)
    if df.empty:
        return df
    df["review_date"] = pd.to_datetime(df["review_date"], utc=True)
    g = df.groupby("product_id", sort=False)
    df["cum_reviews"] = g.cumcount() + 1
    for col in ["neg_size", "neg_quality", "neg_delivery", "neg_packaging"]:
        df[f"cum_{col}"] = g[col].cumsum()
    df["cum_rating"] = g["rating"].cumsum()

    out = pd.DataFrame({
        "product_id": df["product_id"],
        "as_of": df["review_date"],
        "voc_review_count": df["cum_reviews"],
        "voc_avg_rating": df["cum_rating"] / df["cum_reviews"],
        "voc_size_fit_rate": df["cum_neg_size"] / df["cum_reviews"],
        "voc_quality_rate": df["cum_neg_quality"] / df["cum_reviews"],
        "voc_delivery_rate": df["cum_neg_delivery"] / df["cum_reviews"],
        "voc_packaging_rate": df["cum_neg_packaging"] / df["cum_reviews"],
    })
    return out.sort_values("as_of").reset_index(drop=True)


VOC_COLS = [
    "voc_review_count", "voc_avg_rating", "voc_size_fit_rate",
    "voc_quality_rate", "voc_delivery_rate", "voc_packaging_rate",
]


def attach_voc(base: pd.DataFrame, timeline: pd.DataFrame,
               date_col: str) -> pd.DataFrame:
    """As-of join of product review stats onto an order-level frame."""
    if timeline.empty:
        for c in VOC_COLS:
            base[c] = 0.0
        return base
    left = base.sort_values(date_col).reset_index(drop=True)
    left[date_col] = pd.to_datetime(left[date_col], utc=True)
    merged = pd.merge_asof(
        left,
        timeline,
        left_on=date_col,
        right_on="as_of",
        by="product_id",
        direction="backward",
        allow_exact_matches=False,
    )
    for c in VOC_COLS:
        merged[c] = merged[c].fillna(0.0)
    return merged.drop(columns=["as_of"], errors="ignore")


# --------------------------------------------------------------------------
# Orders with replayed customer history
# --------------------------------------------------------------------------
def _replay_history(orders: pd.DataFrame, returns: pd.DataFrame,
                    shipments: pd.DataFrame) -> pd.DataFrame:
    """Add prior_* columns by replaying each customer's timeline in order."""
    orders = orders.sort_values(["customer_id", "order_date"]).reset_index(drop=True)
    g = orders.groupby("customer_id", sort=False)
    orders["prior_order_count"] = g.cumcount()

    # Prior returns: count each customer's returns requested before this order.
    ret = returns[["customer_id", "requested_at"]].dropna().sort_values("requested_at")
    orders["prior_return_count"] = 0
    if not ret.empty:
        by_cust: dict[int, np.ndarray] = {
            cid: grp["requested_at"].values
            for cid, grp in ret.groupby("customer_id", sort=False)
        }
        counts = np.zeros(len(orders), dtype=int)
        for i, (cid, dt) in enumerate(zip(orders["customer_id"].values,
                                          orders["order_date"].values)):
            arr = by_cust.get(cid)
            if arr is not None:
                counts[i] = int(np.searchsorted(arr, dt, side="left"))
        orders["prior_return_count"] = counts

    # Prior RTO and delivery failures: shipments dispatched before this order.
    rto = shipments[shipments["is_rto"]][["customer_id", "shipped_at"]].sort_values("shipped_at")
    orders["prior_rto_count"] = 0
    if not rto.empty:
        by_cust_rto: dict[int, np.ndarray] = {
            cid: grp["shipped_at"].values
            for cid, grp in rto.groupby("customer_id", sort=False)
        }
        counts = np.zeros(len(orders), dtype=int)
        for i, (cid, dt) in enumerate(zip(orders["customer_id"].values,
                                          orders["order_date"].values)):
            arr = by_cust_rto.get(cid)
            if arr is not None:
                counts[i] = int(np.searchsorted(arr, dt, side="left"))
        orders["prior_rto_count"] = counts

    denom = orders["prior_order_count"].replace(0, np.nan)
    orders["prior_return_rate"] = (orders["prior_return_count"] / denom).fillna(0.0)
    orders["prior_rto_rate"] = (orders["prior_rto_count"] / denom).fillna(0.0)
    return orders


def _load_order_base(
    engine: Engine,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (orders_with_history, returns, shipments)."""
    orders = pd.read_sql(
        """
        SELECT o.id AS order_id, o.customer_id, o.order_date, o.order_value,
               o.shipping_cost, o.payment_method, o.is_cod, o.status,
               oi.id AS order_item_id, oi.product_id, oi.quantity,
               p.category, p.subcategory, p.price AS product_price,
               p.has_size_variants, p.weight_kg,
               c.city, c.pincode
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p     ON p.id = oi.product_id
        JOIN customers c    ON c.id = o.customer_id
        """,
        engine,
    )
    returns = pd.read_sql(
        "SELECT order_id, customer_id, requested_at, reason FROM returns", engine
    )
    shipments = pd.read_sql(
        """SELECT order_id, customer_id, shipped_at, courier, promised_days,
                  declared_weight_kg, is_rto, delivery_attempts
           FROM shipments""",
        engine,
    )
    for df, col in ((orders, "order_date"), (returns, "requested_at"),
                    (shipments, "shipped_at")):
        if not df.empty:
            df[col] = pd.to_datetime(df[col], utc=True)

    orders = _replay_history(orders, returns, shipments)
    return orders, returns, shipments


# --------------------------------------------------------------------------
# Return risk
# --------------------------------------------------------------------------
RETURN_NUMERIC = [
    "order_value", "product_price", "quantity", "weight_kg",
    "prior_order_count", "prior_return_count", "prior_return_rate",
    "prior_rto_count",
] + VOC_COLS
RETURN_BOOL = ["has_size_variants", "is_cod"]
RETURN_CATEGORICAL = ["category", "payment_method"]
RETURN_FEATURES = RETURN_NUMERIC + RETURN_BOOL + RETURN_CATEGORICAL


def load_return_risk(engine: Engine) -> pd.DataFrame:
    """One row per delivered order line, target = whether it was returned.

    Only orders that actually reached the customer can be returned, so RTO'd
    orders are excluded rather than counted as negatives.
    """
    orders, returns, _ = _load_order_base(engine)
    delivered = orders[orders["status"].isin(["DELIVERED", "RETURNED"])].copy()

    returned_ids = set(returns["order_id"].dropna().astype(int))
    delivered["returned"] = delivered["order_id"].isin(returned_ids).astype(int)

    timeline = load_product_review_timeline(engine)
    delivered = attach_voc(delivered, timeline, "order_date")

    for c in RETURN_BOOL:
        delivered[c] = delivered[c].astype(int)
    for c in RETURN_CATEGORICAL:
        delivered[c] = delivered[c].astype("category")
    return delivered


# --------------------------------------------------------------------------
# RTO risk
# --------------------------------------------------------------------------
RTO_NUMERIC = [
    "order_value", "product_price", "quantity", "weight_kg", "promised_days",
    "prior_order_count", "prior_rto_count", "prior_rto_rate",
    "prior_return_count",
]
RTO_BOOL = ["is_cod"]
RTO_CATEGORICAL = ["category", "payment_method", "courier", "city"]
RTO_FEATURES = RTO_NUMERIC + RTO_BOOL + RTO_CATEGORICAL


def load_rto_risk(engine: Engine) -> pd.DataFrame:
    """One row per shipped order, target = whether it came back as RTO.

    Everything knowable only after dispatch (actual transit days, delivery
    attempts, measured weight) is excluded -- the model must score at the moment
    the order is placed, which is the only moment an intervention is possible.
    """
    orders, _, shipments = _load_order_base(engine)
    ship = shipments[["order_id", "courier", "promised_days", "is_rto"]]
    df = orders.merge(ship, on="order_id", how="inner")
    df["is_rto"] = df["is_rto"].astype(int)
    for c in RTO_BOOL:
        df[c] = df[c].astype(int)
    for c in RTO_CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


# --------------------------------------------------------------------------
# Anomaly detection
# --------------------------------------------------------------------------
ANOMALY_FEATURES = [
    "order_count", "total_spend", "return_count", "rto_count",
    "delivery_failure_count", "cod_refusal_count", "return_rate", "rto_rate",
    "cod_share", "avg_order_value", "orders_per_active_day",
]


def load_customer_behaviour(engine: Engine) -> pd.DataFrame:
    """Customer-level behavioural aggregates for unsupervised anomaly scoring.

    This model is unsupervised: there is no outcome label, so the leakage rules
    for predictive models do not apply. It describes *what a customer has
    already done*.
    """
    df = pd.read_sql(
        """
        SELECT c.id AS customer_id, c.order_count, c.total_spend, c.return_count,
               c.rto_count, c.delivery_failure_count, c.cod_refusal_count,
               c.signup_date,
               COALESCE(o.cod_orders, 0)  AS cod_orders,
               COALESCE(o.first_order, c.signup_date) AS first_order,
               COALESCE(o.last_order,  c.signup_date) AS last_order
        FROM customers c
        LEFT JOIN (
            SELECT customer_id,
                   SUM(CASE WHEN is_cod THEN 1 ELSE 0 END) AS cod_orders,
                   MIN(order_date) AS first_order,
                   MAX(order_date) AS last_order
            FROM orders GROUP BY customer_id
        ) o ON o.customer_id = c.id
        WHERE c.order_count > 0
        """,
        engine,
    )
    if df.empty:
        return df
    df["total_spend"] = df["total_spend"].astype(float)
    oc = df["order_count"].replace(0, np.nan)
    df["return_rate"] = (df["return_count"] / oc).fillna(0.0)
    df["rto_rate"] = (df["rto_count"] / oc).fillna(0.0)
    df["cod_share"] = (df["cod_orders"] / oc).fillna(0.0)
    df["avg_order_value"] = (df["total_spend"] / oc).fillna(0.0)
    span_days = (
        pd.to_datetime(df["last_order"], utc=True)
        - pd.to_datetime(df["first_order"], utc=True)
    ).dt.days.clip(lower=1)
    df["orders_per_active_day"] = df["order_count"] / span_days
    return df

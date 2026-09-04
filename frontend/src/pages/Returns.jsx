import { useState } from "react";

import { Masthead } from "../App";
import { api } from "../api/client";
import {
  Contributions,
  Disclosure,
  ErrorState,
  Loading,
  Panel,
  Risk,
  SignalChain,
  Tag,
} from "../components/primitives";
import { useAction } from "../hooks/useApi";
import { num, pct, titleCase } from "../lib/format";

const CATEGORIES = ["Apparel", "Footwear", "Electronics", "Home", "Beauty", "Accessories"];

const PRESETS = {
  sizeRisk: {
    label: "High return risk — size complaints",
    values: {
      order_value: 2400, product_price: 2400, quantity: 1, weight_kg: 0.4,
      category: "Apparel", payment_method: "UPI", is_cod: false,
      has_size_variants: true, prior_order_count: 9, prior_return_count: 6,
      prior_rto_count: 0, voc_review_count: 180, voc_avg_rating: 2.6,
      voc_size_fit_rate: 0.42, voc_quality_rate: 0.18,
      voc_delivery_rate: 0.08, voc_packaging_rate: 0.05,
    },
  },
  lowRisk: {
    label: "Low return risk — clean history",
    values: {
      order_value: 3200, product_price: 3200, quantity: 1, weight_kg: 0.3,
      category: "Electronics", payment_method: "CARD", is_cod: false,
      has_size_variants: false, prior_order_count: 12, prior_return_count: 0,
      prior_rto_count: 0, voc_review_count: 220, voc_avg_rating: 4.5,
      voc_size_fit_rate: 0.02, voc_quality_rate: 0.05,
      voc_delivery_rate: 0.06, voc_packaging_rate: 0.03,
    },
  },
};

export default function Returns() {
  const [form, setForm] = useState(PRESETS.sizeRisk.values);
  const predict = useAction(api.predictReturn);

  const set = (key) => (e) => {
    const el = e.target;
    const value =
      el.type === "checkbox" ? el.checked
        : el.type === "number" ? Number(el.value)
          : el.value;
    setForm((f) => ({ ...f, [key]: value }));
  };

  const result = predict.data;
  const vocDriven = result?.top_factors?.some(
    (f) => f.feature.startsWith("voc_") && f.direction === "INCREASES",
  );

  return (
    <>
      <Masthead
        eyebrow="Protect"
        title="Return risk"
        sub="Score an order line before it ships. Review-derived complaint rates for the product are model inputs, so customer feedback moves this number directly."
      />

      <div className="page">
        <div className="grid grid--sidebar">
          <Panel
            title="Order to score"
            note="Supply a product_id to pull that product's stored review signals automatically."
            actions={
              <div className="row">
                {Object.entries(PRESETS).map(([key, p]) => (
                  <button
                    key={key}
                    type="button"
                    className="btn btn--sm"
                    onClick={() => { setForm(p.values); predict.reset(); }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            }
          >
            <form
              className="stack"
              onSubmit={(e) => { e.preventDefault(); predict.run(form); }}
            >
              <div className="grid grid--3">
                <div className="field">
                  <label htmlFor="ret-value">Order value (₹)</label>
                  <input id="ret-value" type="number" min={1} value={form.order_value}
                         onChange={set("order_value")} required />
                </div>
                <div className="field">
                  <label htmlFor="ret-price">Product price (₹)</label>
                  <input id="ret-price" type="number" min={1} value={form.product_price}
                         onChange={set("product_price")} required />
                </div>
                <div className="field">
                  <label htmlFor="ret-cat">Category</label>
                  <select id="ret-cat" value={form.category} onChange={set("category")}>
                    {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="ret-orders">Customer prior orders</label>
                  <input id="ret-orders" type="number" min={0} value={form.prior_order_count}
                         onChange={set("prior_order_count")} />
                </div>
                <div className="field">
                  <label htmlFor="ret-returns">Customer prior returns</label>
                  <input id="ret-returns" type="number" min={0} value={form.prior_return_count}
                         onChange={set("prior_return_count")} />
                </div>
                <div className="field">
                  <label htmlFor="ret-pid">Product ID (optional)</label>
                  <input id="ret-pid" type="number" min={1} value={form.product_id ?? ""}
                         onChange={(e) => setForm((f) => ({
                           ...f,
                           product_id: e.target.value ? Number(e.target.value) : undefined,
                         }))} />
                  <span className="field__hint">Overrides the review rates below.</span>
                </div>
              </div>

              <div className="label" style={{ marginTop: 4 }}>
                Review signals for this product
              </div>
              <div className="grid grid--3">
                <div className="field">
                  <label htmlFor="ret-size">Size/fit complaint rate</label>
                  <input id="ret-size" type="number" min={0} max={1} step={0.01}
                         value={form.voc_size_fit_rate} onChange={set("voc_size_fit_rate")} />
                </div>
                <div className="field">
                  <label htmlFor="ret-qual">Quality complaint rate</label>
                  <input id="ret-qual" type="number" min={0} max={1} step={0.01}
                         value={form.voc_quality_rate} onChange={set("voc_quality_rate")} />
                </div>
                <div className="field">
                  <label htmlFor="ret-rating">Product rating</label>
                  <input id="ret-rating" type="number" min={0} max={5} step={0.1}
                         value={form.voc_avg_rating} onChange={set("voc_avg_rating")} />
                </div>
              </div>

              <div className="row">
                <label className="row" style={{ gap: 6, fontSize: "0.8125rem" }}>
                  <input type="checkbox" checked={form.has_size_variants}
                         onChange={set("has_size_variants")} />
                  Product has size variants
                </label>
                <label className="row" style={{ gap: 6, fontSize: "0.8125rem" }}>
                  <input type="checkbox" checked={form.is_cod} onChange={set("is_cod")} />
                  Cash on delivery
                </label>
              </div>

              <div className="row">
                <button type="submit" className="btn btn--primary" disabled={predict.loading}>
                  {predict.loading ? "Scoring…" : "Score return risk"}
                </button>
              </div>
            </form>
          </Panel>

          <Panel title="Prediction" note="SHAP contributions for this exact order.">
            {predict.loading && <Loading rows={4} />}
            {predict.error && (
              <ErrorState error={predict.error} what="the return model"
                          onRetry={() => predict.run(form)} />
            )}
            {!predict.loading && !predict.error && !result && (
              <p className="muted tiny">
                Fill in the order and score it. The model returns a probability, the factors
                that drove it, and the protection action that addresses the top driver.
              </p>
            )}
            {result && (
              <div className="stack">
                <div>
                  <Risk level={result.risk_level} score={result.return_probability}
                        label="Return risk" />
                </div>

                <div>
                  <div className="label" style={{ marginBottom: 7 }}>Top factors</div>
                  <Contributions items={result.top_factors} />
                </div>

                <div>
                  <div className="label" style={{ marginBottom: 5 }}>Recommended action</div>
                  <div style={{ fontWeight: 600 }}>{titleCase(result.recommended_action)}</div>
                </div>

                {vocDriven && (
                  <div>
                    <div className="label" style={{ marginBottom: 6 }}>
                      Review → protection chain
                    </div>
                    <SignalChain
                      nodes={[
                        "Customer reviews",
                        "Size / quality complaints",
                        "Return risk model input",
                        titleCase(result.recommended_action),
                      ]}
                    />
                    <p className="tiny muted" style={{ marginTop: 8 }}>
                      This score moved because of what customers wrote about the product, not
                      only its order attributes.
                    </p>
                  </div>
                )}

                {result.voc_context && (
                  <div>
                    <div className="label" style={{ marginBottom: 5 }}>Product review context</div>
                    <dl className="dl">
                      <dt>Product</dt>
                      <dd className="text">{result.voc_context.product_title}</dd>
                      <dt>Reviews</dt>
                      <dd>{num(result.voc_context.review_count)}</dd>
                      <dt>Size/fit complaints</dt>
                      <dd>{pct(result.voc_context.size_fit_complaint_rate, 1)}</dd>
                      <dt>Quality complaints</dt>
                      <dd>{pct(result.voc_context.quality_complaint_rate, 1)}</dd>
                    </dl>
                  </div>
                )}

                <div className="row tiny muted">
                  <Tag>{result.model_version}</Tag>
                  <span>{result.model_algorithm}</span>
                </div>
                <Disclosure text={result.disclosure} />
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

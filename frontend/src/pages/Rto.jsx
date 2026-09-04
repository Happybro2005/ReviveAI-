import { useState } from "react";

import { Masthead } from "../App";
import { api } from "../api/client";
import {
  ArithmeticLedger,
  Contributions,
  Disclosure,
  ErrorState,
  Loading,
  Panel,
  Risk,
  Tag,
} from "../components/primitives";
import { useAction } from "../hooks/useApi";
import { money, pct, pctRaw, titleCase } from "../lib/format";

const COURIERS = ["BlueDart", "Delhivery", "Ecom Express", "XpressBees", "IndiaPost"];
const CITIES = ["Mumbai", "Delhi", "Bengaluru", "Patna", "Guwahati", "Bhubaneswar", "Lucknow"];
const CATEGORIES = ["Apparel", "Footwear", "Electronics", "Home", "Beauty", "Accessories"];

const PRESET_HIGH = {
  order_value: 4200, product_price: 4200, quantity: 1, weight_kg: 0.6,
  category: "Apparel", payment_method: "COD", is_cod: true,
  courier: "IndiaPost", city: "Patna", promised_days: 7,
  prior_order_count: 6, prior_rto_count: 3, prior_return_count: 1,
  prior_delivery_failures: 2,
};

const PRESET_LOW = {
  order_value: 3800, product_price: 3800, quantity: 1, weight_kg: 0.5,
  category: "Electronics", payment_method: "UPI", is_cod: false,
  courier: "BlueDart", city: "Mumbai", promised_days: 3,
  prior_order_count: 14, prior_rto_count: 0, prior_return_count: 1,
  prior_delivery_failures: 0,
};

export default function Rto() {
  const [form, setForm] = useState(PRESET_HIGH);
  const predict = useAction(api.predictRto);
  const decide = useAction(api.protectionDecision);

  const set = (key) => (e) => {
    const el = e.target;
    const value =
      el.type === "checkbox" ? el.checked
        : el.type === "number" ? Number(el.value)
          : el.value;
    setForm((f) => ({
      ...f,
      [key]: value,
      ...(key === "payment_method" ? { is_cod: value === "COD" } : {}),
    }));
  };

  async function score(e) {
    e.preventDefault();
    const result = await predict.run(form);
    if (result) {
      await decide.run({
        order_value: form.order_value,
        is_cod: form.is_cod,
        rto_probability: result.rto_probability,
        return_probability: 0.1,
        voc_signals: [],
      });
    }
  }

  const result = predict.data;
  const best = decide.data?.next_best_action;

  return (
    <>
      <Masthead
        eyebrow="Protect"
        title="RTO risk"
        sub="Scored at order placement, using only what is knowable then — the one moment an undelivered shipment can still be prevented."
      />

      <div className="page">
        <div className="grid grid--sidebar">
          <Panel
            title="Order to score"
            actions={
              <div className="row">
                <button type="button" className="btn btn--sm"
                        onClick={() => { setForm(PRESET_HIGH); predict.reset(); decide.reset(); }}>
                  High-risk COD
                </button>
                <button type="button" className="btn btn--sm"
                        onClick={() => { setForm(PRESET_LOW); predict.reset(); decide.reset(); }}>
                  Low-risk prepaid
                </button>
              </div>
            }
          >
            <form className="stack" onSubmit={score}>
              <div className="grid grid--3">
                <div className="field">
                  <label htmlFor="rto-value">Order value (₹)</label>
                  <input id="rto-value" type="number" min={1} value={form.order_value}
                         onChange={set("order_value")} required />
                </div>
                <div className="field">
                  <label htmlFor="rto-pay">Payment method</label>
                  <select id="rto-pay" value={form.payment_method} onChange={set("payment_method")}>
                    {["COD", "UPI", "CARD", "NETBANKING", "WALLET"].map((m) => (
                      <option key={m}>{m}</option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="rto-cat">Category</label>
                  <select id="rto-cat" value={form.category} onChange={set("category")}>
                    {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="rto-courier">Courier</label>
                  <select id="rto-courier" value={form.courier} onChange={set("courier")}>
                    {COURIERS.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="rto-city">Delivery city</label>
                  <select id="rto-city" value={form.city} onChange={set("city")}>
                    {CITIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="rto-days">Promised days</label>
                  <input id="rto-days" type="number" min={1} max={30} value={form.promised_days}
                         onChange={set("promised_days")} />
                </div>
                <div className="field">
                  <label htmlFor="rto-orders">Prior orders</label>
                  <input id="rto-orders" type="number" min={0} value={form.prior_order_count}
                         onChange={set("prior_order_count")} />
                </div>
                <div className="field">
                  <label htmlFor="rto-prior">Prior RTOs</label>
                  <input id="rto-prior" type="number" min={0} value={form.prior_rto_count}
                         onChange={set("prior_rto_count")} />
                </div>
                <div className="field">
                  <label htmlFor="rto-fail">Prior delivery failures</label>
                  <input id="rto-fail" type="number" min={0} value={form.prior_delivery_failures}
                         onChange={set("prior_delivery_failures")} />
                </div>
              </div>
              <div className="row">
                <button type="submit" className="btn btn--primary" disabled={predict.loading}>
                  {predict.loading ? "Scoring…" : "Score RTO risk"}
                </button>
              </div>
            </form>
          </Panel>

          <Panel title="Prediction" note="SHAP contributions plus the prevention action worth taking.">
            {predict.loading && <Loading rows={4} />}
            {predict.error && (
              <ErrorState error={predict.error} what="the RTO model" onRetry={() => predict.run(form)} />
            )}
            {!predict.loading && !predict.error && !result && (
              <p className="muted tiny">
                Score an order to see its RTO probability, the drivers behind it, and whether a
                confirmation step pays for itself.
              </p>
            )}
            {result && (
              <div className="stack">
                <Risk level={result.risk_level} score={result.rto_probability} label="RTO risk" />

                <div>
                  <div className="label" style={{ marginBottom: 7 }}>Top factors</div>
                  <Contributions items={result.top_factors} />
                </div>

                <div className="disclosure">
                  <strong>Policy.</strong>
                  <span>{result.policy_note}</span>
                </div>

                {best && (
                  <div>
                    <div className="label" style={{ marginBottom: 7 }}>
                      Recommended action — {best.label}
                    </div>
                    <ArithmeticLedger
                      rows={[
                        {
                          term: "Expected loss avoided",
                          hint: `${pct(best.uplift, 0)} assumed relative risk reduction`,
                          amount: best.expected_revenue,
                        },
                        { term: "Cost of acting", amount: -best.total_cost },
                      ]}
                      total={{ term: "Expected profit", amount: best.expected_profit }}
                      formatter={(v) => money(v, { precise: true })}
                    />
                    <div className="row tiny muted" style={{ marginTop: 8 }}>
                      <Tag tone="assumed">Assumed effect</Tag>
                      <span>{best.notes}</span>
                    </div>
                    {best.roi !== null && (
                      <div className="tiny muted" style={{ marginTop: 4 }}>
                        ROI {pctRaw(best.roi, 0)}
                      </div>
                    )}
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

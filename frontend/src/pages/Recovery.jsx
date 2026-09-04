import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, TrendChart, useThemeTokens } from "../components/charts";
import {
  ArithmeticLedger,
  Contributions,
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  Risk,
  Stat,
  Tag,
} from "../components/primitives";
import { useAction, useApi } from "../hooks/useApi";
import { money, moneyShort, num, pct, pctRaw, titleCase } from "../lib/format";

const REASONS = [
  "", "PAYMENT_FAILURE", "HIGH_SHIPPING_COST", "PRICE_CONCERN",
  "COUPON_ISSUE", "TECHNICAL_PROBLEM", "CUSTOMER_HESITATION", "OTHER",
];

/** Turn an abandoned-cart row into the session payload the API expects. */
function cartToSession(cart) {
  return {
    cart_value: Number(cart.cart_value),
    shipping_cost: Number(cart.shipping_cost),
    item_count: cart.item_count,
    payment_attempts: cart.payment_attempts,
    payment_failed: cart.payment_failed,
    payment_method: cart.payment_method,
    device_type: cart.device_type,
    checkout_stage: cart.checkout_stage,
    session_duration_sec: cart.session_duration_sec,
    coupon_applied: cart.coupon_applied,
    coupon_failed: cart.coupon_failed,
    address_edits: cart.address_edits,
    page_errors: cart.page_errors,
    hour_of_day: cart.hour_of_day,
    is_weekend: cart.is_weekend,
    prior_order_count: cart.prior_order_count,
    prior_abandonment_count: cart.prior_abandonment_count,
    prior_return_count: cart.prior_return_count,
    prior_rto_count: cart.prior_rto_count,
    customer_id: cart.customer_id,
  };
}

export function DecisionDetail({ decision, prediction, onDispatch, dispatching, dispatched }) {
  if (!decision) return null;
  const best = decision.next_best_action;

  const rows = [
    {
      term: "Incremental revenue",
      hint: `cart × ${pct(best.uplift, 1)} uplift over doing nothing`,
      amount: best.incremental_revenue,
    },
    {
      term: "Gross margin on that revenue",
      hint: `× ${pct(decision.inputs.gross_margin ?? 0.35, 0)} margin`,
      amount: best.gross_profit - best.incremental_revenue,
    },
  ];
  if (best.discount_cost > 0) {
    rows.push({ term: "Discount honoured", hint: "paid on every conversion", amount: -best.discount_cost });
  }
  if (best.shipping_subsidy > 0) {
    rows.push({ term: "Shipping subsidy", hint: "paid on conversion", amount: -best.shipping_subsidy });
  }
  rows.push({
    term: `Outreach (${titleCase(best.channel)})`,
    hint: "paid whether or not they convert",
    amount: -best.comms_cost,
  });

  return (
    <div className="stack">
      <div className="row row--between">
        <div>
          <div className="label">Next best action</div>
          <h2 style={{ marginTop: 4 }}>{best.label}</h2>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="label">Expected profit</div>
          <div
            className="num"
            style={{
              fontSize: "1.5rem",
              fontWeight: 700,
              color: best.expected_profit >= 0 ? "var(--retained-ink)" : "var(--leaking-ink)",
            }}
          >
            {money(best.expected_profit, { precise: true })}
          </div>
          <div className="tiny muted">
            ROI {best.roi === null ? "n/a (no cost)" : pctRaw(best.roi, 0)}
          </div>
        </div>
      </div>

      <p className="muted" style={{ fontSize: "0.8125rem" }}>{decision.rationale}</p>

      <div>
        <div className="label" style={{ marginBottom: 7 }}>The arithmetic</div>
        <ArithmeticLedger
          rows={rows}
          total={{ term: "Expected incremental profit", amount: best.expected_profit }}
          formatter={(v) => money(v, { precise: true })}
        />
      </div>

      <div>
        <div className="label" style={{ marginBottom: 7 }}>
          Every action compared — chosen on profit, not conversion
        </div>
        <div className="tablewrap">
          <table className="data">
            <thead>
              <tr>
                <th>Action</th>
                <th className="n">Recovery</th>
                <th className="n">Uplift</th>
                <th className="n">Cost</th>
                <th className="n">Expected profit</th>
                <th className="n">ROI</th>
              </tr>
            </thead>
            <tbody>
              {[best, ...decision.alternatives].map((a) => (
                <tr key={a.action} className={a.action === best.action ? "is-selected" : ""}>
                  <td>
                    {a.label}
                    {a.action === best.action && (
                      <>
                        {" "}
                        <Tag tone="retained">Chosen</Tag>
                      </>
                    )}
                  </td>
                  <td className="n">{pct(a.probability, 1)}</td>
                  <td className="n">{a.uplift > 0 ? "+" : ""}{pct(a.uplift, 1)}</td>
                  <td className="n">{money(a.total_cost, { precise: true })}</td>
                  <td
                    className="n"
                    style={{
                      color: a.expected_profit >= 0 ? "var(--retained-ink)" : "var(--leaking-ink)",
                      fontWeight: a.action === best.action ? 700 : 400,
                    }}
                  >
                    {money(a.expected_profit, { precise: true })}
                  </td>
                  <td className="n">{a.roi === null ? "—" : pctRaw(a.roi, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {prediction?.reason && (
        <div>
          <div className="label" style={{ marginBottom: 7 }}>
            Diagnosed cause — {prediction.reason.label} ({pct(prediction.reason.confidence, 0)} confidence)
          </div>
          <div className="stack stack--sm">
            {prediction.reason.evidence.map((e) => (
              <div className="evidence" key={e.code}>
                <em>{e.observed}</em>
                <div className="tiny muted">{e.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {prediction?.abandonment?.explanation?.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 7 }}>
            Why this checkout scored {pct(prediction.abandonment.abandonment_probability, 0)}
          </div>
          <Contributions items={prediction.abandonment.explanation} />
          <div className="tiny muted" style={{ marginTop: 8 }}>
            SHAP values from {prediction.abandonment.model_version}. Rust bars push risk up,
            green bars pull it down.
          </div>
        </div>
      )}

      {onDispatch && (
        <div className="row">
          <button
            type="button"
            className="btn btn--primary"
            onClick={onDispatch}
            disabled={dispatching || dispatched || best.action === "NO_ACTION"}
          >
            {dispatched
              ? "Intervention recorded"
              : dispatching
                ? "Recording…"
                : best.action === "NO_ACTION"
                  ? "No action to send"
                  : `Send ${best.label}`}
          </button>
          <span className="tiny muted">
            Records the intervention against this cart so its outcome can be tracked.
          </span>
        </div>
      )}
    </div>
  );
}

export default function Recovery() {
  const t = useThemeTokens();
  const navigate = useNavigate();
  const [days, setDays] = useState(180);
  const [reason, setReason] = useState("");
  const [minValue, setMinValue] = useState(0);
  const [selected, setSelected] = useState(null);
  const [dispatched, setDispatched] = useState(false);

  const overview = useApi(() => api.recoveryOverview(days), [days]);
  const carts = useApi(
    () =>
      api.recoveryCarts({
        limit: 25,
        offset: 0,
        recovered: false,
        min_value: minValue,
        ...(reason ? { reason } : {}),
      }),
    [reason, minValue],
  );

  const predict = useAction(api.recoveryPredict);
  const decide = useAction(api.recoveryDecision);
  const dispatch = useAction(api.createIntervention);

  async function openCart(cart) {
    setSelected(cart);
    setDispatched(false);
    predict.reset();
    decide.reset();
    const session = cartToSession(cart);
    await Promise.all([predict.run(session), decide.run(session)]);
  }

  async function sendIntervention() {
    if (!selected || !decide.data) return;
    const best = decide.data.next_best_action;
    const result = await dispatch.run({
      abandoned_cart_id: selected.id,
      customer_id: selected.customer_id,
      pillar: "RECOVERY",
      action: best.action,
      channel: best.channel,
      predicted_probability: best.probability,
      expected_revenue: best.expected_revenue,
      intervention_cost: best.comms_cost,
      discount_cost: best.discount_cost + best.shipping_subsidy,
      expected_profit: best.expected_profit,
      model_version: predict.data?.abandonment?.model_version,
    });
    if (result) setDispatched(true);
  }

  const o = overview.data;

  return (
    <>
      <Masthead
        eyebrow="Recover"
        title="Revenue recovery"
        sub="Abandoned checkouts, why they were abandoned, and the outreach that pays for itself."
        actions={
          <div className="field" style={{ minWidth: 150 }}>
            <label htmlFor="rec-window">Window</label>
            <select id="rec-window" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[30, 90, 180, 365].map((d) => (
                <option key={d} value={d}>Last {d} days</option>
              ))}
            </select>
          </div>
        }
      />

      <div className="page">
        {overview.loading && <Loading rows={4} />}
        {overview.error && (
          <ErrorState error={overview.error} onRetry={overview.reload} what="recovery data" />
        )}

        {o && (
          <>
            <Disclosure text={o.disclosure} />

            <div className="grid grid--4">
              <Stat tone="leaking" label="Revenue at risk" value={moneyShort(o.revenue_at_risk)}
                    note={`${num(o.abandoned)} abandoned of ${num(o.sessions)} checkouts`} />
              <Stat tone="retained" label="Revenue recovered" value={moneyShort(o.recovered_revenue)}
                    note={`${num(o.recovered)} carts brought back`} />
              <Stat tone="neutral" label="Abandonment rate" value={pct(o.abandonment_rate, 1)}
                    note="Share of checkout sessions abandoned" />
              <Stat tone="retained" label="Recovery rate" value={pct(o.recovery_rate, 1)}
                    note="Share of abandoned carts recovered" />
            </div>

            <div className="grid grid--sidebar">
              <Panel title="Abandonment and recovery over time" note="By week.">
                <TrendChart
                  data={o.trend}
                  xKey="week"
                  formatter={(v) => num(v)}
                  series={[
                    { key: "abandoned", label: "Abandoned", color: t.leaking },
                    { key: "recovered", label: "Recovered", color: t.retained },
                  ]}
                />
              </Panel>
              <Panel title="Why carts are abandoned" note="Diagnosed from behavioural evidence.">
                <BarsChart
                  data={o.by_reason.map((r) => ({ name: titleCase(r.reason), count: r.count }))}
                  xKey="name"
                  layout="vertical"
                  yWidth={130}
                  height={240}
                  formatter={(v) => num(v)}
                  series={[{ key: "count", label: "Carts", color: t.leaking }]}
                />
              </Panel>
            </div>

            <Panel
              title="Historical action performance"
              note="What each outreach actually achieved on this dataset."
              flush
            >
              <div className="tablewrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th className="n">Sent</th>
                      <th className="n">Converted</th>
                      <th className="n">Conversion rate</th>
                      <th className="n">Revenue</th>
                      <th className="n">Realised profit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {o.by_action.map((a) => (
                      <tr key={a.action}>
                        <td>{titleCase(a.action)}</td>
                        <td className="n">{num(a.sent)}</td>
                        <td className="n">{num(a.converted)}</td>
                        <td className="n">{pct(a.conversion_rate, 1)}</td>
                        <td className="n">{money(a.revenue)}</td>
                        <td
                          className="n"
                          style={{ color: a.profit >= 0 ? "var(--retained-ink)" : "var(--leaking-ink)" }}
                        >
                          {money(a.profit)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </>
        )}

        <Panel
          title="Recovery worklist"
          note="Unrecovered carts, highest value first. Select one to score it and compare actions."
          actions={
            <div className="toolbar">
              <div className="field">
                <label htmlFor="filter-reason">Reason</label>
                <select id="filter-reason" value={reason} onChange={(e) => setReason(e.target.value)}>
                  {REASONS.map((r) => (
                    <option key={r} value={r}>{r ? titleCase(r) : "All reasons"}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="filter-value">Min cart value</label>
                <input
                  id="filter-value"
                  type="number"
                  min={0}
                  step={1000}
                  value={minValue}
                  onChange={(e) => setMinValue(Math.max(0, Number(e.target.value) || 0))}
                />
              </div>
            </div>
          }
          flush
        >
          {carts.loading && <div style={{ padding: 16 }}><Loading rows={4} /></div>}
          {carts.error && (
            <div style={{ padding: 16 }}>
              <ErrorState error={carts.error} onRetry={carts.reload} what="the worklist" />
            </div>
          )}
          {carts.data && carts.data.items.length === 0 && (
            <Empty
              title="No carts match these filters"
              body="Widen the value threshold or clear the reason filter."
            />
          )}
          {carts.data && carts.data.items.length > 0 && (
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Segment</th>
                    <th className="n">Cart value</th>
                    <th className="n">Shipping</th>
                    <th>Stage</th>
                    <th>Reason</th>
                    <th className="n">Prior orders</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {carts.data.items.map((c) => (
                    <tr
                      key={c.id}
                      className={`is-clickable ${selected?.id === c.id ? "is-selected" : ""}`}
                      onClick={() => openCart(c)}
                    >
                      <td>{c.customer_name}</td>
                      <td><Tag>{c.segment}</Tag></td>
                      <td className="n">{money(c.cart_value)}</td>
                      <td className="n">
                        {money(c.shipping_cost)}
                        <span className="muted"> ({pct(c.shipping_cart_ratio, 0)})</span>
                      </td>
                      <td className="tiny">{titleCase(c.checkout_stage)}</td>
                      <td className="tiny">{titleCase(c.primary_reason)}</td>
                      <td className="n">{c.prior_order_count}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={(e) => { e.stopPropagation(); openCart(c); }}
                        >
                          Score
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {selected && (
          <Panel
            title={`Decision — ${selected.customer_name}, ${money(selected.cart_value)} cart`}
            note="Scored by the abandonment and recovery models, priced by the profit optimizer."
            actions={
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => navigate(`/customer-360/${selected.customer_id}`)}
              >
                Open Customer 360
              </button>
            }
          >
            {(predict.loading || decide.loading) && <Loading rows={4} />}
            {(predict.error || decide.error) && (
              <ErrorState
                error={predict.error || decide.error}
                onRetry={() => openCart(selected)}
                what="the decision"
              />
            )}
            {decide.data && (
              <>
                {predict.data && (
                  <div className="row" style={{ marginBottom: 14 }}>
                    <Risk
                      level={predict.data.abandonment.risk_level}
                      score={predict.data.abandonment.abandonment_probability}
                      label="Abandonment risk"
                    />
                    <span className="tiny muted">
                      Baseline recovery if you do nothing:{" "}
                      <strong className="num">
                        {pct(predict.data.recovery_probability_baseline, 1)}
                      </strong>
                    </span>
                  </div>
                )}
                <DecisionDetail
                  decision={decide.data}
                  prediction={predict.data}
                  onDispatch={sendIntervention}
                  dispatching={dispatch.loading}
                  dispatched={dispatched}
                />
                {dispatch.error && (
                  <div className="field__error" style={{ marginTop: 10 }}>
                    {dispatch.error.message}
                  </div>
                )}
              </>
            )}
          </Panel>
        )}
      </div>
    </>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";

import { Masthead } from "../App";
import { api } from "../api/client";
import {
  ArithmeticLedger,
  Contributions,
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  Risk,
  SignalChain,
  Stat,
  Tag,
} from "../components/primitives";
import { useAction, useApi } from "../hooks/useApi";
import { money, moneyShort, num, pct, pctRaw, titleCase } from "../lib/format";

function ActionComparison({ decision, formatter }) {
  if (!decision) return null;
  const best = decision.next_best_action;
  const all = [best, ...decision.alternatives];
  return (
    <div className="tablewrap">
      <table className="data">
        <thead>
          <tr>
            <th>Action</th>
            <th className="n">Effect</th>
            <th className="n">Cost</th>
            <th className="n">Expected profit</th>
            <th className="n">ROI</th>
          </tr>
        </thead>
        <tbody>
          {all.map((a) => (
            <tr key={a.action} className={a.action === best.action ? "is-selected" : ""}>
              <td>
                {a.label}
                {a.action === best.action && <> <Tag tone="retained">Chosen</Tag></>}
              </td>
              <td className="n">{pct(a.uplift, 1)}</td>
              <td className="n">{formatter(a.total_cost)}</td>
              <td
                className="n"
                style={{
                  color: a.expected_profit >= 0 ? "var(--retained-ink)" : "var(--leaking-ink)",
                  fontWeight: a.action === best.action ? 700 : 400,
                }}
              >
                {formatter(a.expected_profit)}
              </td>
              <td className="n">{a.roi === null ? "—" : pctRaw(a.roi, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DecisionCenter() {
  const [customerId, setCustomerId] = useState("");
  const [active, setActive] = useState(null);
  const load = useAction(api.customerIntelligence);

  const candidates = useApi(
    () => api.customers({ limit: 12, offset: 0, has_abandoned: true }),
    [],
  );

  async function open(id) {
    setActive(id);
    await load.run(id);
  }

  const d = load.data;
  const money2 = (v) => money(v, { precise: true });

  return (
    <>
      <Masthead
        eyebrow="Engine"
        title="AI Decision Center"
        sub="One customer, every risk score, the reasoning behind each, and the single action with the highest expected profit."
      />

      <div className="page">
        <Panel
          title="Choose a customer"
          note="Pick from customers with abandoned checkouts, or enter an ID directly."
        >
          <form
            className="toolbar"
            onSubmit={(e) => { e.preventDefault(); open(Number(customerId)); }}
          >
            <div className="field">
              <label htmlFor="dc-id">Customer ID</label>
              <input id="dc-id" type="number" min={1} value={customerId}
                     onChange={(e) => setCustomerId(e.target.value)} placeholder="e.g. 42" required />
            </div>
            <button type="submit" className="btn btn--primary" disabled={load.loading}>
              {load.loading ? "Loading…" : "Analyse customer"}
            </button>
          </form>

          {candidates.data && candidates.data.items.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="label" style={{ marginBottom: 7 }}>Customers with abandoned carts</div>
              <div className="row">
                {candidates.data.items.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`btn btn--sm ${active === c.id ? "btn--primary" : ""}`}
                    onClick={() => { setCustomerId(String(c.id)); open(c.id); }}
                  >
                    {c.name} · {moneyShort(c.total_spend)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Panel>

        {load.loading && <Loading rows={5} />}
        {load.error && <ErrorState error={load.error} what="this customer" onRetry={() => open(active)} />}

        {d && (
          <>
            <Panel
              title={d.customer.name}
              note={`${d.customer.segment} · ${d.customer.city} · ${num(d.customer.order_count)} orders`}
              actions={
                <Link to={`/customer-360/${d.customer.id}`} className="btn btn--sm">
                  Open Customer 360
                </Link>
              }
            >
              <div className="grid grid--4">
                <Stat
                  tone={d.checkout_risk?.risk_level === "HIGH" ? "leaking" : "neutral"}
                  label="Checkout risk"
                  value={d.checkout_risk?.abandonment_probability != null
                    ? pct(d.checkout_risk.abandonment_probability, 0) : "—"}
                  note={d.checkout_risk?.risk_level || "No abandoned cart on file"}
                />
                <Stat
                  tone={d.return_risk?.risk_level === "HIGH" ? "leaking" : "neutral"}
                  label="Return risk"
                  value={d.return_risk?.return_probability != null
                    ? pct(d.return_risk.return_probability, 0) : "—"}
                  note={d.return_risk?.risk_level || "No order on file"}
                />
                <Stat
                  tone={d.rto_risk?.risk_level === "HIGH" ? "leaking" : "neutral"}
                  label="RTO risk"
                  value={d.rto_risk?.rto_probability != null
                    ? pct(d.rto_risk.rto_probability, 0) : "—"}
                  note={d.rto_risk?.risk_level || "No shipment on file"}
                />
                <Stat
                  tone={d.customer.value_tier === "HIGH" ? "retained" : "neutral"}
                  label="Customer value"
                  value={d.customer.value_tier}
                  note={`${moneyShort(d.customer.total_spend)} lifetime spend`}
                />
              </div>
            </Panel>

            {d.recovery_decision && (
              <Panel
                title="Recovery — next best action"
                note="Chosen on expected incremental profit, not on conversion rate."
              >
                <div className="stack">
                  <div className="row row--between">
                    <div>
                      <div className="label">Recommended</div>
                      <h2 style={{ marginTop: 4 }}>
                        {d.recovery_decision.next_best_action.label}
                      </h2>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="label">Expected profit</div>
                      <div
                        className="num"
                        style={{
                          fontSize: "1.5rem", fontWeight: 700,
                          color: d.recovery_decision.next_best_action.expected_profit >= 0
                            ? "var(--retained-ink)" : "var(--leaking-ink)",
                        }}
                      >
                        {money2(d.recovery_decision.next_best_action.expected_profit)}
                      </div>
                      <div className="tiny muted">
                        ROI {d.recovery_decision.next_best_action.roi === null
                          ? "n/a" : pctRaw(d.recovery_decision.next_best_action.roi, 0)}
                      </div>
                    </div>
                  </div>

                  <p className="muted" style={{ fontSize: "0.8125rem" }}>
                    {d.recovery_decision.rationale}
                  </p>

                  <ArithmeticLedger
                    rows={[
                      {
                        term: "Incremental revenue",
                        hint: `${pct(d.recovery_decision.next_best_action.uplift, 1)} uplift over doing nothing`,
                        amount: d.recovery_decision.next_best_action.incremental_revenue,
                      },
                      {
                        term: "Margin adjustment",
                        amount: d.recovery_decision.next_best_action.gross_profit
                          - d.recovery_decision.next_best_action.incremental_revenue,
                      },
                      {
                        term: "Discount + subsidy",
                        amount: -(d.recovery_decision.next_best_action.discount_cost
                          + d.recovery_decision.next_best_action.shipping_subsidy),
                      },
                      {
                        term: "Outreach cost",
                        amount: -d.recovery_decision.next_best_action.comms_cost,
                      },
                    ]}
                    total={{
                      term: "Expected incremental profit",
                      amount: d.recovery_decision.next_best_action.expected_profit,
                    }}
                    formatter={money2}
                  />

                  <div>
                    <div className="label" style={{ marginBottom: 7 }}>All actions compared</div>
                    <ActionComparison decision={d.recovery_decision} formatter={money2} />
                  </div>

                  {d.checkout_risk?.explanation && (
                    <div>
                      <div className="label" style={{ marginBottom: 7 }}>
                        Why the checkout risk is {pct(d.checkout_risk.abandonment_probability, 0)}
                      </div>
                      <Contributions items={d.checkout_risk.explanation} />
                    </div>
                  )}

                  {d.recovery_decision.inputs?.diagnosed_reason && (
                    <div>
                      <div className="label" style={{ marginBottom: 7 }}>
                        Diagnosed cause — {d.recovery_decision.inputs.diagnosed_reason.label}
                      </div>
                      <div className="stack stack--sm">
                        {d.recovery_decision.inputs.diagnosed_reason.evidence.map((e) => (
                          <div className="evidence" key={e.code}>
                            <em>{e.observed}</em>
                            <div className="tiny muted">{e.description}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Panel>
            )}

            {d.protection_decision && (
              <Panel
                title="Protection — next best action"
                note="Expected avoided loss against the cost of acting."
              >
                <div className="stack">
                  <div className="row row--between">
                    <div>
                      <div className="label">Recommended</div>
                      <h2 style={{ marginTop: 4 }}>
                        {d.protection_decision.next_best_action.label}
                      </h2>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="label">Expected profit</div>
                      <div
                        className="num"
                        style={{
                          fontSize: "1.5rem", fontWeight: 700,
                          color: d.protection_decision.next_best_action.expected_profit >= 0
                            ? "var(--retained-ink)" : "var(--leaking-ink)",
                        }}
                      >
                        {money2(d.protection_decision.next_best_action.expected_profit)}
                      </div>
                    </div>
                  </div>

                  <p className="muted" style={{ fontSize: "0.8125rem" }}>
                    {d.protection_decision.rationale}
                  </p>

                  {d.voc_signals?.length > 0 && (
                    <div>
                      <div className="label" style={{ marginBottom: 6 }}>
                        Review signals feeding this decision
                      </div>
                      <SignalChain
                        nodes={[
                          "Product reviews",
                          d.voc_signals.map((s) => titleCase(s)).join(" + "),
                          "Protection shortlist",
                          d.protection_decision.next_best_action.label,
                        ]}
                      />
                    </div>
                  )}

                  <ArithmeticLedger
                    rows={[
                      {
                        term: "Expected loss avoided",
                        amount: d.protection_decision.next_best_action.expected_revenue,
                      },
                      {
                        term: "Cost of acting",
                        amount: -d.protection_decision.next_best_action.total_cost,
                      },
                    ]}
                    total={{
                      term: "Expected profit",
                      amount: d.protection_decision.next_best_action.expected_profit,
                    }}
                    formatter={money2}
                  />

                  <div className="row">
                    <Tag tone="assumed">Assumed effect</Tag>
                    <span className="tiny muted">
                      {d.protection_decision.next_best_action.notes}
                    </span>
                  </div>

                  <div>
                    <div className="label" style={{ marginBottom: 7 }}>All actions compared</div>
                    <ActionComparison decision={d.protection_decision} formatter={money2} />
                  </div>

                  {d.return_risk?.top_factors?.length > 0 && (
                    <div>
                      <div className="label" style={{ marginBottom: 7 }}>
                        Why the return risk is {pct(d.return_risk.return_probability, 0)}
                      </div>
                      <Contributions items={d.return_risk.top_factors} />
                    </div>
                  )}
                </div>
              </Panel>
            )}

            {d.anomaly && d.anomaly.risk_level !== "LOW" && (
              <Panel title="Anomaly check" note={d.anomaly.note}>
                <div className="stack">
                  <div className="row">
                    <Risk level={d.anomaly.risk_level} score={d.anomaly.anomaly_score}
                          label="Anomaly score" />
                    <Tag tone="watch">{titleCase(d.anomaly.anomaly_class)}</Tag>
                  </div>
                  <div className="stack stack--sm">
                    {d.anomaly.evidence.map((e, i) => (
                      <div className="evidence" key={i}><em>{e}</em></div>
                    ))}
                  </div>
                </div>
              </Panel>
            )}

            {!d.recovery_decision && !d.protection_decision && (
              <Empty
                title="Not enough history for this customer"
                body="This customer has no abandoned cart and no order, so there is nothing to decide on yet."
              />
            )}

            <Disclosure text={d.disclosure} />
          </>
        )}
      </div>
    </>
  );
}

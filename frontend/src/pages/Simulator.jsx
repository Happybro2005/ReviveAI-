import { useEffect, useState } from "react";

import { Masthead } from "../App";
import { api } from "../api/client";
import { useThemeTokens } from "../components/charts";
import {
  ArithmeticLedger,
  Disclosure,
  ErrorState,
  LedgerStrip,
  Loading,
  Panel,
  Stat,
} from "../components/primitives";
import { useAction, useApi } from "../hooks/useApi";
import { money, moneyShort, num, pct, pctRaw } from "../lib/format";

const SLIDERS = [
  { key: "abandonment_rate", label: "Abandonment rate", min: 0, max: 1, step: 0.01, format: (v) => pct(v, 0) },
  { key: "recovery_rate", label: "Recovery rate", min: 0, max: 1, step: 0.01, format: (v) => pct(v, 0) },
  { key: "discount_rate", label: "Discount offered", min: 0, max: 0.5, step: 0.01, format: (v) => pct(v, 0) },
  { key: "gross_margin", label: "Gross margin", min: 0, max: 1, step: 0.01, format: (v) => pct(v, 0) },
  { key: "contact_coverage", label: "Carts contacted", min: 0, max: 1, step: 0.05, format: (v) => pct(v, 0) },
];

const NUMBERS = [
  { key: "checkout_volume", label: "Monthly checkouts", step: 1000, min: 0 },
  { key: "average_order_value", label: "Average order value (₹)", step: 100, min: 0 },
  { key: "delivery_cost_per_order", label: "Delivery cost per order (₹)", step: 5, min: 0 },
  { key: "intervention_cost_per_contact", label: "Outreach cost per contact (₹)", step: 0.25, min: 0 },
];

export default function Simulator() {
  const t = useThemeTokens();
  const defaults = useApi(() => api.simulatorDefaults(), []);
  const calc = useAction(api.simulate);
  const [form, setForm] = useState(null);

  useEffect(() => {
    if (defaults.data && !form) {
      const { source, disclosure, ...values } = defaults.data;
      setForm(values);
    }
  }, [defaults.data, form]);

  // Recompute whenever an input changes; the maths is cheap and instant feedback
  // is the point of a simulator.
  useEffect(() => {
    if (form) calc.run(form);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const r = calc.data;

  return (
    <>
      <Masthead
        eyebrow="Engine"
        title="Revenue simulator"
        sub="What recovery is worth at rates you choose. Pure arithmetic — no model involved, and every intermediate figure is shown."
      />

      <div className="page">
        {defaults.loading && <Loading rows={4} />}
        {defaults.error && (
          <ErrorState error={defaults.error} onRetry={defaults.reload} what="simulator defaults" />
        )}

        {form && (
          <div className="grid grid--sidebar">
            <div className="stack">
              <Panel
                title="Assumptions"
                note={defaults.data?.source}
                actions={
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => {
                      const { source, disclosure, ...values } = defaults.data;
                      setForm(values);
                    }}
                  >
                    Reset to observed
                  </button>
                }
              >
                <div className="stack">
                  <div className="grid grid--2">
                    {NUMBERS.map((n) => (
                      <div className="field" key={n.key}>
                        <label htmlFor={`sim-${n.key}`}>{n.label}</label>
                        <input
                          id={`sim-${n.key}`}
                          type="number"
                          min={n.min}
                          step={n.step}
                          value={form[n.key]}
                          onChange={(e) => set(n.key, Math.max(0, Number(e.target.value) || 0))}
                        />
                      </div>
                    ))}
                  </div>

                  <div className="stack">
                    {SLIDERS.map((s) => (
                      <div className="slider" key={s.key}>
                        <div className="slider__top">
                          <label htmlFor={`sim-${s.key}`} className="label">{s.label}</label>
                          <span className="slider__value">{s.format(form[s.key])}</span>
                        </div>
                        <input
                          id={`sim-${s.key}`}
                          type="range"
                          min={s.min}
                          max={s.max}
                          step={s.step}
                          value={form[s.key]}
                          onChange={(e) => set(s.key, Number(e.target.value))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </Panel>

              {r && (
                <Panel title="The arithmetic" note="Every term, in the order it is applied.">
                  <ArithmeticLedger
                    rows={[
                      {
                        term: "Gross margin on recovered revenue",
                        hint: `${moneyShort(r.recovered_revenue)} × ${pct(form.gross_margin, 0)}`,
                        amount: r.gross_profit,
                      },
                      { term: "Discount honoured", amount: -r.discount_cost },
                      { term: "Delivery cost on recovered orders", amount: -r.delivery_cost },
                      {
                        term: "Outreach cost",
                        hint: `${num(r.contacted_checkouts)} carts contacted`,
                        amount: -r.outreach_cost,
                      },
                    ]}
                    total={{ term: "Net profit", amount: r.net_profit }}
                  />
                </Panel>
              )}
            </div>

            <div className="stack">
              {calc.error && <ErrorState error={calc.error} what="the calculation" />}

              {r && (
                <>
                  <div className="grid grid--2">
                    <Stat tone="leaking" label="Revenue at risk" value={moneyShort(r.revenue_at_risk)}
                          note={`${num(r.abandoned_checkouts)} abandoned checkouts`} />
                    <Stat tone="retained" label="Recovered revenue" value={moneyShort(r.recovered_revenue)}
                          note={`${num(r.recovered_orders)} orders brought back`} />
                    <Stat tone={r.net_profit >= 0 ? "retained" : "leaking"} label="Net profit"
                          value={moneyShort(r.net_profit)}
                          note={`After ${moneyShort(r.total_cost)} of cost`} />
                    <Stat tone="neutral" label="ROI"
                          value={r.roi_percent === null ? "n/a" : pctRaw(r.roi_percent, 0)}
                          note={r.roi_percent === null
                            ? "No cost incurred, so ROI is undefined"
                            : "Net profit over total cost"} />
                  </div>

                  <Panel title="Where the at-risk revenue goes">
                    <LedgerStrip
                      segments={[
                        {
                          key: "recovered",
                          label: "Recovered",
                          value: r.recovered_revenue,
                          color: t.retained,
                          textColor: "var(--retained-ink)",
                        },
                        {
                          key: "lost",
                          label: "Stays lost",
                          value: r.unrecovered_revenue,
                          color: t.leaking,
                          textColor: "var(--leaking-ink)",
                        },
                      ]}
                    />
                  </Panel>

                  <Panel title="Per-order economics">
                    <dl className="dl">
                      <dt>Profit per recovered order</dt>
                      <dd>
                        {r.profit_per_recovered_order === null
                          ? "—" : money(r.profit_per_recovered_order, { precise: true })}
                      </dd>
                      <dt>Discount cost</dt>
                      <dd>{money(r.discount_cost)}</dd>
                      <dt>Delivery cost</dt>
                      <dd>{money(r.delivery_cost)}</dd>
                      <dt>Outreach cost</dt>
                      <dd>{money(r.outreach_cost)}</dd>
                      <dt>Total cost</dt>
                      <dd>{money(r.total_cost)}</dd>
                    </dl>
                    <p className="tiny muted" style={{ marginTop: 12 }}>
                      Outreach is charged on every cart contacted, not only the ones that convert,
                      because that is what actually happens when the messages go out.
                    </p>
                  </Panel>

                  <Disclosure text={r.disclosure} />
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

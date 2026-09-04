import { useState } from "react";

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, useThemeTokens } from "../components/charts";
import {
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  Stat,
  Tag,
} from "../components/primitives";
import { useApi } from "../hooks/useApi";
import { money, moneyShort, num, pct, pctRaw, titleCase } from "../lib/format";

export default function Interventions() {
  const [days, setDays] = useState(180);
  const t = useThemeTokens();
  const { data, error, loading, reload } = useApi(() => api.recoveryOverview(days), [days]);
  const catalogue = useApi(() => api.actionCatalogue(), []);

  const totals = data
    ? data.by_action.reduce(
        (acc, a) => ({
          sent: acc.sent + a.sent,
          converted: acc.converted + a.converted,
          revenue: acc.revenue + a.revenue,
          profit: acc.profit + a.profit,
        }),
        { sent: 0, converted: 0, revenue: 0, profit: 0 },
      )
    : null;

  return (
    <>
      <Masthead
        eyebrow="Recover"
        title="Interventions"
        sub="What was sent, what it achieved, and what it cost. Outcome tracking closes the loop back into the models."
        actions={
          <div className="field" style={{ minWidth: 150 }}>
            <label htmlFor="iv-window">Window</label>
            <select id="iv-window" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[30, 90, 180, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}
            </select>
          </div>
        }
      />

      <div className="page">
        {loading && <Loading rows={4} />}
        {error && <ErrorState error={error} onRetry={reload} what="intervention data" />}

        {data && totals && (
          <>
            <div className="grid grid--4">
              <Stat tone="neutral" label="Interventions sent" value={num(totals.sent)} />
              <Stat tone="retained" label="Converted" value={num(totals.converted)}
                    note={totals.sent > 0 ? pct(totals.converted / totals.sent, 1) + " conversion rate" : "—"} />
              <Stat tone="retained" label="Revenue attributed" value={moneyShort(totals.revenue)} />
              <Stat tone={totals.profit >= 0 ? "retained" : "leaking"} label="Realised profit"
                    value={moneyShort(totals.profit)}
                    note="Revenue at margin, net of discount and outreach cost" />
            </div>

            {data.by_action.length === 0 ? (
              <Empty
                title="No interventions in this window"
                body="Send one from the recovery worklist, or widen the window."
              />
            ) : (
              <>
                <div className="grid grid--2">
                  <Panel title="Conversion rate by action">
                    <BarsChart
                      data={data.by_action.map((a) => ({
                        name: titleCase(a.action),
                        rate: Number((a.conversion_rate * 100).toFixed(1)),
                      }))}
                      xKey="name" layout="vertical" yWidth={155} height={250}
                      formatter={(v) => `${v}%`}
                      series={[{ key: "rate", label: "Conversion %", color: t.structure }]}
                    />
                  </Panel>
                  <Panel
                    title="Realised profit by action"
                    note="The ranking that matters — conversion alone does not pay the bills."
                  >
                    <BarsChart
                      data={data.by_action.map((a) => ({
                        name: titleCase(a.action), profit: Math.round(a.profit),
                      }))}
                      xKey="name" layout="vertical" yWidth={155} height={250}
                      formatter={moneyShort}
                      series={[{ key: "profit", label: "Profit", color: t.retained }]}
                    />
                  </Panel>
                </div>

                <Panel title="Action performance" flush>
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
                          <th className="n">Profit per send</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.by_action.map((a) => (
                          <tr key={a.action}>
                            <td>{titleCase(a.action)}</td>
                            <td className="n">{num(a.sent)}</td>
                            <td className="n">{num(a.converted)}</td>
                            <td className="n">{pct(a.conversion_rate, 1)}</td>
                            <td className="n">{money(a.revenue)}</td>
                            <td className="n" style={{
                              color: a.profit >= 0 ? "var(--retained-ink)" : "var(--leaking-ink)",
                            }}>
                              {money(a.profit)}
                            </td>
                            <td className="n">
                              {a.sent > 0 ? money(a.profit / a.sent, { precise: true }) : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </>
            )}

            {catalogue.data && (
              <Panel
                title="Action catalogue"
                note="What the decision engine can choose from, and whether each effect is learned or assumed."
                flush
              >
                <div className="tablewrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Pillar</th><th>Action</th><th>Channel</th>
                        <th className="n">Assumed reduction</th><th className="n">Cost</th>
                        <th>Effect basis</th>
                      </tr>
                    </thead>
                    <tbody>
                      {catalogue.data.recovery.map((a) => (
                        <tr key={`r-${a.action}`}>
                          <td><Tag>Recover</Tag></td>
                          <td>{a.label}</td>
                          <td className="tiny muted">—</td>
                          <td className="n tiny muted">—</td>
                          <td className="n tiny muted">varies</td>
                          <td><Tag tone="learned">Learned</Tag></td>
                        </tr>
                      ))}
                      {catalogue.data.protection.map((a) => (
                        <tr key={`p-${a.action}`}>
                          <td><Tag>Protect</Tag></td>
                          <td>{a.label}</td>
                          <td className="tiny">{titleCase(a.channel)}</td>
                          <td className="n">
                            {a.rto_reduction > 0 && `${pct(a.rto_reduction, 0)} RTO`}
                            {a.rto_reduction > 0 && a.return_reduction > 0 && " · "}
                            {a.return_reduction > 0 && `${pct(a.return_reduction, 0)} return`}
                            {a.rto_reduction === 0 && a.return_reduction === 0 && "—"}
                          </td>
                          <td className="n">{money(a.fixed_cost, { precise: true })}</td>
                          <td><Tag tone="assumed">Assumed</Tag></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={{ padding: 14 }}>
                  <div className="disclosure">
                    <strong>Learned vs assumed.</strong>
                    <span>{catalogue.data.assumption_disclosure}</span>
                  </div>
                </div>
              </Panel>
            )}

            <Disclosure text={data.disclosure} />
          </>
        )}
      </div>
    </>
  );
}

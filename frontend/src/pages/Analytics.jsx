import { useState } from "react";

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, TrendChart, useThemeTokens } from "../components/charts";
import {
  Disclosure,
  Empty,
  ErrorState,
  LedgerStrip,
  Loading,
  Panel,
  Stat,
  Tag,
} from "../components/primitives";
import { useApi } from "../hooks/useApi";
import { money, moneyShort, num, pct, titleCase } from "../lib/format";

/**
 * Cross-pillar analytics. The point of this page is the join: which review
 * concerns line up with which fulfilment losses, so a seller can see the same
 * problem from both sides.
 */
export default function Analytics() {
  const [days, setDays] = useState(365);
  const t = useThemeTokens();

  const recovery = useApi(() => api.recoveryOverview(days), [days]);
  const protection = useApi(() => api.protectionOverview(days), [days]);
  const voc = useApi(() => api.vocInsights(), []);

  const loading = recovery.loading || protection.loading || voc.loading;
  const error = recovery.error || protection.error || voc.error;

  const r = recovery.data;
  const p = protection.data;
  const v = voc.data;

  /* Line up each review concern with the fulfilment loss it maps to. */
  const crosswalk = v && p
    ? v.top_concerns
        .filter((c) => c.risk_signal)
        .map((c) => {
          const isReturn = c.risk_signal === "RETURN_RISK";
          return {
            concern: c.aspect_label,
            mentions: c.negative_mentions,
            share: c.share_of_reviews,
            signal: c.risk_signal,
            observedEvents: isReturn ? p.returns : p.rto_count,
            observedLoss: isReturn ? p.return_loss : p.rto_loss,
            eventLabel: isReturn ? "returns" : "RTO shipments",
          };
        })
    : [];

  return (
    <>
      <Masthead
        eyebrow="Engine"
        title="Analytics"
        sub="The three pillars side by side, and the crosswalk between what customers complain about and what fulfilment actually loses."
        actions={
          <div className="field" style={{ minWidth: 150 }}>
            <label htmlFor="an-window">Window</label>
            <select id="an-window" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[90, 180, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}
            </select>
          </div>
        }
      />

      <div className="page">
        {loading && <Loading rows={5} />}
        {error && (
          <ErrorState
            error={error}
            what="analytics"
            onRetry={() => { recovery.reload(); protection.reload(); voc.reload(); }}
          />
        )}

        {r && p && v && (
          <>
            <Panel
              title="Total revenue leakage"
              note="Every stream of lost revenue in one flow, priced with the published cost model."
            >
              <LedgerStrip
                segments={[
                  {
                    key: "abandon",
                    label: "Abandoned carts",
                    value: r.revenue_at_risk - r.recovered_revenue,
                    color: t.leaking,
                    textColor: "var(--leaking-ink)",
                    sub: `${num(r.abandoned)} checkouts`,
                  },
                  {
                    key: "refund",
                    label: "Refunds",
                    value: p.refund_value,
                    color: t.watch,
                    textColor: "var(--watch-ink)",
                    sub: `${num(p.returns)} returns`,
                  },
                  {
                    key: "rto",
                    label: "RTO logistics",
                    value: p.rto_loss,
                    color: t.series[4],
                    sub: `${num(p.rto_count)} shipments`,
                  },
                  {
                    key: "returnops",
                    label: "Return handling",
                    value: p.return_loss,
                    color: t.series[5],
                    sub: "logistics + restock + margin",
                  },
                ]}
              />
            </Panel>

            <div className="grid grid--4">
              <Stat tone="retained" label="Recovered" value={moneyShort(r.recovered_revenue)}
                    note={`${pct(r.recovery_rate, 1)} of abandoned carts`} />
              <Stat tone="leaking" label="Abandonment" value={pct(r.abandonment_rate, 1)}
                    note={`${num(r.sessions)} checkouts in window`} />
              <Stat tone="leaking" label="RTO rate" value={pct(p.rto_rate, 1)}
                    note={`${num(p.shipments)} shipments`} />
              <Stat tone="leaking" label="Return rate" value={pct(p.return_rate, 1)}
                    note={`${num(p.orders)} orders`} />
            </div>

            <Panel
              title="Reviews to fulfilment crosswalk"
              note="Each customer concern next to the fulfilment loss it feeds. This is the join that makes Voice of Customer operational rather than decorative."
              flush
            >
              {crosswalk.length === 0 ? (
                <Empty
                  title="No analysed reviews yet"
                  body="Run scripts/analyze_reviews.py to build this crosswalk."
                />
              ) : (
                <div className="tablewrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Customer concern</th>
                        <th className="n">Negative reviews</th>
                        <th className="n">Share of reviews</th>
                        <th>Feeds</th>
                        <th className="n">Observed events</th>
                        <th className="n">Observed loss</th>
                      </tr>
                    </thead>
                    <tbody>
                      {crosswalk.map((c) => (
                        <tr key={c.concern}>
                          <td>{c.concern}</td>
                          <td className="n">{num(c.mentions)}</td>
                          <td className="n">{pct(c.share, 1)}</td>
                          <td>
                            <Tag tone={c.signal === "RETURN_RISK" ? "leaking" : "watch"}>
                              {c.signal.replace(/_/g, " ")}
                            </Tag>
                          </td>
                          <td className="n">
                            {num(c.observedEvents)}
                            <div className="tiny muted">{c.eventLabel}</div>
                          </td>
                          <td className="n">{money(c.observedLoss)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <div className="grid grid--2">
              <Panel title="Recovery trend" note="Abandoned versus recovered carts, weekly.">
                <TrendChart
                  data={r.trend}
                  xKey="week"
                  formatter={(x) => num(x)}
                  series={[
                    { key: "abandoned", label: "Abandoned", color: t.leaking },
                    { key: "recovered", label: "Recovered", color: t.retained },
                  ]}
                />
              </Panel>
              <Panel title="Courier RTO rate" note="Where logistics recommendations come from.">
                <BarsChart
                  data={p.couriers.map((c) => ({
                    name: c.courier, rate: Number((c.rto_rate * 100).toFixed(1)),
                  }))}
                  xKey="name" layout="vertical" yWidth={110} height={240}
                  formatter={(x) => `${x}%`}
                  series={[{ key: "rate", label: "RTO %", color: t.leaking }]}
                />
              </Panel>
            </div>

            <div className="grid grid--2">
              <Panel title="Abandonment reasons" flush>
                <div className="tablewrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Reason</th><th className="n">Carts</th>
                        <th className="n">Value</th><th className="n">Recovery rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.by_reason.map((x) => (
                        <tr key={x.reason}>
                          <td>{titleCase(x.reason)}</td>
                          <td className="n">{num(x.count)}</td>
                          <td className="n">{money(x.value)}</td>
                          <td className="n">{pct(x.recovery_rate, 1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
              <Panel title="Return reasons" flush>
                <div className="tablewrap">
                  <table className="data">
                    <thead>
                      <tr><th>Reason</th><th className="n">Returns</th><th className="n">Refund value</th></tr>
                    </thead>
                    <tbody>
                      {p.return_reasons.map((x) => (
                        <tr key={x.reason}>
                          <td>{titleCase(x.reason)}</td>
                          <td className="n">{num(x.count)}</td>
                          <td className="n">{money(x.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </div>

            <Disclosure text={r.disclosure} />
          </>
        )}
      </div>
    </>
  );
}

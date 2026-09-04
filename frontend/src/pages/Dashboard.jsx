import { useState } from "react";
import { Link } from "react-router-dom";

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, DonutChart, FunnelBars, TrendChart, useThemeTokens } from "../components/charts";
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
import { money, moneyShort, num, pct } from "../lib/format";

const WINDOWS = [
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: 180, label: "180 days" },
  { value: 365, label: "365 days" },
];

export default function Dashboard() {
  const [days, setDays] = useState(180);
  const t = useThemeTokens();
  const { data, error, loading, reload } = useApi(() => api.dashboard(days), [days]);

  const k = data?.kpis;

  /* The signature ledger: where the money actually went in this window.
     Completed revenue, revenue recovered from abandonment, and the two
     leakage streams, as one proportional flow. */
  const ledgerSegments = data
    ? [
        {
          key: "completed",
          label: "Completed",
          value: (data.revenue_leakage || []).reduce((s, r) => s + r.completed_value, 0),
          color: t.structure,
        },
        {
          key: "recovered",
          label: "Recovered",
          value: k.revenue_recovered,
          color: t.retained,
          textColor: "var(--retained-ink)",
          sub: `${pct(k.recovery_rate, 1)} of carts`,
        },
        {
          key: "at-risk",
          label: "Still at risk",
          value: Math.max(k.revenue_at_risk - k.revenue_recovered, 0),
          color: t.leaking,
          textColor: "var(--leaking-ink)",
          sub: "unrecovered carts",
        },
        {
          key: "fulfilment",
          label: "Lost to RTO & returns",
          value: k.revenue_protected_opportunity,
          color: t.watch,
          textColor: "var(--watch-ink)",
          sub: `${num(k.rto_count)} RTO · ${num(k.return_count)} returns`,
        },
      ]
    : [];

  const sentimentData = data
    ? Object.entries(data.sentiment_distribution || {}).map(([name, value]) => ({
        name: name.charAt(0) + name.slice(1).toLowerCase(),
        value,
        color:
          name === "POSITIVE"
            ? t.retained
            : name === "NEGATIVE"
              ? t.leaking
              : name === "MIXED"
                ? t.watch
                : t.structure,
      }))
    : [];

  return (
    <>
      <Masthead
        eyebrow="Command view"
        title="Revenue intelligence"
        sub="Where revenue is leaking right now, what the models predict, and which actions pay for themselves."
        actions={
          <div className="field" style={{ minWidth: 150 }}>
            <label htmlFor="dash-window">Window</label>
            <select
              id="dash-window"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              {WINDOWS.map((w) => (
                <option key={w.value} value={w.value}>
                  Last {w.label}
                </option>
              ))}
            </select>
          </div>
        }
      />

      <div className="page">
        {loading && <Loading rows={5} label="Loading dashboard" />}
        {error && <ErrorState error={error} onRetry={reload} what="the dashboard" />}

        {data && (
          <>
            <Disclosure text={data.disclosure} />

            <Panel
              title="Revenue flow"
              note={data.kpi_basis}
            >
              <LedgerStrip segments={ledgerSegments} />
            </Panel>

            <div className="grid grid--4">
              <Stat
                tone="retained"
                label="Revenue recovered"
                value={moneyShort(k.revenue_recovered)}
                note={`${pct(k.recovery_rate, 1)} of abandoned carts came back`}
              />
              <Stat
                tone="leaking"
                label="Revenue at risk"
                value={moneyShort(k.revenue_at_risk)}
                note={`${pct(k.abandonment_rate, 1)} checkout abandonment rate`}
              />
              <Stat
                tone="retained"
                label="Incremental profit"
                value={moneyShort(k.incremental_profit)}
                note="Realised profit from recorded conversions, net of cost"
              />
              <Stat
                tone="watch"
                label="Protection opportunity"
                value={moneyShort(k.revenue_protected_opportunity)}
                note="Observed RTO and return loss that protection actions target"
              />
              <Stat
                tone="leaking"
                label="RTO"
                value={`${num(k.rto_count)}`}
                note={`${pct(k.rto_rate, 1)} of shipments · ${moneyShort(k.revenue_leaking_to_rto)} lost`}
              />
              <Stat
                tone="leaking"
                label="Returns"
                value={`${num(k.return_count)}`}
                note={`${pct(k.return_rate, 1)} of orders · ${moneyShort(k.revenue_leaking_to_returns)} lost`}
              />
              <Stat
                tone="watch"
                label="Anomalies flagged"
                value={num(k.anomaly_count)}
                note={`${moneyShort(k.anomaly_exposure)} exposure on customer-behaviour flags`}
              />
              <Stat
                tone="neutral"
                label="Reviews analysed"
                value={num(k.analysed_reviews)}
                note={`of ${num(k.total_reviews)} · ${k.average_rating} average rating`}
              />
            </div>

            <div className="grid grid--sidebar">
              <Panel
                title="Revenue leakage over time"
                note="Cart value completed versus abandoned, by month."
              >
                <TrendChart
                  data={data.revenue_leakage}
                  xKey="month"
                  formatter={moneyShort}
                  series={[
                    { key: "completed_value", label: "Completed", color: t.structure },
                    { key: "abandoned_value", label: "Abandoned", color: t.leaking },
                  ]}
                />
              </Panel>

              <Panel title="Recovery funnel" note="Checkout to recovered revenue.">
                <FunnelBars stages={data.recovery_funnel} />
              </Panel>
            </div>

            <div className="grid grid--sidebar">
              <Panel
                title="Top customer concerns"
                note="Negative aspect mentions across analysed reviews. Each concern is wired to a downstream risk signal."
                actions={
                  <Link to="/voice-of-customer" className="btn btn--sm">
                    Open Voice of Customer
                  </Link>
                }
              >
                {data.top_concerns.length === 0 ? (
                  <Empty
                    title="No reviews analysed yet"
                    body="Run scripts/analyze_reviews.py to populate customer concerns."
                  />
                ) : (
                  <>
                    <BarsChart
                      data={data.top_concerns.map((c) => ({
                        name: c.aspect_label,
                        mentions: c.negative_mentions,
                      }))}
                      xKey="name"
                      layout="vertical"
                      yWidth={118}
                      height={230}
                      formatter={(v) => num(v)}
                      series={[{ key: "mentions", label: "Negative mentions", color: t.leaking }]}
                    />
                    <div className="tablewrap" style={{ marginTop: 12 }}>
                      <table className="data">
                        <thead>
                          <tr>
                            <th>Concern</th>
                            <th className="n">Negative</th>
                            <th className="n">Share</th>
                            <th>Feeds</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.top_concerns.map((c) => (
                            <tr key={c.aspect}>
                              <td>{c.aspect_label}</td>
                              <td className="n">{num(c.negative_mentions)}</td>
                              <td className="n">{pct(c.negative_share, 1)}</td>
                              <td>
                                {c.risk_signal ? (
                                  <Tag
                                    tone={
                                      c.risk_signal === "RETURN_RISK" ? "leaking" : "watch"
                                    }
                                  >
                                    {c.risk_signal.replace(/_/g, " ")}
                                  </Tag>
                                ) : (
                                  <span className="muted tiny">—</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </Panel>

              <Panel title="Customer sentiment" note="Across every analysed review.">
                {sentimentData.length === 0 ? (
                  <Empty title="No sentiment yet" body="No reviews have been analysed." />
                ) : (
                  <DonutChart data={sentimentData} />
                )}
              </Panel>
            </div>

            <Panel
              title="AI recommendations"
              note="Each recommendation is backed by counted review evidence and priced with observed loss."
              actions={
                <Link to="/voice-of-customer" className="btn btn--sm">
                  See all
                </Link>
              }
            >
              {data.recommendations.length === 0 ? (
                <Empty
                  title="No recommendations yet"
                  body="Recommendations appear once reviews have been analysed and aggregated."
                />
              ) : (
                <div className="stack">
                  {data.recommendations.map((r, i) => (
                    <div key={i} className={`reccard reccard--${r.priority.toLowerCase()}`}>
                      <div className="reccard__head">
                        <div className="reccard__problem">{r.problem}</div>
                        <Tag
                          tone={
                            r.priority === "CRITICAL" || r.priority === "HIGH"
                              ? "leaking"
                              : r.priority === "MEDIUM"
                                ? "watch"
                                : "retained"
                          }
                        >
                          {r.priority}
                        </Tag>
                      </div>
                      <div className="reccard__action">{r.recommendation}</div>
                      <div className="reccard__foot">
                        <span>
                          <strong className="num">{num(r.supporting_review_count)}</strong> reviews
                        </span>
                        <span>
                          Observed loss{" "}
                          <strong className="num">{money(r.estimated_business_impact)}</strong>
                        </span>
                        {r.linked_risk_signal && (
                          <span>Feeds {r.linked_risk_signal.replace(/_/g, " ").toLowerCase()}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}
      </div>
    </>
  );
}

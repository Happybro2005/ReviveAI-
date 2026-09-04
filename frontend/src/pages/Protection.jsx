import { useState } from "react";
import { Link } from "react-router-dom";

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, useThemeTokens } from "../components/charts";
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

export default function Protection() {
  const [days, setDays] = useState(180);
  const t = useThemeTokens();
  const { data, error, loading, reload } = useApi(() => api.protectionOverview(days), [days]);

  return (
    <>
      <Masthead
        eyebrow="Protect"
        title="Revenue protection"
        sub="Money that leaves after the sale: returns, undelivered shipments, and operational anomalies."
        actions={
          <div className="field" style={{ minWidth: 150 }}>
            <label htmlFor="prot-window">Window</label>
            <select id="prot-window" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[30, 90, 180, 365].map((d) => (
                <option key={d} value={d}>Last {d} days</option>
              ))}
            </select>
          </div>
        }
      />

      <div className="page">
        {loading && <Loading rows={4} />}
        {error && <ErrorState error={error} onRetry={reload} what="protection data" />}

        {data && (
          <>
            <Disclosure text={data.disclosure} />

            <Panel title="Where post-sale revenue goes" note={data.loss_basis}>
              <LedgerStrip
                segments={[
                  {
                    key: "kept",
                    label: "Delivered and kept",
                    value: Math.max(
                      data.order_value - data.rto_loss - data.return_loss - data.refund_value,
                      0,
                    ),
                    color: t.structure,
                  },
                  {
                    key: "refunds",
                    label: "Refunded",
                    value: data.refund_value,
                    color: t.watch,
                    textColor: "var(--watch-ink)",
                    sub: `${num(data.returns)} returns`,
                  },
                  {
                    key: "rto",
                    label: "RTO logistics loss",
                    value: data.rto_loss,
                    color: t.leaking,
                    textColor: "var(--leaking-ink)",
                    sub: `${num(data.rto_count)} shipments`,
                  },
                  {
                    key: "returnloss",
                    label: "Return handling loss",
                    value: data.return_loss,
                    color: t.series[4],
                    sub: "logistics + restock + margin",
                  },
                ]}
              />
            </Panel>

            <div className="grid grid--4">
              <Stat tone="leaking" label="RTO rate" value={pct(data.rto_rate, 1)}
                    note={`${num(data.rto_count)} of ${num(data.shipments)} shipments returned undelivered`} />
              <Stat tone="leaking" label="Return rate" value={pct(data.return_rate, 1)}
                    note={`${num(data.returns)} returns on ${num(data.orders)} orders`} />
              <Stat tone="watch" label="COD share" value={pct(data.cod_share, 1)}
                    note="Cash-on-delivery orders carry most of the RTO risk" />
              <Stat tone="watch" label="Late deliveries" value={num(data.late_deliveries)}
                    note={`Average ${data.avg_delivery_days} days against promise`} />
            </div>

            <div className="grid grid--2">
              <Panel title="Return reasons" note="Counted from actual return records.">
                {data.return_reasons.length === 0 ? (
                  <Empty title="No returns in this window" />
                ) : (
                  <BarsChart
                    data={data.return_reasons.map((r) => ({
                      name: titleCase(r.reason), count: r.count,
                    }))}
                    xKey="name" layout="vertical" yWidth={140} height={230}
                    formatter={(v) => num(v)}
                    series={[{ key: "count", label: "Returns", color: t.leaking }]}
                  />
                )}
              </Panel>
              <Panel title="RTO reasons" note="Why shipments came back undelivered.">
                {data.rto_reasons.length === 0 ? (
                  <Empty title="No RTO events in this window" />
                ) : (
                  <BarsChart
                    data={data.rto_reasons.map((r) => ({
                      name: titleCase(r.reason), count: r.count,
                    }))}
                    xKey="name" layout="vertical" yWidth={140} height={230}
                    formatter={(v) => num(v)}
                    series={[{ key: "count", label: "Shipments", color: t.watch }]}
                  />
                )}
              </Panel>
            </div>

            <Panel
              title="Courier performance"
              note="RTO and delay rates by carrier — the lane-level view behind logistics recommendations."
              flush
            >
              <div className="tablewrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Courier</th>
                      <th className="n">Shipments</th>
                      <th className="n">RTO</th>
                      <th className="n">RTO rate</th>
                      <th className="n">Late</th>
                      <th className="n">Avg days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.couriers.map((c) => (
                      <tr key={c.courier}>
                        <td>{c.courier}</td>
                        <td className="n">{num(c.shipments)}</td>
                        <td className="n">{num(c.rto)}</td>
                        <td className="n" style={{
                          color: c.rto_rate > 0.18 ? "var(--leaking-ink)" : "inherit",
                          fontWeight: c.rto_rate > 0.18 ? 700 : 400,
                        }}>
                          {pct(c.rto_rate, 1)}
                        </td>
                        <td className="n">{num(c.late)}</td>
                        <td className="n">{c.avg_days}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel
              title="Anomaly summary"
              note="Customer behaviour and operational anomalies are counted separately — an operational outlier is not a customer problem."
              actions={<Link to="/fraud" className="btn btn--sm">Open anomalies</Link>}
              flush
            >
              <div className="tablewrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Class</th>
                      <th>Risk level</th>
                      <th className="n">Count</th>
                      <th className="n">Exposure</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.anomalies.map((a, i) => (
                      <tr key={i}>
                        <td>
                          <Tag tone={a.anomaly_class === "CUSTOMER_BEHAVIOR" ? "watch" : undefined}>
                            {titleCase(a.anomaly_class)}
                          </Tag>
                        </td>
                        <td>{a.risk_level}</td>
                        <td className="n">{num(a.count)}</td>
                        <td className="n">{a.exposure > 0 ? money(a.exposure) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <div className="grid grid--3">
              <Link to="/returns" className="panel" style={{ padding: 16, textDecoration: "none", color: "inherit" }}>
                <div className="panel__title">Score return risk →</div>
                <p className="panel__note" style={{ marginTop: 6 }}>
                  Predict whether an order line will come back, with the review evidence that
                  drives it.
                </p>
              </Link>
              <Link to="/rto" className="panel" style={{ padding: 16, textDecoration: "none", color: "inherit" }}>
                <div className="panel__title">Score RTO risk →</div>
                <p className="panel__note" style={{ marginTop: 6 }}>
                  Predict undelivered shipments at order placement, while prevention is still
                  possible.
                </p>
              </Link>
              <Link to="/fraud" className="panel" style={{ padding: 16, textDecoration: "none", color: "inherit" }}>
                <div className="panel__title">Analyse anomalies →</div>
                <p className="panel__note" style={{ marginTop: 6 }}>
                  Business rules plus an isolation forest, kept apart from fraud accusations.
                </p>
              </Link>
            </div>
          </>
        )}
      </div>
    </>
  );
}

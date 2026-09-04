import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Masthead } from "../App";
import { api } from "../api/client";
import {
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  Stat,
  Tabs,
  Tag,
} from "../components/primitives";
import { useApi } from "../hooks/useApi";
import { date, money, moneyShort, num, pct, titleCase } from "../lib/format";

const TABS = [
  { id: "orders", label: "Orders" },
  { id: "payments", label: "Payments" },
  { id: "returns", label: "Returns" },
  { id: "checkout", label: "Checkout behaviour" },
  { id: "reviews", label: "Reviews" },
  { id: "interventions", label: "Interventions" },
];

function CustomerList({ onSelect }) {
  const [search, setSearch] = useState("");
  const [segment, setSegment] = useState("");
  const [query, setQuery] = useState({ limit: 25, offset: 0 });

  const { data, error, loading, reload } = useApi(
    () => api.customers({ ...query, ...(search ? { search } : {}), ...(segment ? { segment } : {}) }),
    [query, search, segment],
  );

  return (
    <Panel
      title="Customers"
      note="Select a customer to open their full record."
      actions={
        <div className="toolbar">
          <div className="field">
            <label htmlFor="c360-search">Search</label>
            <input id="c360-search" type="text" value={search} placeholder="Name, email or ID"
                   onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="c360-seg">Segment</label>
            <select id="c360-seg" value={segment} onChange={(e) => setSegment(e.target.value)}>
              <option value="">All segments</option>
              {["VIP", "LOYAL", "NEW", "PROSPECT"].map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
        </div>
      }
      flush
    >
      {loading && <div style={{ padding: 16 }}><Loading rows={4} /></div>}
      {error && <div style={{ padding: 16 }}><ErrorState error={error} onRetry={reload} what="customers" /></div>}
      {data && data.items.length === 0 && (
        <Empty title="No customers match" body="Clear the search or segment filter." />
      )}
      {data && data.items.length > 0 && (
        <>
          <div className="tablewrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Segment</th>
                  <th>City</th>
                  <th className="n">Orders</th>
                  <th className="n">Spend</th>
                  <th className="n">Returns</th>
                  <th className="n">RTO</th>
                  <th className="n">Abandoned</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id} className="is-clickable" onClick={() => onSelect(c.id)}>
                    <td>{c.name}<div className="tiny muted">{c.external_id}</div></td>
                    <td><Tag>{c.segment}</Tag></td>
                    <td>{c.city}</td>
                    <td className="n">{num(c.order_count)}</td>
                    <td className="n">{money(c.total_spend)}</td>
                    <td className="n">{num(c.return_count)}</td>
                    <td className="n">{num(c.rto_count)}</td>
                    <td className="n">{num(c.abandonment_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row row--between" style={{ padding: "10px 16px" }}>
            <span className="tiny muted">
              Showing {data.offset + 1}–{Math.min(data.offset + data.limit, data.total)} of{" "}
              {num(data.total)}
            </span>
            <div className="row">
              <button type="button" className="btn btn--sm" disabled={query.offset === 0}
                      onClick={() => setQuery((q) => ({ ...q, offset: Math.max(0, q.offset - q.limit) }))}>
                Previous
              </button>
              <button type="button" className="btn btn--sm"
                      disabled={data.offset + data.limit >= data.total}
                      onClick={() => setQuery((q) => ({ ...q, offset: q.offset + q.limit }))}>
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}

function CustomerDetail({ customerId, onBack }) {
  const [tab, setTab] = useState("orders");
  const { data, error, loading, reload } = useApi(() => api.customer(customerId), [customerId]);

  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorState error={error} onRetry={reload} what="this customer" />;
  if (!data) return null;

  const p = data.profile;
  const negativeAspects = data.review_aspects.filter((a) => a.sentiment === "NEGATIVE");

  return (
    <div className="stack">
      <Panel
        title={p.name}
        note={`${p.external_id} · ${p.city}, ${p.state} · joined ${date(p.signup_date)}`}
        actions={
          <div className="row">
            <Link to="/ai-decision-center" className="btn btn--sm">Open Decision Center</Link>
            <button type="button" className="btn btn--sm" onClick={onBack}>Back to list</button>
          </div>
        }
      >
        <div className="grid grid--4">
          <Stat tone="neutral" label="Segment" value={p.segment}
                note={`${p.value_tier} value tier`} />
          <Stat tone="retained" label="Lifetime spend" value={moneyShort(p.total_spend)}
                note={`${num(p.order_count)} orders · ${money(p.avg_order_value)} average`} />
          <Stat tone={p.return_rate > 0.3 ? "leaking" : "neutral"} label="Return rate"
                value={pct(p.return_rate, 1)} note={`${num(p.return_count)} returns`} />
          <Stat tone={p.rto_rate > 0.2 ? "leaking" : "neutral"} label="RTO rate"
                value={pct(p.rto_rate, 1)} note={`${num(p.rto_count)} undelivered shipments`} />
        </div>
      </Panel>

      {data.anomalies.length > 0 && (
        <Panel title="Anomaly flags" note="Review prompts raised on this customer.">
          <div className="stack stack--sm">
            {data.anomalies.map((a, i) => (
              <div key={i} className="row">
                <Tag tone={a.anomaly_class === "CUSTOMER_BEHAVIOR" ? "watch" : undefined}>
                  {titleCase(a.anomaly_class)}
                </Tag>
                <span className={`risk risk--${a.risk_level.toLowerCase()}`}>
                  <span className="risk__level">{a.risk_level}</span>
                  <span className="risk__score">{a.anomaly_score.toFixed(2)}</span>
                </span>
                <span className="tiny muted">{a.evidence}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {negativeAspects.length > 0 && (
        <Panel
          title="What this customer complains about"
          note="Aspect sentiment across their own reviews — the same signal that feeds their return risk."
        >
          <div className="row">
            {negativeAspects.map((a) => (
              <Tag key={a.aspect} tone="leaking">
                {titleCase(a.aspect)} · {a.count}
              </Tag>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="History" actions={<Tabs tabs={TABS} active={tab} onChange={setTab} />} flush>
        <div className="tablewrap">
          {tab === "orders" && (
            <table className="data">
              <thead>
                <tr>
                  <th>Order</th><th>Date</th><th className="n">Value</th><th>Payment</th>
                  <th>Status</th><th>Courier</th><th className="n">Days</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.order_ref}</td>
                    <td>{date(o.order_date)}</td>
                    <td className="n">{money(o.order_value)}</td>
                    <td>{o.payment_method}{o.is_cod && <> <Tag tone="watch">COD</Tag></>}</td>
                    <td>
                      <Tag tone={o.status === "RTO" || o.status === "RETURNED" ? "leaking" : undefined}>
                        {o.status}
                      </Tag>
                    </td>
                    <td className="tiny">{o.courier || "—"}</td>
                    <td className="n">
                      {o.actual_days ?? "—"}
                      {o.actual_days > o.promised_days && (
                        <span style={{ color: "var(--leaking-ink)" }}> late</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "payments" && (
            <table className="data">
              <thead>
                <tr>
                  <th>Reference</th><th>Attempted</th><th className="n">Amount</th>
                  <th>Method</th><th>Status</th><th>Failure reason</th><th className="n">Attempt</th>
                </tr>
              </thead>
              <tbody>
                {data.payments.map((x) => (
                  <tr key={x.id}>
                    <td className="tiny">{x.payment_ref}</td>
                    <td>{date(x.attempted_at)}</td>
                    <td className="n">{money(x.amount)}</td>
                    <td>{x.method}</td>
                    <td>
                      <Tag tone={x.status === "FAILED" ? "leaking" : "retained"}>{x.status}</Tag>
                    </td>
                    <td className="tiny muted">{x.failure_reason ? titleCase(x.failure_reason) : "—"}</td>
                    <td className="n">{x.attempt_number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "returns" && (
            data.returns.length === 0 ? (
              <Empty title="No returns" body="This customer has not returned anything." />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>Reference</th><th>Requested</th><th>Product</th>
                    <th>Reason</th><th className="n">Refund</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.returns.map((r) => (
                    <tr key={r.id}>
                      <td className="tiny">{r.return_ref}</td>
                      <td>{date(r.requested_at)}</td>
                      <td>{r.product_title}<div className="tiny muted">{r.category}</div></td>
                      <td><Tag tone="leaking">{titleCase(r.reason)}</Tag></td>
                      <td className="n">{money(r.refund_amount)}</td>
                      <td className="tiny">{r.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {tab === "checkout" && (
            <table className="data">
              <thead>
                <tr>
                  <th>Started</th><th className="n">Cart</th><th className="n">Shipping</th>
                  <th>Stage</th><th>Device</th><th>Outcome</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {data.checkout_sessions.map((s) => (
                  <tr key={s.id}>
                    <td>{date(s.started_at)}</td>
                    <td className="n">{money(s.cart_value)}</td>
                    <td className="n">
                      {money(s.shipping_cost)}
                      <span className="muted"> ({pct(s.shipping_cart_ratio, 0)})</span>
                    </td>
                    <td className="tiny">{titleCase(s.checkout_stage)}</td>
                    <td className="tiny">{titleCase(s.device_type)}</td>
                    <td>
                      {s.abandoned ? (
                        <Tag tone={s.recovered ? "retained" : "leaking"}>
                          {s.recovered ? "Recovered" : "Abandoned"}
                        </Tag>
                      ) : (
                        <Tag tone="retained">Completed</Tag>
                      )}
                    </td>
                    <td className="tiny muted">
                      {s.primary_reason ? titleCase(s.primary_reason) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "reviews" && (
            data.reviews.length === 0 ? (
              <Empty title="No reviews" body="This customer has not written a review." />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>Date</th><th>Product</th><th className="n">Rating</th>
                    <th>Sentiment</th><th>Review</th>
                  </tr>
                </thead>
                <tbody>
                  {data.reviews.map((r) => (
                    <tr key={r.id}>
                      <td>{date(r.review_date)}</td>
                      <td className="tiny">{r.product_title}</td>
                      <td className="n">{r.rating}</td>
                      <td>
                        {r.sentiment ? (
                          <Tag tone={
                            r.sentiment === "POSITIVE" ? "retained"
                              : r.sentiment === "NEGATIVE" ? "leaking"
                                : r.sentiment === "MIXED" ? "watch" : undefined
                          }>
                            {r.sentiment}
                          </Tag>
                        ) : <span className="muted tiny">Not analysed</span>}
                      </td>
                      <td className="tiny muted" style={{ maxWidth: 420 }}>{r.review_text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {tab === "interventions" && (
            data.interventions.length === 0 ? (
              <Empty
                title="No interventions yet"
                body="Send one from the recovery worklist to start tracking outcomes for this customer."
              />
            ) : (
              <table className="data">
                <thead>
                  <tr>
                    <th>Sent</th><th>Pillar</th><th>Action</th><th>Channel</th>
                    <th className="n">Predicted</th><th className="n">Expected profit</th>
                    <th>Outcome</th><th className="n">Realised profit</th>
                  </tr>
                </thead>
                <tbody>
                  {data.interventions.map((i) => (
                    <tr key={i.id}>
                      <td>{date(i.sent_at)}</td>
                      <td className="tiny">{i.pillar}</td>
                      <td>{titleCase(i.action)}</td>
                      <td className="tiny">{titleCase(i.channel)}</td>
                      <td className="n">{pct(i.predicted_probability, 0)}</td>
                      <td className="n">{money(i.expected_profit)}</td>
                      <td>
                        <Tag tone={
                          i.outcome === "CONVERTED" ? "retained"
                            : i.outcome === "PENDING" ? "watch" : "leaking"
                        }>
                          {titleCase(i.outcome)}
                        </Tag>
                      </td>
                      <td className="n">
                        {i.realised_profit != null ? money(i.realised_profit) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>
      </Panel>

      <Disclosure text={data.disclosure} />
    </div>
  );
}

export default function Customer360() {
  const { customerId } = useParams();
  const navigate = useNavigate();
  const [selected, setSelected] = useState(customerId ? Number(customerId) : null);

  useEffect(() => {
    setSelected(customerId ? Number(customerId) : null);
  }, [customerId]);

  return (
    <>
      <Masthead
        eyebrow="Engine"
        title="Customer 360"
        sub="Orders, payments, returns, shipments, reviews, risk scores and interventions for one customer, joined from the database."
      />
      <div className="page">
        {selected ? (
          <CustomerDetail
            customerId={selected}
            onBack={() => { setSelected(null); navigate("/customer-360"); }}
          />
        ) : (
          <CustomerList onSelect={(id) => navigate(`/customer-360/${id}`)} />
        )}
      </div>
    </>
  );
}

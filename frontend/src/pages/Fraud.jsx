import { useState } from "react";
import { Link } from "react-router-dom";

import { Masthead } from "../App";
import { api } from "../api/client";
import {
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  Risk,
  Tabs,
  Tag,
} from "../components/primitives";
import { useAction, useApi } from "../hooks/useApi";
import { money, num, titleCase } from "../lib/format";

const CLASSES = [
  { id: "", label: "All anomalies" },
  { id: "CUSTOMER_BEHAVIOR", label: "Customer behaviour" },
  { id: "LOGISTICS_OPERATIONAL", label: "Logistics / operational" },
];

export default function Fraud() {
  const [cls, setCls] = useState("");
  const [customerId, setCustomerId] = useState("");
  const list = useApi(
    () => api.anomalies({ limit: 50, offset: 0, ...(cls ? { anomaly_class: cls } : {}) }),
    [cls],
  );
  const analyze = useAction(api.analyzeFraud);

  return (
    <>
      <Masthead
        eyebrow="Protect"
        title="Anomalies"
        sub="Deterministic business rules paired with an isolation forest. An anomaly is a prompt to review, never a fraud determination."
      />

      <div className="page">
        <div className="disclosure">
          <strong>How to read this.</strong>
          <span>
            Customer-behaviour anomalies describe what a customer has done. Operational
            anomalies describe how a shipment was handled — a weight mismatch is a warehouse
            or courier issue, not a customer one. The two are never merged.
          </span>
        </div>

        <Panel
          title="Analyse a customer"
          note="Enter a customer ID to pull their behavioural aggregates and score them live."
        >
          <form
            className="toolbar"
            onSubmit={(e) => {
              e.preventDefault();
              analyze.run({ customer_id: Number(customerId) });
            }}
          >
            <div className="field">
              <label htmlFor="fraud-cust">Customer ID</label>
              <input
                id="fraud-cust"
                type="number"
                min={1}
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                placeholder="e.g. 42"
                required
              />
            </div>
            <button type="submit" className="btn btn--primary" disabled={analyze.loading}>
              {analyze.loading ? "Analysing…" : "Analyse"}
            </button>
          </form>

          {analyze.error && (
            <div style={{ marginTop: 14 }}>
              <ErrorState error={analyze.error} what="this customer" />
            </div>
          )}

          {analyze.data && (
            <div className="stack" style={{ marginTop: 16 }}>
              <div className="row">
                <Risk
                  level={analyze.data.risk_level}
                  score={analyze.data.anomaly_score}
                  label="Anomaly score"
                />
                <Tag tone={analyze.data.anomaly_class === "CUSTOMER_BEHAVIOR" ? "watch" : undefined}>
                  {titleCase(analyze.data.anomaly_class)}
                </Tag>
                {analyze.data.model_score !== null && (
                  <span className="tiny muted">
                    Isolation forest score {analyze.data.model_score.toFixed(3)}
                  </span>
                )}
              </div>

              <div>
                <div className="label" style={{ marginBottom: 6 }}>Evidence</div>
                <div className="stack stack--sm">
                  {analyze.data.evidence.map((e, i) => (
                    <div className="evidence" key={i}><em>{e}</em></div>
                  ))}
                </div>
              </div>

              {analyze.data.triggered_rules.length > 0 && (
                <div>
                  <div className="label" style={{ marginBottom: 6 }}>Rules triggered</div>
                  <div className="stack stack--sm">
                    {analyze.data.triggered_rules.map((r) => (
                      <div key={r.code} className="row" style={{ gap: 8 }}>
                        <Tag tone={r.anomaly_class === "CUSTOMER_BEHAVIOR" ? "watch" : undefined}>
                          {r.code.replace(/_/g, " ")}
                        </Tag>
                        <span className="tiny muted">{r.description}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="label" style={{ marginBottom: 5 }}>Recommended step</div>
                <div style={{ fontWeight: 600 }}>
                  {titleCase(analyze.data.recommended_action)}
                </div>
              </div>

              <p className="tiny muted">{analyze.data.note}</p>
            </div>
          )}
        </Panel>

        <Panel
          title="Detected anomalies"
          note="Stored anomaly events, highest score first."
          actions={<Tabs tabs={CLASSES} active={cls} onChange={setCls} />}
          flush
        >
          {list.loading && <div style={{ padding: 16 }}><Loading rows={4} /></div>}
          {list.error && (
            <div style={{ padding: 16 }}>
              <ErrorState error={list.error} onRetry={list.reload} what="anomalies" />
            </div>
          )}
          {list.data && list.data.items.length === 0 && (
            <Empty
              title="No anomalies in this class"
              body="Anomaly events are written by the data generator and the rule engine."
            />
          )}
          {list.data && list.data.items.length > 0 && (
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Class</th>
                    <th>Subject</th>
                    <th className="n">Score</th>
                    <th>Level</th>
                    <th>Evidence</th>
                    <th>Recommended step</th>
                    <th className="n">Exposure</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Tag tone={a.anomaly_class === "CUSTOMER_BEHAVIOR" ? "watch" : undefined}>
                          {a.anomaly_class === "CUSTOMER_BEHAVIOR" ? "Customer" : "Operational"}
                        </Tag>
                      </td>
                      <td>
                        {a.customer_id ? (
                          <Link to={`/customer-360/${a.customer_id}`}>
                            {a.customer_name || `Customer ${a.customer_id}`}
                          </Link>
                        ) : (
                          <span className="muted">Shipment {a.shipment_id}</span>
                        )}
                      </td>
                      <td className="n">{a.anomaly_score.toFixed(3)}</td>
                      <td>
                        <span className={`risk risk--${a.risk_level.toLowerCase()}`}>
                          <span className="risk__level">{a.risk_level}</span>
                        </span>
                      </td>
                      <td className="tiny muted">{a.evidence}</td>
                      <td className="tiny">{titleCase(a.recommended_action)}</td>
                      <td className="n">
                        {a.estimated_exposure > 0 ? money(a.estimated_exposure) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {list.data && <Disclosure text={list.data.disclosure} />}
      </div>
    </>
  );
}

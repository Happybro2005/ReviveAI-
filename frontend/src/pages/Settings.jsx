import { Masthead } from "../App";
import { api } from "../api/client";
import {
  Disclosure,
  ErrorState,
  Loading,
  Panel,
  Tag,
} from "../components/primitives";
import { useApi } from "../hooks/useApi";
import { money, titleCase } from "../lib/format";

/**
 * Settings is read-only on purpose.
 *
 * Every value here comes from the server's environment, and changing economics
 * from a browser would silently rewrite the numbers behind decisions already
 * recorded against interventions. The page shows what the engine is using and
 * where to change it.
 */
export default function Settings() {
  const health = useApi(() => api.health(), []);
  const catalogue = useApi(() => api.actionCatalogue(), []);
  const status = useApi(() => api.modelStatus(), []);

  const loading = health.loading || catalogue.loading || status.loading;
  const error = health.error || catalogue.error || status.error;
  const costs = catalogue.data?.cost_model;

  return (
    <>
      <Masthead
        eyebrow="Engine"
        title="Settings"
        sub="What this deployment is running: connection state, trained models, and the cost assumptions behind every profit figure."
      />

      <div className="page">
        {loading && <Loading rows={5} />}
        {error && (
          <ErrorState
            error={error}
            what="settings"
            onRetry={() => { health.reload(); catalogue.reload(); status.reload(); }}
          />
        )}

        {health.data && (
          <Panel title="System status">
            <dl className="dl">
              <dt>API</dt>
              <dd className="text">
                <Tag tone={health.data.status === "ok" ? "retained" : "watch"}>
                  {health.data.status}
                </Tag>
              </dd>
              <dt>Database</dt>
              <dd className="text">
                <Tag tone={health.data.database === "connected" ? "retained" : "leaking"}>
                  {health.data.database}
                </Tag>
              </dd>
              <dt>Server</dt>
              <dd className="text tiny muted">{health.data.database_detail || "—"}</dd>
              <dt>Reviews analysed</dt>
              <dd className="text">
                {health.data.reviews_analysed === null ? (
                  <span className="muted">unknown</span>
                ) : (
                  <Tag tone={health.data.reviews_analysed ? "retained" : "watch"}>
                    {health.data.reviews_analysed ? "yes" : "not yet"}
                  </Tag>
                )}
              </dd>
            </dl>

            {health.data.models_missing.length > 0 && (
              <div className="disclosure" style={{ marginTop: 14 }}>
                <strong>Models missing.</strong>
                <span>
                  {health.data.models_missing.join(", ")} — run{" "}
                  <code>cd backend &amp;&amp; python scripts/train_models.py</code> to train them.
                  Endpoints that need a missing model return 503 rather than a fabricated score.
                </span>
              </div>
            )}
          </Panel>
        )}

        {status.data && (
          <Panel title="Model artifacts" note={`Loaded from ${status.data.artifact_dir}`} flush>
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>State</th>
                    <th>Artifact</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data.models.map((m) => (
                    <tr key={m.name}>
                      <td>{titleCase(m.name)}</td>
                      <td>
                        <Tag tone={m.trained ? "retained" : "watch"}>
                          {m.trained ? "trained" : "not trained"}
                        </Tag>
                      </td>
                      <td className="tiny muted">{m.path}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {costs && (
          <Panel
            title="Cost model"
            note="Set in .env on the server. These values price every expected-profit figure in the platform."
          >
            <div className="grid grid--2">
              <div>
                <div className="label" style={{ marginBottom: 7 }}>Outreach cost per contact</div>
                <dl className="dl">
                  <dt>Email</dt><dd>{money(costs.email, { precise: true })}</dd>
                  <dt>SMS</dt><dd>{money(costs.sms, { precise: true })}</dd>
                  <dt>WhatsApp</dt><dd>{money(costs.whatsapp, { precise: true })}</dd>
                  <dt>Call</dt><dd>{money(costs.call, { precise: true })}</dd>
                  <dt>Manual review</dt><dd>{money(costs.manual_review, { precise: true })}</dd>
                </dl>
              </div>
              <div>
                <div className="label" style={{ marginBottom: 7 }}>Fulfilment loss per event</div>
                <dl className="dl">
                  <dt>Gross margin</dt><dd>{(costs.gross_margin * 100).toFixed(0)}%</dd>
                  <dt>RTO logistics</dt><dd>{money(costs.rto_logistics_loss)}</dd>
                  <dt>RTO handling</dt><dd>{money(costs.rto_handling_loss)}</dd>
                  <dt>Return logistics</dt><dd>{money(costs.return_logistics_loss)}</dd>
                  <dt>Return restocking</dt><dd>{money(costs.return_restock_loss)}</dd>
                  <dt>Margin erosion</dt>
                  <dd>{(costs.return_margin_erosion * 100).toFixed(0)}%</dd>
                </dl>
              </div>
            </div>

            <p className="tiny muted" style={{ marginTop: 14 }}>
              These are read-only here. Editing economics from a browser would silently change the
              numbers behind interventions already recorded, so they live in{" "}
              <code>.env</code> and are documented in <code>docs/business-metrics.md</code>.
            </p>
          </Panel>
        )}

        {catalogue.data && (
          <Panel title="Effect assumptions">
            <div className="disclosure">
              <strong>Learned vs assumed.</strong>
              <span>{catalogue.data.assumption_disclosure}</span>
            </div>
            <div className="tablewrap" style={{ marginTop: 14 }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Protection action</th>
                    <th className="n">RTO reduction</th>
                    <th className="n">Return reduction</th>
                    <th className="n">Cost</th>
                    <th>Basis</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogue.data.protection.map((a) => (
                    <tr key={a.action}>
                      <td>{a.label}</td>
                      <td className="n">
                        {a.rto_reduction > 0 ? `${(a.rto_reduction * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td className="n">
                        {a.return_reduction > 0 ? `${(a.return_reduction * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td className="n">{money(a.fixed_cost, { precise: true })}</td>
                      <td className="tiny muted">{a.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        <Panel title="Running the pipeline">
          <p className="tiny muted" style={{ marginBottom: 10 }}>
            Order matters: reviews must be analysed before models are trained, because the return
            model joins product review signals as of each order date.
          </p>
          <ol className="tiny muted" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.9 }}>
            <li><code>python scripts/init_db.py</code> — create the database</li>
            <li><code>alembic upgrade head</code> — apply migrations</li>
            <li><code>python scripts/generate_data.py --reset</code> — generate synthetic data</li>
            <li><code>python scripts/analyze_reviews.py</code> — run the Voice of Customer pipeline</li>
            <li><code>python scripts/train_models.py</code> — train and register every model</li>
            <li><code>uvicorn app.main:app --reload</code> — start the API</li>
          </ol>
        </Panel>

        {health.data && <Disclosure text={health.data.disclosure} />}
      </div>
    </>
  );
}

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, useThemeTokens } from "../components/charts";
import {
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  Tag,
} from "../components/primitives";
import { useApi } from "../hooks/useApi";
import { num, titleCase } from "../lib/format";

function Metric({ label, value }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="num" style={{ fontSize: "1.125rem", fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function ConfusionMatrix({ cm }) {
  if (!cm) return null;
  const total = cm.tn + cm.fp + cm.fn + cm.tp;
  const cell = (v, tone) => (
    <td className="n" style={{ color: tone }}>
      {num(v)}
      <div className="tiny muted">{total ? `${((v / total) * 100).toFixed(1)}%` : "—"}</div>
    </td>
  );
  return (
    <table className="data" style={{ maxWidth: 380 }}>
      <thead>
        <tr>
          <th />
          <th className="n">Predicted no</th>
          <th className="n">Predicted yes</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th style={{ position: "static" }}>Actual no</th>
          {cell(cm.tn, "var(--retained-ink)")}
          {cell(cm.fp, "var(--leaking-ink)")}
        </tr>
        <tr>
          <th style={{ position: "static" }}>Actual yes</th>
          {cell(cm.fn, "var(--leaking-ink)")}
          {cell(cm.tp, "var(--retained-ink)")}
        </tr>
      </tbody>
    </table>
  );
}

function ModelCard({ model }) {
  const t = useThemeTokens();
  const m = model.metrics || {};
  const importance = m.permutation_importance;

  if (!model.trained) {
    return (
      <Panel title={titleCase(model.name)}>
        <Empty
          title="Not trained yet"
          body="Run: cd backend && python scripts/train_models.py"
        />
      </Panel>
    );
  }

  const isSupervised = m.roc_auc !== undefined;
  const isSentiment = m.accuracy !== undefined;

  return (
    <Panel
      title={titleCase(model.name)}
      note={model.notes}
      actions={<Tag>{model.version}</Tag>}
    >
      <div className="stack">
        <div className="row" style={{ gap: 28 }}>
          {isSupervised && (
            <>
              <Metric label="ROC-AUC" value={m.roc_auc?.toFixed(4) ?? "—"} />
              <Metric label="PR-AUC" value={m.pr_auc?.toFixed(4) ?? "—"} />
              <Metric label="Precision" value={m.precision?.toFixed(3) ?? "—"} />
              <Metric label="Recall" value={m.recall?.toFixed(3) ?? "—"} />
              <Metric label="F1" value={m.f1?.toFixed(3) ?? "—"} />
              <Metric label="Brier" value={m.brier?.toFixed(4) ?? "—"} />
            </>
          )}
          {isSentiment && (
            <>
              <Metric label="Accuracy" value={m.accuracy?.toFixed(4) ?? "—"} />
              <Metric label="Macro F1" value={m.macro_f1?.toFixed(4) ?? "—"} />
            </>
          )}
          {m.supervised === false && (
            <>
              <Metric label="Customers" value={num(m.n_customers)} />
              <Metric label="Flagged" value={num(m.flagged)} />
              <Metric label="Contamination" value={m.contamination} />
            </>
          )}
        </div>

        <div className="row tiny muted" style={{ gap: 20 }}>
          <span>{model.algorithm}</span>
          {m.train_rows && (
            <span>{num(m.train_rows)} train / {num(m.test_rows)} test rows</span>
          )}
          {m.positive_rate !== undefined && (
            <span>Base rate {(m.positive_rate * 100).toFixed(1)}%</span>
          )}
          {m.split && <span>{m.split}</span>}
        </div>

        {m.note && (
          <div className="disclosure">
            <strong>Note.</strong>
            <span>{m.note}</span>
          </div>
        )}

        {m.confusion_matrix && (
          <div>
            <div className="label" style={{ marginBottom: 7 }}>
              Confusion matrix at threshold {m.threshold}
            </div>
            <div className="tablewrap"><ConfusionMatrix cm={m.confusion_matrix} /></div>
          </div>
        )}

        {m.per_class && (
          <div>
            <div className="label" style={{ marginBottom: 7 }}>Per-class performance</div>
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Class</th><th className="n">Precision</th>
                    <th className="n">Recall</th><th className="n">F1</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(m.per_class).map(([cls, v]) => (
                    <tr key={cls}>
                      <td>{cls}</td>
                      <td className="n">{v.precision.toFixed(3)}</td>
                      <td className="n">{v.recall.toFixed(3)}</td>
                      <td className="n">{v["f1-score"].toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {importance && importance.length > 0 && (
          <div>
            <div className="label" style={{ marginBottom: 7 }}>
              Permutation importance — drop in ROC-AUC when a feature is shuffled
            </div>
            <BarsChart
              data={importance.slice(0, 10).map((f) => ({
                name: f.label, importance: Number(f.importance.toFixed(5)),
              }))}
              xKey="name" layout="vertical" yWidth={190}
              height={Math.min(importance.length, 10) * 26 + 40}
              formatter={(v) => v.toFixed(4)}
              series={[{ key: "importance", label: "Importance", color: t.structure }]}
            />
          </div>
        )}

        <details>
          <summary className="tiny muted" style={{ cursor: "pointer" }}>
            {model.feature_names?.length ?? 0} input features
          </summary>
          <div className="row" style={{ marginTop: 8, gap: 6 }}>
            {(model.feature_names || []).map((f) => <Tag key={f}>{f}</Tag>)}
          </div>
        </details>
      </div>
    </Panel>
  );
}

export default function ModelInsights() {
  const { data, error, loading, reload } = useApi(() => api.modelMetrics(), []);

  return (
    <>
      <Masthead
        eyebrow="Engine"
        title="Model insights"
        sub="Every model, how it was trained, how it scores on held-out data, and what it actually uses to decide."
      />

      <div className="page">
        {loading && <Loading rows={6} />}
        {error && <ErrorState error={error} onRetry={reload} what="model metrics" />}

        {data && (
          <>
            <Disclosure text={data.disclosure} />

            <div className="disclosure">
              <strong>How these were evaluated.</strong>
              <span>{data.evaluation_note}</span>
            </div>

            <Panel
              title="No target leakage"
              note="Rule enforced in code, not just in policy."
            >
              <p className="tiny muted">
                Every training routine calls <code>assert_no_leakage()</code> before fitting, which
                rejects any feature set containing outcome information for that model — a leaky
                feature set raises before an artifact is written. The abandonment model cannot see
                recovery outcomes; the RTO model cannot see actual transit days, delivery attempts
                or measured weight; the return model joins product review statistics as of the
                order date, so a product's later reviews can never influence an earlier prediction.
                Splits are time-based rather than random, so no model is tested on a period it
                trained on. The same rules are asserted independently in{" "}
                <code>tests/test_leakage.py</code>.
              </p>
            </Panel>

            {data.models.map((m) => <ModelCard key={m.name} model={m} />)}
          </>
        )}
      </div>
    </>
  );
}

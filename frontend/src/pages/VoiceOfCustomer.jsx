import { useRef, useState } from "react";

import { Masthead } from "../App";
import { api } from "../api/client";
import { BarsChart, DivergingAspects, DonutChart, useThemeTokens } from "../components/charts";
import {
  Disclosure,
  Empty,
  ErrorState,
  Loading,
  Panel,
  SignalChain,
  Stat,
  Tabs,
  Tag,
} from "../components/primitives";
import { useAction, useApi } from "../hooks/useApi";
import { money, num, pct, titleCase } from "../lib/format";

const TABS = [
  { id: "insights", label: "Insights" },
  { id: "analyzer", label: "Review analyzer" },
  { id: "bulk", label: "Bulk upload" },
  { id: "recommendations", label: "Seller recommendations" },
];

const SAMPLE =
  "The product quality is good but delivery took 8 days. Packaging was damaged. Please improve delivery speed.";

const SENTIMENT_TONE = {
  POSITIVE: "retained",
  NEGATIVE: "leaking",
  MIXED: "watch",
  NEUTRAL: undefined,
};

/* ---------------------------------------------------------------- Insights */
function Insights() {
  const t = useThemeTokens();
  const { data, error, loading, reload } = useApi(() => api.vocInsights(), []);

  if (loading) return <Loading rows={5} />;
  if (error) return <ErrorState error={error} onRetry={reload} what="review insights" />;
  if (!data) return null;

  if (data.analysed_reviews === 0) {
    return (
      <Empty
        title="No reviews analysed yet"
        body="Run scripts/analyze_reviews.py to process the review corpus, then reload this page."
      />
    );
  }

  const dist = data.sentiment_distribution;
  const sentimentData = Object.entries(dist).map(([name, value]) => ({
    name: titleCase(name),
    value,
    color:
      name === "POSITIVE" ? t.retained
        : name === "NEGATIVE" ? t.leaking
          : name === "MIXED" ? t.watch : t.structure,
  }));

  return (
    <div className="stack">
      <div className="grid grid--4">
        <Stat tone="neutral" label="Reviews analysed" value={num(data.analysed_reviews)}
              note={`of ${num(data.total_reviews)} stored reviews`} />
        <Stat tone="retained" label="Positive" value={num(dist.POSITIVE || 0)}
              note={pct((dist.POSITIVE || 0) / data.analysed_reviews, 1) + " of analysed"} />
        <Stat tone="leaking" label="Negative" value={num(dist.NEGATIVE || 0)}
              note={pct((dist.NEGATIVE || 0) / data.analysed_reviews, 1) + " of analysed"} />
        <Stat tone="watch" label="Mixed" value={num(dist.MIXED || 0)}
              note="Both praise and complaint in one review" />
        <Stat tone="neutral" label="Neutral" value={num(dist.NEUTRAL || 0)}
              note="No clear polarity detected" />
        <Stat tone="neutral" label="Average rating" value={data.average_rating ?? "—"}
              note="Across all stored reviews" />
      </div>

      <div className="grid grid--sidebar">
        <Panel
          title="Aspect analysis"
          note="Positive and negative share per aspect, from clause-scoped sentiment."
        >
          <DivergingAspects data={data.aspect_analysis} height={300} />
        </Panel>
        <Panel title="Sentiment distribution">
          <DonutChart data={sentimentData} height={260} />
        </Panel>
      </div>

      <div className="grid grid--sidebar">
        <Panel
          title="Top customer concerns"
          note="Every concern is wired to a downstream risk signal — this is what connects reviews to protection."
          flush
        >
          <div className="tablewrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Concern</th>
                  <th className="n">Negative mentions</th>
                  <th className="n">Share of reviews</th>
                  <th>Feeds risk signal</th>
                </tr>
              </thead>
              <tbody>
                {data.top_concerns.map((c) => (
                  <tr key={c.aspect}>
                    <td>{c.aspect_label}</td>
                    <td className="n">{num(c.negative_mentions)}</td>
                    <td className="n">{pct(c.share_of_reviews, 1)}</td>
                    <td>
                      {c.risk_signal ? (
                        <Tag tone={c.risk_signal === "RETURN_RISK" ? "leaking" : "watch"}>
                          {c.risk_signal.replace(/_/g, " ")}
                        </Tag>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="What customers ask for" note="Explicit improvement requests only.">
          {data.top_suggestions.length === 0 ? (
            <Empty title="No suggestions detected" body="No review contained an explicit request." />
          ) : (
            <BarsChart
              data={data.top_suggestions.slice(0, 8).map((s) => ({
                name: s.suggestion, count: s.count,
              }))}
              xKey="name" layout="vertical" yWidth={172} height={300}
              formatter={(v) => num(v)}
              series={[{ key: "count", label: "Reviews", color: t.series[5] }]}
            />
          )}
        </Panel>
      </div>

      <Disclosure text={data.disclosure} />
    </div>
  );
}

/* ---------------------------------------------------------------- Analyzer */
function Analyzer() {
  const [text, setText] = useState(SAMPLE);
  const [rating, setRating] = useState(2);
  const analyze = useAction(api.analyzeReview);
  const r = analyze.data;

  const negativeAspects = r?.aspects?.filter((a) => a.sentiment === "NEGATIVE") ?? [];

  return (
    <div className="grid grid--sidebar">
      <Panel title="Analyse a review" note="Results come from the backend NLP pipeline, not the browser.">
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            analyze.run({ review_text: text, rating: rating || null });
          }}
        >
          <div className="field">
            <label htmlFor="voc-text">Review text</label>
            <textarea
              id="voc-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={8000}
              required
              placeholder="Paste a customer review…"
            />
            <span className="field__hint">{text.length} / 8000 characters</span>
          </div>
          <div className="toolbar">
            <div className="field" style={{ maxWidth: 150 }}>
              <label htmlFor="voc-rating">Star rating (optional)</label>
              <select
                id="voc-rating"
                value={rating}
                onChange={(e) => setRating(Number(e.target.value))}
              >
                <option value={0}>Not supplied</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{n} star{n > 1 ? "s" : ""}</option>
                ))}
              </select>
            </div>
            <button type="submit" className="btn btn--primary" disabled={analyze.loading || !text.trim()}>
              {analyze.loading ? "Analysing…" : "Analyse review"}
            </button>
            <button type="button" className="btn" onClick={() => { setText(SAMPLE); analyze.reset(); }}>
              Reset to sample
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="Analysis">
        {analyze.loading && <Loading rows={4} />}
        {analyze.error && (
          <ErrorState error={analyze.error} what="the review" onRetry={() => analyze.run({ review_text: text, rating })} />
        )}
        {!analyze.loading && !analyze.error && !r && (
          <p className="muted tiny">
            Submit a review to see its overall sentiment, per-aspect sentiment with the exact
            phrase that drove each verdict, any explicit suggestions, and the seller action it
            implies.
          </p>
        )}
        {r && (
          <div className="stack">
            <div className="row">
              <Tag tone={SENTIMENT_TONE[r.sentiment]}>{r.sentiment}</Tag>
              <span className="tiny muted">
                polarity <strong className="num">{r.sentiment_score.toFixed(3)}</strong>
                {"  ·  "}
                confidence <strong className="num">{pct(r.confidence, 0)}</strong>
                {"  ·  "}
                language <strong>{r.language}</strong>
              </span>
              <span className="spacer" />
              <Tag tone={r.priority === "CRITICAL" || r.priority === "HIGH" ? "leaking" : r.priority === "MEDIUM" ? "watch" : "retained"}>
                {r.priority}
              </Tag>
            </div>

            <div>
              <div className="label" style={{ marginBottom: 7 }}>Aspects detected</div>
              {r.aspects.length === 0 ? (
                <p className="tiny muted">No aspect from the catalogue was mentioned.</p>
              ) : (
                <div className="tablewrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Aspect</th>
                        <th>Sentiment</th>
                        <th className="n">Score</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.aspects.map((a) => (
                        <tr key={a.aspect}>
                          <td>{titleCase(a.aspect)}</td>
                          <td><Tag tone={SENTIMENT_TONE[a.sentiment]}>{a.sentiment}</Tag></td>
                          <td className="n">{a.sentiment_score.toFixed(2)}</td>
                          <td className="tiny muted">“{a.evidence_span}”</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <div className="label" style={{ marginBottom: 7 }}>Customer suggestions</div>
              {r.suggestions.length === 0 ? (
                <p className="tiny muted">
                  No explicit request found. A complaint alone is not treated as a suggestion.
                </p>
              ) : (
                <div className="stack stack--sm">
                  {r.suggestions.map((s, i) => (
                    <div key={i}>
                      <div style={{ fontWeight: 600, fontSize: "0.8125rem" }}>
                        {s.normalized_suggestion}
                      </div>
                      <div className="quote">“{s.source_span}”</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {negativeAspects.length > 0 && (
              <div>
                <div className="label" style={{ marginBottom: 6 }}>Where this goes next</div>
                <SignalChain
                  nodes={[
                    "This review",
                    negativeAspects.map((a) => titleCase(a.aspect)).join(" + "),
                    (r.risk_signals[0] || "RISK SIGNAL").replace(/_/g, " "),
                    "Seller recommendation",
                  ]}
                />
              </div>
            )}

            <div>
              <div className="label" style={{ marginBottom: 5 }}>Business impact</div>
              <p className="tiny muted">{r.business_impact}</p>
            </div>

            <div>
              <div className="label" style={{ marginBottom: 5 }}>Recommended seller action</div>
              <p style={{ fontSize: "0.8125rem", fontWeight: 600, marginBottom: 4 }}>
                {r.recommended_action}
              </p>
              <p className="tiny muted">{r.recommended_action_detail}</p>
            </div>

            <div className="row tiny muted">
              <Tag>{r.model_version}</Tag>
              {r.model_label && (
                <span>
                  Classifier says {r.model_label} at {pct(r.model_confidence, 0)}
                </span>
              )}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------- Bulk */
function Bulk() {
  const t = useThemeTokens();
  const [file, setFile] = useState(null);
  const [persist, setPersist] = useState(false);
  const inputRef = useRef(null);
  const upload = useAction((formData, p) => api.bulkAnalyze(formData, p));
  const r = upload.data;

  function submit(e) {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    upload.run(fd, persist);
  }

  return (
    <div className="stack">
      <Panel
        title="Upload a CSV of reviews"
        note="Required column: review_text. Optional: review_id, customer_id, product_id, rating, review_date."
      >
        <form className="stack" onSubmit={submit}>
          <div className="field">
            <label htmlFor="voc-file">CSV file</label>
            <input
              id="voc-file"
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <span className="field__hint">
              Up to 12 MB and 20,000 rows. Blank rows, duplicates and bad ratings are skipped and
              reported rather than failing the upload.
            </span>
          </div>
          <label className="row" style={{ gap: 6, fontSize: "0.8125rem" }}>
            <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
            Save these reviews and their analysis to the database
          </label>
          <div className="row">
            <button type="submit" className="btn btn--primary" disabled={!file || upload.loading}>
              {upload.loading ? "Processing…" : "Analyse CSV"}
            </button>
            {file && <span className="tiny muted">{file.name}</span>}
          </div>
        </form>
      </Panel>

      {upload.loading && <Panel title="Processing"><Loading rows={3} /></Panel>}
      {upload.error && (
        <Panel title="Upload failed">
          <ErrorState error={upload.error} what="the upload" />
        </Panel>
      )}

      {r && (
        <>
          <div className="grid grid--4">
            <Stat tone="neutral" label="Rows received" value={num(r.rows_received)} />
            <Stat tone="retained" label="Analysed" value={num(r.rows_processed)} />
            <Stat tone="watch" label="Skipped" value={num(r.rows_skipped + r.duplicates_skipped)}
                  note={`${num(r.duplicates_skipped)} duplicates`} />
            <Stat tone="neutral" label="Saved" value={num(r.persisted)}
                  note={persist ? "Written to the database" : "Not saved (preview only)"} />
          </div>

          {r.errors.length > 0 && (
            <Panel title={`${r.errors.length} row issue${r.errors.length > 1 ? "s" : ""}`}>
              <ul className="tiny muted" style={{ margin: 0, paddingLeft: 18 }}>
                {r.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </Panel>
          )}

          <div className="grid grid--sidebar">
            <Panel title="Aspect analysis" note="From the uploaded reviews only.">
              {r.aspect_analysis.length === 0 ? (
                <Empty title="No aspects detected" />
              ) : (
                <DivergingAspects data={r.aspect_analysis} height={280} />
              )}
            </Panel>
            <Panel title="Sentiment distribution">
              <DonutChart
                data={Object.entries(r.sentiment_distribution).map(([name, value]) => ({
                  name: titleCase(name),
                  value,
                  color:
                    name === "POSITIVE" ? t.retained
                      : name === "NEGATIVE" ? t.leaking
                        : name === "MIXED" ? t.watch : t.structure,
                }))}
                height={240}
              />
            </Panel>
          </div>

          <div className="grid grid--2">
            <Panel title="Top issues" flush>
              <div className="tablewrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Issue</th>
                      <th className="n">Mentions</th>
                      <th className="n">Share</th>
                      <th>Feeds</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.top_issues.map((i) => (
                      <tr key={i.aspect}>
                        <td>{i.aspect_label}</td>
                        <td className="n">{num(i.negative_mentions)}</td>
                        <td className="n">{pct(i.share_of_reviews, 1)}</td>
                        <td className="tiny">{i.risk_signal?.replace(/_/g, " ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel title="Top suggestions" flush>
              <div className="tablewrap">
                <table className="data">
                  <thead>
                    <tr><th>Suggestion</th><th className="n">Count</th></tr>
                  </thead>
                  <tbody>
                    {r.top_suggestions.map((s, i) => (
                      <tr key={i}>
                        <td>{s.suggestion}</td>
                        <td className="n">{num(s.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>

          {r.seller_recommendations.length > 0 && (
            <Panel title="Seller recommendations" note="Rebuilt after saving these reviews.">
              <div className="stack">
                {r.seller_recommendations.map((rec, i) => (
                  <RecommendationCard rec={rec} key={i} />
                ))}
              </div>
            </Panel>
          )}

          <Disclosure text={r.disclosure} />
        </>
      )}
    </div>
  );
}

/* --------------------------------------------------------- Recommendations */
function RecommendationCard({ rec }) {
  return (
    <div className={`reccard reccard--${rec.priority.toLowerCase()}`}>
      <div className="reccard__head">
        <div>
          <div className="reccard__problem">{rec.problem}</div>
          <div className="tiny muted" style={{ marginTop: 3 }}>
            {rec.affected || rec.category || "All products"} · {rec.aspect_label || titleCase(rec.aspect)}
          </div>
        </div>
        <Tag
          tone={
            rec.priority === "CRITICAL" || rec.priority === "HIGH" ? "leaking"
              : rec.priority === "MEDIUM" ? "watch" : "retained"
          }
        >
          {rec.priority}
        </Tag>
      </div>

      <div className="reccard__action">{rec.recommendation}</div>

      {rec.linked_risk_signal && (
        <SignalChain
          nodes={[
            `${num(rec.supporting_review_count)} reviews`,
            rec.aspect_label || titleCase(rec.aspect),
            rec.linked_risk_signal.replace(/_/g, " "),
            "This recommendation",
          ]}
        />
      )}

      <div className="reccard__foot">
        <span>
          <strong className="num">{num(rec.supporting_review_count)}</strong> negative reviews
        </span>
        <span>
          <strong className="num">{pct(rec.negative_share, 0)}</strong> negative share
        </span>
        <span>
          Observed loss <strong className="num">{money(rec.estimated_business_impact)}</strong>
        </span>
      </div>

      {rec.impact_basis && (
        <details>
          <summary className="tiny muted" style={{ cursor: "pointer" }}>
            How this figure was calculated
          </summary>
          <p className="tiny muted" style={{ marginTop: 6 }}>{rec.impact_basis}</p>
        </details>
      )}
    </div>
  );
}

function Recommendations() {
  const { data, error, loading, reload } = useApi(() => api.recommendations({ limit: 30 }), []);
  if (loading) return <Loading rows={5} />;
  if (error) return <ErrorState error={error} onRetry={reload} what="recommendations" />;
  if (!data || data.items.length === 0) {
    return (
      <Empty
        title="No recommendations yet"
        body="Recommendations appear once reviews have been analysed. Run scripts/analyze_reviews.py."
      />
    );
  }
  return (
    <div className="stack">
      <div className="disclosure">
        <strong>Evidence only.</strong>
        <span>
          Nothing here is recommended without counted review evidence, and every rupee figure is
          loss already observed in the data — not a forecast.
        </span>
      </div>
      {data.items.map((rec) => <RecommendationCard rec={rec} key={rec.id ?? rec.problem + rec.scope} />)}
      <Disclosure text={data.disclosure} />
    </div>
  );
}

/* --------------------------------------------------------------------- Page */
export default function VoiceOfCustomer() {
  const [tab, setTab] = useState("insights");
  return (
    <>
      <Masthead
        eyebrow="Listen"
        title="Voice of Customer"
        sub="What customers actually said, what it costs, and which of it becomes a return or a delivery problem."
      />
      <div className="page">
        <Tabs tabs={TABS} active={tab} onChange={setTab} />
        {tab === "insights" && <Insights />}
        {tab === "analyzer" && <Analyzer />}
        {tab === "bulk" && <Bulk />}
        {tab === "recommendations" && <Recommendations />}
      </div>
    </>
  );
}

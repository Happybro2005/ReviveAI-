import { moneyShort, pct, riskClass, titleCase } from "../lib/format";

/* -------------------------------------------------------------------------
   Panels, tiles, states
   ------------------------------------------------------------------------- */
export function Panel({ title, note, actions, children, flush = false }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel__head">
          <div>
            {title && <div className="panel__title">{title}</div>}
            {note && <div className="panel__note">{note}</div>}
          </div>
          {actions}
        </header>
      )}
      <div className={flush ? "panel__body panel__body--flush" : "panel__body"}>
        {children}
      </div>
    </section>
  );
}

export function Stat({ label, value, note, tone = "neutral" }) {
  return (
    <div className={`stat stat--${tone}`}>
      <div className="stat__label">{label}</div>
      <div className="stat__value">{value}</div>
      {note && <div className="stat__note">{note}</div>}
    </div>
  );
}

export function Loading({ rows = 3, label = "Loading" }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 34 : 18 }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry, what = "this view" }) {
  const message = error?.message || "Something went wrong.";
  const isSetup = error?.code === "model_not_trained" || error?.status === 503;
  return (
    <div className="state state--error" role="alert">
      <div className="state__title">
        {isSetup ? `${titleCase(what)} needs setup` : `Could not load ${what}`}
      </div>
      <div className="state__body">{message}</div>
      {error?.detail && typeof error.detail === "string" && (
        <div className="state__body tiny muted">{error.detail}</div>
      )}
      {onRetry && (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title, body, action }) {
  return (
    <div className="state">
      <div className="state__title">{title}</div>
      {body && <div className="state__body">{body}</div>}
      {action}
    </div>
  );
}

export function Disclosure({ text }) {
  if (!text) return null;
  return (
    <div className="disclosure">
      <strong>Synthetic demo data.</strong>
      <span>{text}</span>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Risk marks
   ------------------------------------------------------------------------- */
export function Risk({ level, score, label }) {
  return (
    <span className={`risk risk--${riskClass(level)}`}>
      <span className="risk__level">{label || level}</span>
      {score !== undefined && score !== null && (
        <span className="risk__score">{pct(score, 0)}</span>
      )}
    </span>
  );
}

export function Tag({ children, tone }) {
  return <span className={tone ? `tag tag--${tone}` : "tag"}>{children}</span>;
}

/* -------------------------------------------------------------------------
   SIGNATURE — the ledger strip
   A proportional flow band above an aligned figure column. This is the one
   bespoke device in the system; it appears on the dashboard as revenue flow
   and in the decision center as signed profit arithmetic.
   ------------------------------------------------------------------------- */
export function LedgerStrip({ segments, formatter = moneyShort }) {
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.value || 0), 0);
  return (
    <div className="ledger">
      <div className="ledger__band" role="img" aria-label="Revenue flow breakdown">
        {segments.map((s) => {
          const share = total > 0 ? Math.max(0, s.value || 0) / total : 0;
          return (
            <div
              key={s.key}
              className="ledger__seg"
              style={{ flexGrow: Math.max(share, 0.004), background: s.color }}
              title={`${s.label}: ${formatter(s.value)} (${pct(share, 1)})`}
            />
          );
        })}
      </div>
      <div className="ledger__keys">
        {segments.map((s) => {
          const share = total > 0 ? Math.max(0, s.value || 0) / total : 0;
          return (
            <div key={s.key} className="ledger__key">
              <div className="ledger__keytop">
                <span className="ledger__swatch" style={{ background: s.color }} />
                <span className="ledger__keylabel">{s.label}</span>
              </div>
              <div className="ledger__keyvalue" style={{ color: s.textColor || "inherit" }}>
                {formatter(s.value)}
              </div>
              <div className="ledger__keyshare">
                {pct(share, 1)} of flow
                {s.sub ? ` · ${s.sub}` : ""}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Signed arithmetic ledger: terms in, costs out, net at the foot. */
export function ArithmeticLedger({ rows, total, formatter }) {
  const fmt = formatter || ((v) => moneyShort(v));
  const scale = Math.max(
    ...rows.map((r) => Math.abs(r.amount || 0)),
    Math.abs(total?.amount || 0),
    1,
  );
  const bar = (amount) => {
    const width = `${(Math.abs(amount) / scale) * 100}%`;
    const positive = amount >= 0;
    return (
      <div className="arith__bar">
        <span
          style={{
            width,
            left: 0,
            background: positive ? "var(--retained)" : "var(--leaking)",
          }}
        />
      </div>
    );
  };
  return (
    <div className="arith">
      {rows.map((r) => (
        <div className="arith__row" key={r.term}>
          <div className="arith__term">
            {r.term}
            {r.hint && <div className="tiny muted">{r.hint}</div>}
          </div>
          {bar(r.amount)}
          <div
            className={`arith__amount ${
              r.amount >= 0 ? "arith__amount--pos" : "arith__amount--neg"
            }`}
          >
            {r.amount >= 0 ? "" : "−"}
            {fmt(Math.abs(r.amount))}
          </div>
        </div>
      ))}
      {total && (
        <div className="arith__row arith__row--total">
          <div className="arith__term">{total.term}</div>
          {bar(total.amount)}
          <div
            className={`arith__amount ${
              total.amount >= 0 ? "arith__amount--pos" : "arith__amount--neg"
            }`}
          >
            {total.amount >= 0 ? "" : "−"}
            {fmt(Math.abs(total.amount))}
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Explainability
   ------------------------------------------------------------------------- */
export function Contributions({ items, emptyText = "No explanation available." }) {
  if (!items || items.length === 0) {
    return <div className="tiny muted">{emptyText}</div>;
  }
  const max = Math.max(...items.map((i) => Math.abs(i.contribution)), 0.0001);
  return (
    <div className="contrib">
      {items.map((item) => {
        const up = item.direction === "INCREASES";
        const width = `${(Math.abs(item.contribution) / max) * 50}%`;
        return (
          <div className="contrib__row" key={item.feature}>
            <div className="contrib__name">
              {item.label}
              {item.value !== null && item.value !== undefined && item.value !== "" && (
                <div className="contrib__value">{String(item.value)}</div>
              )}
            </div>
            <div className="contrib__track">
              <div
                className={`contrib__fill ${up ? "contrib__fill--up" : "contrib__fill--down"}`}
                style={{ width }}
              />
            </div>
            <div className={`contrib__pct ${up ? "contrib__pct--up" : "contrib__pct--down"}`}>
              {up ? "+" : "−"}
              {Math.round(item.percent_of_total)}%
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Reviews → risk signal → action, drawn as an explicit chain. */
export function SignalChain({ nodes }) {
  return (
    <div className="chain">
      {nodes.map((node, i) => (
        <span key={`${node}-${i}`} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className="chain__node">{node}</span>
          {i < nodes.length - 1 && <span className="chain__arrow">→</span>}
        </span>
      ))}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={active === t.id}
          className={`tabs__tab ${active === t.id ? "is-active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

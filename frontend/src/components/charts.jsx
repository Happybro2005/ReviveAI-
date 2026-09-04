/**
 * Recharts wrappers.
 *
 * All chart colour comes from the CSS token layer, read at render time, so the
 * charts follow the light/dark theme instead of carrying their own palette.
 */
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Re-read CSS variables whenever the theme attribute changes. */
export function useThemeTokens() {
  const read = () => {
    if (typeof window === "undefined") return {};
    const s = getComputedStyle(document.documentElement);
    const get = (name) => s.getPropertyValue(name).trim();
    return {
      retained: get("--retained"),
      leaking: get("--leaking"),
      watch: get("--watch"),
      structure: get("--structure"),
      ink3: get("--ink-3"),
      rule: get("--rule"),
      surface: get("--surface"),
      ink: get("--ink"),
      series: [
        get("--series-1"),
        get("--series-2"),
        get("--series-3"),
        get("--series-4"),
        get("--series-5"),
        get("--series-6"),
      ],
    };
  };
  const [tokens, setTokens] = useState(read);
  useEffect(() => {
    const update = () => setTokens(read());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    return () => {
      observer.disconnect();
      mq.removeEventListener("change", update);
    };
  }, []);
  return tokens;
}

function useTooltipStyle(t) {
  return {
    contentStyle: {
      background: t.surface,
      border: `1px solid ${t.rule}`,
      borderRadius: 3,
      fontSize: 12,
      fontFamily: "'Public Sans', system-ui, sans-serif",
      color: t.ink,
      boxShadow: "none",
    },
    labelStyle: { color: t.ink3, fontSize: 11, marginBottom: 4 },
    itemStyle: { color: t.ink },
  };
}

const axisProps = (t) => ({
  stroke: t.rule,
  tick: { fill: t.ink3, fontSize: 11, fontFamily: "'JetBrains Mono', monospace" },
  tickLine: false,
});

export function TrendChart({ data, xKey, series, height = 240, formatter }) {
  const t = useThemeTokens();
  const tip = useTooltipStyle(t);
  if (!data || data.length === 0) return null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={t.rule} strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey={xKey} {...axisProps(t)} />
        <YAxis {...axisProps(t)} width={62} tickFormatter={formatter} />
        <Tooltip {...tip} formatter={formatter ? (v) => formatter(v) : undefined} />
        <Legend
          wrapperStyle={{ fontSize: 12, color: t.ink3, paddingTop: 8 }}
          iconType="plainline"
        />
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color || t.series[i % t.series.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BarsChart({
  data,
  xKey,
  series,
  height = 240,
  formatter,
  layout = "horizontal",
  yWidth = 62,
  stacked = false,
}) {
  const t = useThemeTokens();
  const tip = useTooltipStyle(t);
  if (!data || data.length === 0) return null;
  const vertical = layout === "vertical";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout={layout}
        margin={{ top: 6, right: 14, bottom: 0, left: 4 }}
        barCategoryGap={vertical ? "22%" : "26%"}
      >
        <CartesianGrid stroke={t.rule} strokeDasharray="2 4" vertical={vertical} horizontal={!vertical} />
        {vertical ? (
          <>
            <XAxis type="number" {...axisProps(t)} tickFormatter={formatter} />
            <YAxis type="category" dataKey={xKey} {...axisProps(t)} width={yWidth} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...axisProps(t)} />
            <YAxis {...axisProps(t)} width={yWidth} tickFormatter={formatter} />
          </>
        )}
        <Tooltip {...tip} cursor={{ fill: t.rule, opacity: 0.35 }}
                 formatter={formatter ? (v) => formatter(v) : undefined} />
        {series.length > 1 && (
          <Legend wrapperStyle={{ fontSize: 12, color: t.ink3, paddingTop: 8 }} iconType="square" />
        )}
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stackId={stacked ? "a" : undefined}
            fill={s.color || t.series[i % t.series.length]}
            radius={vertical ? [0, 2, 2, 0] : [2, 2, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DonutChart({ data, height = 220, colors }) {
  const t = useThemeTokens();
  const tip = useTooltipStyle(t);
  if (!data || data.length === 0) return null;
  const palette = colors || t.series;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius="56%"
          outerRadius="82%"
          paddingAngle={1}
          stroke={t.surface}
          strokeWidth={2}
        >
          {data.map((entry, i) => (
            <Cell key={entry.name} fill={entry.color || palette[i % palette.length]} />
          ))}
        </Pie>
        <Tooltip {...tip} />
        <Legend wrapperStyle={{ fontSize: 12, color: t.ink3 }} iconType="square" />
      </PieChart>
    </ResponsiveContainer>
  );
}

/** Aspect sentiment: positive right, negative left of a shared baseline. */
export function DivergingAspects({ data, height = 280 }) {
  const t = useThemeTokens();
  const tip = useTooltipStyle(t);
  if (!data || data.length === 0) return null;
  const rows = data.map((d) => ({
    name: d.aspect_label || d.aspect,
    Positive: Math.round((d.positive_share ?? 0) * 100),
    Negative: -Math.round((d.negative_share ?? 0) * 100),
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" stackOffset="sign"
                margin={{ top: 6, right: 16, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={t.rule} strokeDasharray="2 4" horizontal={false} />
        <XAxis
          type="number"
          {...axisProps(t)}
          domain={[-100, 100]}
          tickFormatter={(v) => `${Math.abs(v)}%`}
        />
        <YAxis type="category" dataKey="name" {...axisProps(t)} width={112} />
        <Tooltip
          {...tip}
          cursor={{ fill: t.rule, opacity: 0.35 }}
          formatter={(v, n) => [`${Math.abs(v)}%`, n]}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: t.ink3, paddingTop: 8 }} iconType="square" />
        <Bar dataKey="Negative" stackId="s" fill={t.leaking} radius={[2, 0, 0, 2]} />
        <Bar dataKey="Positive" stackId="s" fill={t.retained} radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Funnel drawn as proportional rules rather than a tapered polygon. */
export function FunnelBars({ stages }) {
  const t = useThemeTokens();
  if (!stages || stages.length === 0) return null;
  const top = Math.max(...stages.map((s) => s.count), 1);
  return (
    <div className="stack stack--sm">
      {stages.map((s, i) => {
        const share = s.count / top;
        const prev = i > 0 ? stages[i - 1].count : null;
        return (
          <div key={s.stage}>
            <div className="row row--between" style={{ marginBottom: 4 }}>
              <span style={{ fontSize: "0.8125rem" }}>{s.stage}</span>
              <span className="num" style={{ fontSize: "0.8125rem", fontWeight: 600 }}>
                {s.count.toLocaleString("en-IN")}
                {prev ? (
                  <span className="muted" style={{ fontWeight: 400 }}>
                    {"  "}
                    {prev > 0 ? `${((s.count / prev) * 100).toFixed(1)}%` : "—"}
                  </span>
                ) : null}
              </span>
            </div>
            <div style={{ height: 12, background: "var(--surface-sunk)", borderRadius: 1 }}>
              <div
                style={{
                  height: "100%",
                  width: `${Math.max(share * 100, 0.5)}%`,
                  background: t.series[i % t.series.length],
                  borderRadius: 1,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

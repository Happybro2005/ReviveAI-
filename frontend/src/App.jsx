import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { api } from "./api/client";
import { useApi } from "./hooks/useApi";

import Dashboard from "./pages/Dashboard";
import Recovery from "./pages/Recovery";
import Protection from "./pages/Protection";
import Returns from "./pages/Returns";
import Rto from "./pages/Rto";
import Fraud from "./pages/Fraud";
import VoiceOfCustomer from "./pages/VoiceOfCustomer";
import DecisionCenter from "./pages/DecisionCenter";
import Customer360 from "./pages/Customer360";
import Simulator from "./pages/Simulator";
import Interventions from "./pages/Interventions";
import Analytics from "./pages/Analytics";
import ModelInsights from "./pages/ModelInsights";
import Settings from "./pages/Settings";

/* The rail is grouped by the three verbs because that is the architecture:
   RECOVER, PROTECT, LISTEN, and the engines they all share. */
const NAV = [
  {
    verb: "Recover",
    slug: "recover",
    links: [
      { to: "/recovery", label: "Recovery overview" },
      { to: "/interventions", label: "Interventions" },
    ],
  },
  {
    verb: "Protect",
    slug: "protect",
    links: [
      { to: "/protection", label: "Protection overview" },
      { to: "/returns", label: "Return risk" },
      { to: "/rto", label: "RTO risk" },
      { to: "/fraud", label: "Anomalies" },
    ],
  },
  {
    verb: "Listen",
    slug: "listen",
    links: [{ to: "/voice-of-customer", label: "Voice of Customer" }],
  },
  {
    verb: "Engine",
    slug: "engine",
    links: [
      { to: "/ai-decision-center", label: "AI Decision Center" },
      { to: "/customer-360", label: "Customer 360" },
      { to: "/revenue-simulator", label: "Revenue simulator" },
      { to: "/analytics", label: "Analytics" },
      { to: "/model-insights", label: "Model insights" },
      { to: "/settings", label: "Settings" },
    ],
  },
];

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("reviveai-theme") || "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("reviveai-theme", theme);
    } catch {
      /* storage can be unavailable; the theme still applies for this session */
    }
  }, [theme]);
  return [theme, setTheme];
}

function Rail() {
  const [theme, setTheme] = useTheme();
  const { data: health } = useApi(() => api.health(), []);
  const missing = health?.models_missing?.length ?? 0;

  return (
    <nav className="rail" aria-label="Main">
      <div className="rail__brand">
        <div className="rail__wordmark">
          Revive<em>AI</em>
        </div>
        <div className="rail__tagline">
          Recover lost revenue. Protect future revenue. Listen to customers.
        </div>
      </div>

      <div className="rail__nav">
        {NAV.map((group) => (
          <div key={group.verb} className={`rail__group rail__group--${group.slug}`}>
            <div className="rail__grouphead">
              <span className="rail__verb">{group.verb}</span>
              <span className="rail__grouprule" />
            </div>
            {group.links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `rail__link ${isActive ? "is-active" : ""}`
                }
              >
                {link.label}
                {link.to === "/model-insights" && missing > 0 && (
                  <span className="tag tag--watch">{missing}</span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </div>

      <div className="rail__foot">
        <span className="tiny muted">
          {health ? (
            health.database === "connected" ? (
              <>DB connected</>
            ) : (
              <span style={{ color: "var(--leaking-ink)" }}>DB unavailable</span>
            )
          ) : (
            "Checking…"
          )}
        </span>
        <button
          type="button"
          className="themetoggle"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </div>
    </nav>
  );
}

export function Masthead({ eyebrow, title, sub, actions }) {
  return (
    <header className="masthead">
      <div className="masthead__row">
        <div>
          {eyebrow && <div className="masthead__eyebrow">{eyebrow}</div>}
          <h1>{title}</h1>
          {sub && <div className="masthead__sub">{sub}</div>}
        </div>
        {actions}
      </div>
    </header>
  );
}

function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <div className="shell">
      <Rail />
      <main className="main">
        <ScrollReset />
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/recovery" element={<Recovery />} />
          <Route path="/interventions" element={<Interventions />} />
          <Route path="/protection" element={<Protection />} />
          <Route path="/returns" element={<Returns />} />
          <Route path="/rto" element={<Rto />} />
          <Route path="/fraud" element={<Fraud />} />
          <Route path="/voice-of-customer" element={<VoiceOfCustomer />} />
          <Route path="/ai-decision-center" element={<DecisionCenter />} />
          <Route path="/customer-360" element={<Customer360 />} />
          <Route path="/customer-360/:customerId" element={<Customer360 />} />
          <Route path="/revenue-simulator" element={<Simulator />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/model-insights" element={<ModelInsights />} />
          <Route path="/settings" element={<Settings />} />
          <Route
            path="*"
            element={
              <>
                <Masthead title="Page not found" sub="That route does not exist." />
                <div className="page">
                  <NavLink to="/dashboard" className="btn">
                    Back to dashboard
                  </NavLink>
                </div>
              </>
            }
          />
        </Routes>
      </main>
    </div>
  );
}

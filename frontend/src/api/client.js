/**
 * Thin API client.
 *
 * Every request goes through here so error shape, timeouts and the base URL are
 * handled in one place. The backend returns structured errors as
 * { error, message, detail }; ApiError carries those through to the UI so a
 * failure can say what actually went wrong instead of "something broke".
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api";
const DEFAULT_TIMEOUT = 30000;

export class ApiError extends Error {
  constructor(message, { status, code, detail } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request(path, { method = "GET", body, signal, timeout = DEFAULT_TIMEOUT, isForm } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  if (signal) signal.addEventListener("abort", () => controller.abort());

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers: isForm ? undefined : { "Content-Type": "application/json" },
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      throw new ApiError(
        `The request to ${path} timed out after ${timeout / 1000}s. The API may still be starting up.`,
        { code: "timeout" },
      );
    }
    // Report the URL actually attempted. Hard-coding a port here sends people
    // to check the wrong one whenever VITE_API_BASE is overridden.
    throw new ApiError(
      `Could not reach the API at ${BASE}. Check that the backend is running there.`,
      { code: "network", detail: `Tried: ${BASE}${path}` },
    );
  }
  clearTimeout(timer);

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { message: text };
    }
  }

  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      payload?.message ||
      (typeof detail === "string" ? detail : null) ||
      `Request failed with status ${response.status}.`;
    throw new ApiError(message, {
      status: response.status,
      code: payload?.error,
      detail,
    });
  }
  return payload;
}

export const api = {
  health: () => request("/health"),
  dashboard: (days = 180) => request(`/dashboard?days=${days}`),

  recoveryOverview: (days = 180) => request(`/recovery/overview?days=${days}`),
  recoveryPredict: (session) => request("/recovery/predict", { method: "POST", body: session }),
  recoveryDecision: (session) => request("/recovery/decision", { method: "POST", body: session }),
  recoveryCarts: (params) => request(`/recovery/carts?${new URLSearchParams(params)}`),
  createIntervention: (body) => request("/recovery/intervention", { method: "POST", body }),

  protectionOverview: (days = 180) => request(`/protection/overview?days=${days}`),
  predictReturn: (body) => request("/returns/predict", { method: "POST", body }),
  predictRto: (body) => request("/rto/predict", { method: "POST", body }),
  analyzeFraud: (body) => request("/fraud/analyze", { method: "POST", body }),
  anomalies: (params) => request(`/protection/anomalies?${new URLSearchParams(params)}`),
  protectionDecision: (body) => request("/protection/decision", { method: "POST", body }),

  analyzeReview: (body) => request("/reviews/analyze", { method: "POST", body }),
  bulkAnalyze: (formData, persist = false) =>
    request(`/reviews/bulk-analyze?persist=${persist}`, {
      method: "POST",
      body: formData,
      isForm: true,
      timeout: 180000,
    }),
  vocInsights: (params = {}) => request(`/reviews/insights?${new URLSearchParams(params)}`),
  recommendations: (params = {}) => request(`/reviews/recommendations?${new URLSearchParams(params)}`),

  customers: (params) => request(`/customers?${new URLSearchParams(params)}`),
  customer: (id) => request(`/customer/${id}`),
  customerIntelligence: (id) => request(`/customer/${id}/intelligence`),

  nextBestAction: (body) => request("/decision/next-best-action", { method: "POST", body }),
  actionCatalogue: () => request("/decision/actions"),

  simulate: (body) => request("/simulator/calculate", { method: "POST", body }),
  simulatorDefaults: () => request("/simulator/defaults"),

  modelMetrics: () => request("/models/metrics"),
  modelStatus: () => request("/models/status"),
};

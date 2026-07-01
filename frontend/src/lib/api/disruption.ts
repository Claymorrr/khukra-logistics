const API_ROOT = "/api";
const REFRESH_TIMEOUT_MS = 300_000;

function formatError(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (payload && typeof payload === "object") {
    const obj = payload as { detail?: unknown };
    if (typeof obj.detail === "string") return obj.detail;
  }
  return fallback;
}

async function apiFetch<T>(path: string, init?: RequestInit, timeoutMs = 120_000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_ROOT}${path}`, { ...init, signal: controller.signal });
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error("Request timed out. Try fewer signals or restart the API.");
    }
    throw new Error("Network request failed. Is the API running?");
  } finally {
    window.clearTimeout(timeout);
  }
  if (!res.ok) {
    const text = await res.text();
    let parsed: unknown = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* keep text */
    }
    if (res.status === 404) {
      throw new Error(
        `API endpoint not found (${path}). Restart with .\\scripts\\start-dev.ps1 to load the latest API.`,
      );
    }
    throw new Error(formatError(parsed, `Request failed: ${res.status}`));
  }
  return res.json() as Promise<T>;
}

export interface DisruptionSignal {
  signal_id: string;
  label: string;
  category: string;
  source: string;
  description: string;
}

export interface SignalStatus {
  signal_id: string;
  label: string;
  category: string;
  source: string;
  first_date?: string | null;
  last_date?: string | null;
  row_count?: number | null;
}

export interface DisruptionStatus {
  signal_count: number;
  covered_count: number;
  signals: SignalStatus[];
}

export interface Insight {
  type: string;
  interpretation: string;
  signal_id?: string;
  signal_a?: string;
  signal_b?: string;
  pearson_r?: number;
  ci_low?: number;
  ci_high?: number;
  prob_positive?: number;
  prob_strong?: number;
  prob_elevated?: number;
  credible_nonzero?: boolean;
  z_score?: number;
  regime?: string;
  best_lag_days?: number;
  correlation?: number;
}

export interface DiscoverResult {
  profile: { signals: Array<Record<string, unknown>>; total: number };
  composite_risk: {
    current: number;
    ci_low?: number;
    ci_high?: number;
    prob_elevated?: number;
    percentile_rank: number;
    interpretation: string;
    series: { dates: string[]; composite_z: number[] };
  };
  discovery: {
    insight_count: number;
    insights: Insight[];
    methodology: string;
  };
}

export interface ForecastResult {
  composite_risk: DiscoverResult["composite_risk"];
  forecast: {
    horizon_days: number;
    selected_method?: string;
    method_scores?: Record<string, { walk_forward_mae: number; direction_hit_rate: number }>;
    smooth_days?: number;
    production_series?: { dates: string[]; values: number[] };
    hybrid_mode?: string;
    channel_weights?: Record<string, number>;
    forecast_mae: number;
    forecast_rmse: number;
    credible_level?: number;
    forecast: number[];
    forecast_lower: number[];
    forecast_upper: number[];
    interpretation: string;
  };
  evaluation?: EvaluationResult | null;
}

export interface EvaluationWalkForward {
  methods: Record<
    string,
    { walk_forward_mae: number; walk_forward_rmse: number; direction_hit_rate: number }
  >;
  best_method: string;
  beats_holt: boolean;
  beats_naive: boolean;
}

export interface EvaluationResult {
  evaluated_at: string;
  evaluation_date: string;
  north_star: string;
  precision_score: number;
  verdict: "on_track" | "improving" | "needs_work";
  interpretation: string;
  walk_forward: EvaluationWalkForward;
  hybrid: {
    channels: Record<string, { signal_ids: string[]; active_count: number }>;
    hybrid_mode: string;
    total_signals: number;
  };
  channel_ablation?: Record<string, number>;
}

export interface EvaluationHistoryRow {
  evaluation_date?: string;
  precision_score?: number;
  verdict?: string;
  best_method?: string;
  walk_forward_mae?: number;
}

export interface EvaluateResponse {
  evaluation: EvaluationResult;
  saved_to?: string | null;
  history: EvaluationHistoryRow[];
}

export interface EvaluationHistoryResponse {
  latest: EvaluationResult | null;
  history: EvaluationResult[];
  days: number;
}

export type PanelScale = "raw" | "rebased" | "zscore";

export interface PanelSeriesRow {
  date: string;
  [signalId: string]: string | number | null;
}

export interface PanelProfileSignal {
  signal_id: string;
  row_count: number;
  first_date: string;
  last_date: string;
  mean: number;
  std: number;
  min: number;
  max: number;
  missing_pct: number;
}

export interface PanelDataResult {
  scale: PanelScale;
  tail_days: number | null;
  signal_ids: string[];
  date_range: { start: string; end: string };
  row_count: number;
  missing_pct: Record<string, number>;
  profile: { signals: PanelProfileSignal[]; total: number };
  series: PanelSeriesRow[];
  recent_rows: PanelSeriesRow[];
}

export function getCatalog() {
  return apiFetch<{ signals: DisruptionSignal[]; categories: string[] }>("/disruption/catalog");
}

export function getStatus() {
  return apiFetch<DisruptionStatus>("/disruption/status");
}

export function refreshSignals(body: { signal_ids?: string[]; years?: number } = {}) {
  return apiFetch("/disruption/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, REFRESH_TIMEOUT_MS);
}

export function discoverSignals(body: { signal_ids?: string[] } = {}) {
  return apiFetch<DiscoverResult>("/disruption/discover", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function forecastRisk(body: { signal_ids?: string[]; horizon_days?: number } = {}) {
  return apiFetch<ForecastResult>("/disruption/forecast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function evaluatePrecision(body: {
  signal_ids?: string[];
  horizon_days?: number;
  persist?: boolean;
} = {}) {
  return apiFetch<EvaluateResponse>("/disruption/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface ProductionModelResult {
  horizon_days: number;
  production_method: string;
  selected_method: string;
  smooth_days: number;
  hybrid_mode?: string;
  production_series: { dates: string[]; values: number[] };
  method_scores?: Record<string, { walk_forward_mae: number; direction_hit_rate: number }>;
  forecast_mae?: number;
  forecast: number[];
  forecast_lower: number[];
  forecast_upper: number[];
  interpretation: string;
}

export function getProductionModel(horizonDays = 30) {
  return apiFetch<ProductionModelResult>(
    `/disruption/production-model?horizon_days=${horizonDays}`,
    undefined,
    60_000,
  );
}

export function getEvaluationHistory(days = 30) {
  return apiFetch<EvaluationHistoryResponse>(`/disruption/evaluation?days=${days}`);
}

export function getPanelData(body: {
  signal_ids?: string[];
  tail_days?: number;
  scale?: PanelScale;
  table_rows?: number;
} = {}) {
  return apiFetch<PanelDataResult>("/disruption/panel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface CorrelationCell {
  signal_a: string;
  signal_b: string;
  value: number;
}

export interface ExploreResult {
  methods_run: string[];
  methods_expected?: number;
  signal_scope?: string;
  methodology: string;
  correlation_matrices: {
    signals: string[];
    n_obs: number;
    pearson: CorrelationCell[];
    spearman: CorrelationCell[];
    interpretation: string;
  } | null;
  mutual_information: {
    signals: string[];
    bins: number;
    cells: Array<{ signal_a: string; signal_b: string; mutual_information: number }>;
    interpretation: string;
  } | null;
  pca: {
    n_components: number;
    components: Array<{
      component: string;
      explained_variance: number;
      explained_pct: number;
      loadings: Record<string, number>;
      series: { dates: string[]; values: number[] };
    }>;
    interpretation: string;
  } | null;
  rolling_correlation: {
    window_days: number;
    pairs: Array<{
      signal_a: string;
      signal_b: string;
      static_pearson_r: number;
      window_days: number;
      series: { dates: string[]; correlation: number[] };
    }>;
    interpretation: string;
  } | null;
  changepoints: {
    composite: {
      changepoints: Array<{ date: string; index: number; composite_z: number }>;
    };
    per_signal: Array<{ signal_id: string; changepoints: Array<{ date: string; index: number }> }>;
    interpretation: string;
  } | null;
  clustering: {
    signals: string[];
    clusters: Array<{ cluster_id: number; signals: string[] }>;
    interpretation: string;
  } | null;
  bayesian_predictive: {
    max_lag: number;
    tests: Array<{
      cause: string;
      effect: string;
      posterior_prob: number;
      log_bayes_factor: number;
      interpretation: string;
    }>;
    interpretation: string;
  } | null;
}

export function exploreSignals(body: { signal_ids?: string[] } = {}) {
  return apiFetch<ExploreResult>("/disruption/explore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface NewsHeadline {
  feed_id: string;
  title: string;
  link: string;
  published_at: string;
  stress_score: number;
  impact_score?: number;
  relevance_score?: number;
  judgment_tier?: string;
  matched_keywords: string;
  judgment_rationale?: string;
  sentiment_compound?: number;
  sentiment_is_negative?: boolean;
}

export interface NewsStatus {
  signal_id: string;
  sentiment_signal_id?: string;
  objective?: string;
  feeds: Array<{ feed_id: string; label: string; url: string }>;
  headlines_total: number;
  stress_headlines: number;
  negative_headlines?: number;
  first_date: string | null;
  last_date: string | null;
  sentiment_first_date?: string | null;
  sentiment_last_date?: string | null;
  recent_headlines: NewsHeadline[];
}

export interface NewsRefreshResult {
  signal_id: string;
  sentiment_signal_id?: string;
  objective?: string;
  feeds_polled: number;
  entries_fetched: number;
  entries_new: number;
  entries_rejected?: number;
  entries_retained?: number;
  negative_headlines?: number;
  headlines_total: number;
  stress_days: number;
  sentiment_days?: number;
  latency_ms: number;
  errors: Array<{ feed_id: string; error: string }>;
  recent_headlines: NewsHeadline[];
  status: string;
}

export function refreshNews() {
  return apiFetch<NewsRefreshResult>("/disruption/refresh-news", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }, 60_000);
}

export function getNewsStatus() {
  return apiFetch<NewsStatus>("/disruption/news");
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getPanelData,
  type DiscoverResult,
  type DisruptionSignal,
  type ExploreResult,
  type ForecastResult,
  type PanelDataResult,
  type PanelScale,
} from "@/lib/api/disruption";
import { AdvancedExploration } from "@/components/AdvancedExploration";
import {
  CHART_GRID,
  CHART_TOOLTIP,
  COMPOSITE_COLOR,
  FORECAST_COLOR,
  SIGNAL_COLORS,
} from "@/lib/chartTheme";

const TAIL_OPTIONS = [
  { label: "6M", days: 126 },
  { label: "1Y", days: 252 },
  { label: "2Y", days: 504 },
  { label: "5Y", days: 1260 },
  { label: "All", days: 5000 },
];

function addDays(iso: string, n: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

interface ChartDashboardProps {
  selected: string[];
  catalogById: Record<string, DisruptionSignal>;
  coveredCount: number;
  discovery: DiscoverResult | null;
  forecast: ForecastResult | null;
  panelVersion: number;
  explore: ExploreResult | null;
  exploreLoading: boolean;
  onRequestExplore?: () => void;
}

export function ChartDashboard({
  selected,
  catalogById,
  coveredCount,
  discovery,
  forecast,
  panelVersion,
  explore,
  exploreLoading,
  onRequestExplore,
}: ChartDashboardProps) {
  const [tailDays, setTailDays] = useState(504);
  const [scale, setScale] = useState<PanelScale>("rebased");
  const [chartSignals, setChartSignals] = useState<string[]>([]);
  const [panel, setPanel] = useState<PanelDataResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"overview" | "advanced">("overview");

  const signalIds = useMemo(
    () => (selected.length ? [...selected].sort().join(",") : ""),
    [selected],
  );

  const loadPanel = useCallback(async () => {
    if (coveredCount === 0) return;
    setLoading(true);
    try {
      const result = await getPanelData({
        signal_ids: signalIds ? signalIds.split(",") : undefined,
        tail_days: tailDays,
        scale,
        table_rows: 10,
      });
      setPanel(result);
    } catch {
      /* parent shows errors */
    } finally {
      setLoading(false);
    }
  }, [coveredCount, signalIds, tailDays, scale]);

  useEffect(() => {
    void loadPanel();
  }, [loadPanel, panelVersion]);

  useEffect(() => {
    if (panel && chartSignals.length === 0) {
      setChartSignals(panel.signal_ids);
    }
  }, [panel, chartSignals.length]);

  const signalChartData = useMemo(() => {
    if (!panel) return [];
    return panel.series.map((row) => {
      const point: Record<string, string | number | null> = { date: row.date };
      for (const id of chartSignals) point[id] = row[id] ?? null;
      return point;
    });
  }, [panel, chartSignals]);

  const compositeChartData = useMemo(() => {
    const series = discovery?.composite_risk.series;
    if (!series?.dates.length) return [];
    const tail = tailDays < 5000 ? series.dates.length - Math.min(tailDays, series.dates.length) : 0;
    return series.dates.slice(tail).map((date, i) => ({
      date,
      composite: series.composite_z[tail + i],
    }));
  }, [discovery, tailDays]);

  const forecastChartData = useMemo(() => {
    const series = forecast?.forecast.production_series;
    const fallback = discovery?.composite_risk.series ?? forecast?.composite_risk.series;
    const fc = forecast?.forecast;
    if (!fc) return compositeChartData;

    const histDates = series?.dates?.length ? series.dates : fallback?.dates ?? [];
    const histZ = series?.values?.length ? series.values : fallback?.composite_z ?? [];
    if (!histDates.length) return compositeChartData;

    const tail = Math.min(252, histDates.length);
    const histSlice = histDates.slice(-tail);
    const zSlice = histZ.slice(-tail);
    const lastDate = histSlice[histSlice.length - 1];

    const hist = histSlice.map((date, i) => ({
      date,
      actual: zSlice[i],
      projected: null as number | null,
      lower: null as number | null,
      upper: null as number | null,
    }));

    const proj = fc.forecast.map((v, i) => ({
      date: addDays(lastDate, i + 1),
      actual: null as number | null,
      projected: v,
      lower: fc.forecast_lower[i] ?? null,
      upper: fc.forecast_upper[i] ?? null,
    }));

    if (hist.length) {
      const bridge = { ...hist[hist.length - 1], projected: hist[hist.length - 1].actual };
      return [...hist.slice(0, -1), bridge, ...proj];
    }
    return proj;
  }, [discovery, forecast, compositeChartData]);

  const compositeMeta = discovery?.composite_risk ?? forecast?.composite_risk;

  if (coveredCount === 0) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center rounded-2xl border border-dashed border-white/15 bg-black/20 p-12 text-center">
        <p className="text-lg font-medium text-zinc-300">No chart data yet</p>
        <p className="mt-2 max-w-md text-sm text-zinc-500">
          Refresh signals from the control panel to load charts. The dashboard will show signal
          levels, composite risk, and forecast projections.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setTab("overview")}
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            tab === "overview" ? "bg-amber-500/25 text-amber-100" : "text-zinc-500 hover:bg-white/5"
          }`}
        >
          Overview
        </button>
        <button
          type="button"
          onClick={() => {
            setTab("advanced");
            onRequestExplore?.();
          }}
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            tab === "advanced" ? "bg-violet-500/25 text-violet-100" : "text-zinc-500 hover:bg-white/5"
          }`}
        >
          Advanced exploration
          {explore?.methods_run.length === 7 ? (
            <span className="ml-2 text-[10px] opacity-70">(7 methods)</span>
          ) : explore?.methods_run.length ? (
            <span className="ml-2 text-[10px] text-amber-400/80">
              ({explore.methods_run.length}/7 methods)
            </span>
          ) : null}
        </button>
      </div>

      {tab === "advanced" ? (
        <AdvancedExploration explore={explore} catalogById={catalogById} loading={exploreLoading} />
      ) : (
        <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/30 px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {TAIL_OPTIONS.map((o) => (
            <button
              key={o.days}
              type="button"
              onClick={() => setTailDays(o.days)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                tailDays === o.days
                  ? "bg-amber-500/25 text-amber-100"
                  : "text-zinc-500 hover:bg-white/5"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          {(["rebased", "zscore", "raw"] as PanelScale[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScale(s)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize ${
                scale === s ? "bg-sky-500/20 text-sky-100" : "text-zinc-500 hover:bg-white/5"
              }`}
            >
              {s === "zscore" ? "Z-score" : s}
            </button>
          ))}
        </div>
        {loading && <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />}
      </div>

      <ChartPanel
        title="Disruption signals"
        subtitle={
          scale === "rebased"
            ? "All series rebased to 100 at window start — compare relative moves"
            : scale === "zscore"
              ? "60-day rolling z-score per signal"
              : "Raw daily levels from FRED and Yahoo"
        }
        height="h-[min(52vh,520px)]"
      >
        {signalChartData.length > 0 ? (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(panel?.signal_ids ?? []).map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() =>
                    setChartSignals((prev) =>
                      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                    )
                  }
                  className={`rounded-md border px-2 py-0.5 text-[11px] ${
                    chartSignals.includes(id) ? "text-zinc-200" : "border-white/5 text-zinc-600"
                  }`}
                  style={
                    chartSignals.includes(id)
                      ? { borderColor: SIGNAL_COLORS[id], background: `${SIGNAL_COLORS[id]}18` }
                      : undefined
                  }
                >
                  {catalogById[id]?.label ?? id}
                </button>
              ))}
            </div>
            <ResponsiveContainer width="100%" height="88%">
              <LineChart data={signalChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#555" minTickGap={48} />
                <YAxis tick={{ fontSize: 11 }} stroke="#555" width={44} />
                <Tooltip contentStyle={CHART_TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {chartSignals.map((id) => (
                  <Line
                    key={id}
                    type="monotone"
                    dataKey={id}
                    name={catalogById[id]?.label ?? id}
                    stroke={SIGNAL_COLORS[id] ?? "#888"}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </>
        ) : (
          <ChartPlaceholder label="Loading signal panel…" />
        )}
      </ChartPanel>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartPanel
          title="Composite disruption index"
          subtitle={
            compositeMeta
              ? `Current ${compositeMeta.current.toFixed(2)}σ [${(compositeMeta.ci_low ?? compositeMeta.current).toFixed(2)}, ${(compositeMeta.ci_high ?? compositeMeta.current).toFixed(2)}] · P(elevated)=${((compositeMeta.prob_elevated ?? 0) * 100).toFixed(0)}%`
              : "Run discovery to compute the Bayesian composite z-index"
          }
          height="h-[min(40vh,400px)]"
        >
          {compositeChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="92%">
              <LineChart data={compositeChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#555" minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} stroke="#555" width={36} />
                <Tooltip contentStyle={CHART_TOOLTIP} />
                <ReferenceLine y={1.5} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "+1.5σ", fill: "#ef4444", fontSize: 10 }} />
                <ReferenceLine y={-1.5} stroke="#22c55e" strokeDasharray="4 4" label={{ value: "-1.5σ", fill: "#22c55e", fontSize: 10 }} />
                <ReferenceLine y={0} stroke="#444" />
                {explore?.changepoints?.composite.changepoints.map((cp) => (
                  <ReferenceLine
                    key={cp.date}
                    x={cp.date}
                    stroke="#f472b6"
                    strokeDasharray="3 3"
                    strokeOpacity={0.6}
                  />
                ))}
                <Line
                  type="monotone"
                  dataKey="composite"
                  name="Composite z"
                  stroke={COMPOSITE_COLOR}
                  strokeWidth={2.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <ChartPlaceholder label="Run discovery to see composite risk" />
          )}
        </ChartPanel>

        <ChartPanel
          title="Production model forecast"
          subtitle={
            forecast
              ? `${forecast.forecast.horizon_days}d ${forecast.forecast.selected_method ?? "mean_reversion"} projection · ${forecast.forecast.smooth_days ?? 9}d smoothed input · MAE ${forecast.forecast.forecast_mae.toFixed(3)}`
              : "Run forecast to see production model outlook"
          }
          height="h-[min(40vh,400px)]"
        >
          {forecast && forecastChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="92%">
              <LineChart data={forecastChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#555" minTickGap={36} />
                <YAxis tick={{ fontSize: 10 }} stroke="#555" width={36} />
                <Tooltip contentStyle={CHART_TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="Historical"
                  stroke={COMPOSITE_COLOR}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="projected"
                  name="Forecast"
                  stroke={FORECAST_COLOR}
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="upper"
                  name="Upper"
                  stroke={FORECAST_COLOR}
                  strokeWidth={1}
                  strokeOpacity={0.35}
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="lower"
                  name="Lower"
                  stroke={FORECAST_COLOR}
                  strokeWidth={1}
                  strokeOpacity={0.35}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <ChartPlaceholder label="Run forecast to see projection" />
          )}
        </ChartPanel>
      </div>
        </>
      )}
    </div>
  );
}

function ChartPanel({
  title,
  subtitle,
  height,
  children,
}: {
  title: string;
  subtitle: string;
  height: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.04] to-black/40 p-4 ${height}`}>
      <div className="mb-2 shrink-0">
        <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        <p className="text-[11px] text-zinc-500">{subtitle}</p>
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}

function ChartPlaceholder({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-white/10 bg-black/20">
      <p className="text-sm text-zinc-600">{label}</p>
    </div>
  );
}

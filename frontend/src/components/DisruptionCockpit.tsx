"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronDown,
  Database,
  FlaskConical,
  Globe2,
  Loader2,
  Newspaper,
  RefreshCw,
  Search,
  TrendingUp,
} from "lucide-react";
import {
  discoverSignals,
  exploreSignals,
  forecastRisk,
  getCatalog,
  getStatus,
  refreshSignals,
  type DiscoverResult,
  type DisruptionSignal,
  type DisruptionStatus,
  type ExploreResult,
  type ForecastResult,
  type Insight,
} from "@/lib/api/disruption";
import { ChartDashboard } from "@/components/ChartDashboard";
import { EvaluationScorecard } from "@/components/EvaluationScorecard";
import { WeekAheadForecast } from "@/components/WeekAheadForecast";
import { CompositeInterpretVisual } from "@/components/CompositeInterpretVisual";
import { IndexMathVisual } from "@/components/IndexMathVisual";
import { FeatureGuide } from "@/components/FeatureGuide";
import { NewsPanel } from "@/components/NewsPanel";

export function DisruptionCockpit() {
  const [catalog, setCatalog] = useState<DisruptionSignal[]>([]);
  const [status, setStatus] = useState<DisruptionStatus | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [years, setYears] = useState(10);
  const [discovery, setDiscovery] = useState<DiscoverResult | null>(null);
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [explore, setExplore] = useState<ExploreResult | null>(null);
  const [panelVersion, setPanelVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [forecasting, setForecasting] = useState(false);
  const [exploring, setExploring] = useState(false);
  const [exploreAttempted, setExploreAttempted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showInsights, setShowInsights] = useState(true);
  const [showHelp, setShowHelp] = useState(false);
  const [evalRefreshKey, setEvalRefreshKey] = useState(0);
  const weekForecastInit = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cat, st] = await Promise.all([getCatalog(), getStatus()]);
      setCatalog(cat.signals);
      setStatus(st);
      setError(null);
      if (!selected.length) setSelected(cat.signals.map((s) => s.signal_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [selected.length]);

  useEffect(() => {
    void load();
  }, [load]);

  const discover = useCallback(async () => {
    setDiscovering(true);
    setError(null);
    try {
      const result = await discoverSignals({
        signal_ids: selected.length ? selected : undefined,
      });
      setDiscovery(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Discovery failed");
    } finally {
      setDiscovering(false);
    }
  }, [selected]);

  const runExplore = useCallback(async () => {
    setExploring(true);
    setExploreAttempted(true);
    setError(null);
    try {
      const result = await exploreSignals({});
      setExplore(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Exploration failed");
    } finally {
      setExploring(false);
    }
  }, []);

  const runForecast = useCallback(async () => {
    setForecasting(true);
    setError(null);
    try {
      const result = await forecastRisk({
        signal_ids: selected.length ? selected : undefined,
        horizon_days: 7,
      });
      setForecast(result);
      setEvalRefreshKey((k) => k + 1);
      if (!discovery) {
        setDiscovery({
          profile: { signals: [], total: 0 },
          composite_risk: result.composite_risk,
          discovery: { insight_count: 0, insights: [], methodology: "" },
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Forecast failed");
    } finally {
      setForecasting(false);
    }
  }, [discovery, selected]);

  useEffect(() => {
    if ((status?.covered_count ?? 0) > 0 && !weekForecastInit.current) {
      weekForecastInit.current = true;
      void runForecast();
    }
  }, [status?.covered_count, runForecast]);

  const refresh = useCallback(
    async (all = false) => {
      setRefreshing(true);
      setError(null);
      try {
        await refreshSignals({
          signal_ids: all ? undefined : selected.length ? selected : undefined,
          years,
        });
        await load();
        setPanelVersion((v) => v + 1);
        setEvalRefreshKey((k) => k + 1);
        await discoverSignals({
          signal_ids: all ? undefined : selected.length ? selected : undefined,
        }).then((r) => {
          setDiscovery(r);
          setExplore(null);
          setExploreAttempted(false);
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Refresh failed");
      } finally {
        setRefreshing(false);
      }
    },
    [load, selected, years],
  );

  const toggle = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  };

  const coveragePct =
    status && status.signal_count > 0
      ? Math.round((status.covered_count / status.signal_count) * 100)
      : 0;

  const catalogById = useMemo(
    () => Object.fromEntries(catalog.map((s) => [s.signal_id, s])),
    [catalog],
  );

  const compositeZ = discovery?.composite_risk.current;

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-4">
      {/* Compact top bar */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-black/40 px-5 py-4">
        <div className="flex items-center gap-4">
          <Globe2 className="h-6 w-6 text-amber-400" />
          <div>
            <h1 className="text-lg font-semibold text-white">Khukra</h1>
            <p className="text-xs text-zinc-500">Disruption risk · 7-day outlook</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-center">
          <MiniKpi label="Coverage" value={status ? `${coveragePct}%` : "—"} />
          <MiniKpi
            label="Composite z"
            value={compositeZ != null ? compositeZ.toFixed(2) : "—"}
            accent={compositeZ != null && compositeZ > 1.5}
          />
          <MiniKpi
            label="Insights"
            value={discovery ? String(discovery.discovery.insight_count) : "—"}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <ActionBtn
            icon={RefreshCw}
            label="Refresh"
            loading={refreshing}
            onClick={() => void refresh(true)}
            primary
          />
          <ActionBtn
            icon={Search}
            label="Discover"
            loading={discovering}
            onClick={() => void discover()}
          />
          <ActionBtn
            icon={FlaskConical}
            label="Explore"
            loading={exploring}
            onClick={() => void runExplore()}
          />
          <ActionBtn
            icon={BarChart3}
            label="Week forecast"
            loading={forecasting}
            onClick={() => void runForecast()}
          />
        </div>
      </header>

      <CompositeInterpretVisual refreshKey={evalRefreshKey} />

      <WeekAheadForecast refreshKey={evalRefreshKey} />

      <IndexMathVisual refreshKey={evalRefreshKey} />

      <EvaluationScorecard refreshKey={evalRefreshKey} />

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      <NewsPanel
        onRefreshed={() => {
          setPanelVersion((v) => v + 1);
          setEvalRefreshKey((k) => k + 1);
          void load();
        }}
      />

      {/* Chart-first layout */}
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <aside className="space-y-3 rounded-2xl border border-white/10 bg-white/[0.02] p-4 lg:sticky lg:top-4 lg:self-start">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
            <Database className="h-3.5 w-3.5" />
            Signals
          </p>
          <div className="space-y-1">
            {(status?.signals ?? []).map((sym) => (
              <label
                key={sym.signal_id}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-white/5"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(sym.signal_id)}
                  onChange={() => toggle(sym.signal_id)}
                  className="rounded"
                />
                <span className="flex-1 truncate text-zinc-300">
                  {catalogById[sym.signal_id]?.label ?? sym.signal_id}
                </span>
                {sym.last_date && (
                  <span className="text-[10px] text-zinc-600">✓</span>
                )}
              </label>
            ))}
          </div>
          <label className="block border-t border-white/5 pt-3 text-[11px] text-zinc-500">
            History {years}y
            <input
              type="range"
              min={1}
              max={15}
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </label>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="w-full rounded-lg border border-white/10 py-1.5 text-[11px] text-zinc-500 hover:bg-white/5"
          >
            {loading ? "Loading…" : "Reload status"}
          </button>
        </aside>

        <main>
          <ChartDashboard
            selected={selected}
            catalogById={catalogById}
            coveredCount={status?.covered_count ?? 0}
            discovery={discovery}
            forecast={forecast}
            panelVersion={panelVersion}
            explore={explore}
            exploreLoading={exploring}
            onRequestExplore={() => {
              if (!exploring && !exploreAttempted) void runExplore();
            }}
          />
        </main>
      </div>

      {/* Collapsible insights */}
      {discovery && discovery.discovery.insights.length > 0 && (
        <section className="rounded-2xl border border-white/10 bg-white/[0.02]">
          <button
            type="button"
            onClick={() => setShowInsights(!showInsights)}
            className="flex w-full items-center justify-between px-5 py-3 text-left"
          >
            <span className="text-sm font-medium text-zinc-300">
              Statistical insights ({discovery.discovery.insight_count})
            </span>
            <ChevronDown
              className={`h-4 w-4 text-zinc-500 transition ${showInsights ? "rotate-180" : ""}`}
            />
          </button>
          {showInsights && (
            <div className="grid gap-2 border-t border-white/5 px-5 pb-4 md:grid-cols-2">
              {discovery.discovery.insights.slice(0, 6).map((insight, i) => (
                <InsightCard key={`${insight.type}-${i}`} insight={insight} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Collapsible documentation */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.02]">
        <button
          type="button"
          onClick={() => setShowHelp(!showHelp)}
          className="flex w-full items-center justify-between px-5 py-3 text-left"
        >
          <span className="text-sm text-zinc-500">Feature reference &amp; glossary</span>
          <ChevronDown
            className={`h-4 w-4 text-zinc-600 transition ${showHelp ? "rotate-180" : ""}`}
          />
        </button>
        {showHelp && (
          <div className="border-t border-white/5 p-5">
            <FeatureGuide
              catalog={catalog}
              status={status}
              hasDiscovery={discovery != null}
              coveragePct={coveragePct}
            />
          </div>
        )}
      </section>
    </div>
  );
}

function MiniKpi({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-zinc-600">{label}</p>
      <p className={`text-xl font-semibold ${accent ? "text-amber-400" : "text-white"}`}>
        {value}
      </p>
    </div>
  );
}

function ActionBtn({
  icon: Icon,
  label,
  loading,
  onClick,
  primary,
}: {
  icon: typeof RefreshCw;
  label: string;
  loading: boolean;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${
        primary
          ? "bg-amber-500/25 text-amber-100 hover:bg-amber-500/35"
          : "border border-white/10 text-zinc-300 hover:bg-white/5"
      }`}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
      {label}
    </button>
  );
}

function InsightCard({ insight }: { insight: Insight }) {
  const isNews = insight.type.startsWith("news_");
  const icon = isNews ? (
    <Newspaper className="h-3.5 w-3.5 text-cyan-400" />
  ) : insight.type === "regime_shift" ? (
    <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
  ) : insight.type === "lead_lag" ? (
    <TrendingUp className="h-3.5 w-3.5 text-violet-400" />
  ) : (
    <Activity className="h-3.5 w-3.5 text-sky-400" />
  );

  return (
    <div className="rounded-xl border border-white/10 bg-black/25 px-3 py-2.5 text-xs">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-600">
        {icon}
        {insight.type.replaceAll("_", " ")}
      </div>
      <p className="mt-1.5 leading-5 text-zinc-400">{insight.interpretation}</p>
    </div>
  );
}

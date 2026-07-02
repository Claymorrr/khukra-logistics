"use client";

import { useCallback, useEffect, useState } from "react";
import { Gauge, Loader2, Sparkles, TrendingDown } from "lucide-react";
import {
  applyForecastOptimization,
  getForecastOptimization,
  type ForecastOptimization,
} from "@/lib/api/disruption";

export function MaeOptimizerPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [data, setData] = useState<ForecastOptimization | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getForecastOptimization());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load MAE optimization");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const apply = async () => {
    setApplying(true);
    setMessage(null);
    setError(null);
    try {
      const res = await applyForecastOptimization();
      setMessage(res.message);
      setData((prev) =>
        prev
          ? { ...prev, active_config: res.active_config, recommended: res.optimization.recommended }
          : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply optimization");
    } finally {
      setApplying(false);
    }
  };

  const baseline = data?.baseline.walk_forward_mae;
  const tuned = data?.recommended.walk_forward_mae;
  const active = data?.active_config?.walk_forward_mae ?? baseline;

  return (
    <section className="rounded-2xl border border-violet-500/25 bg-gradient-to-br from-violet-950/20 via-black/50 to-black/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-violet-300">
            <Gauge className="h-4 w-4" />
            MAE optimizer
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            Walk-forward grid search over smooth days, method, and mean-reversion params
          </p>
        </div>
        {loading && <Loader2 className="h-5 w-5 animate-spin text-violet-400/60" />}
      </div>

      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      {message && <p className="mt-3 text-sm text-emerald-300">{message}</p>}

      {data && !loading && (
        <div className="mt-5 space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Default MAE</p>
              <p className="mt-1 font-mono text-2xl text-zinc-300">{baseline?.toFixed(3)}σ</p>
              <p className="mt-1 text-[10px] text-zinc-600">
                smooth {data.baseline.smooth_days}d · {data.baseline.production_method}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/20 px-4 py-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-emerald-400/80">Tuned MAE</p>
              <p className="mt-1 font-mono text-2xl text-emerald-300">{tuned?.toFixed(3)}σ</p>
              <p className="mt-1 text-[10px] text-emerald-600/80">
                {data.improvement_abs > 0 ? (
                  <span className="inline-flex items-center gap-1">
                    <TrendingDown className="h-3 w-3" />
                    −{data.improvement_abs.toFixed(3)}σ ({data.improvement_pct}%)
                  </span>
                ) : (
                  "Already optimal"
                )}
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Active / target</p>
              <p className="mt-1 font-mono text-2xl text-white">{active?.toFixed(3)}σ</p>
              <p className="mt-1 text-[10px] text-zinc-600">target ≤ {data.mae_target}σ</p>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-zinc-300">
            <p className="font-medium text-violet-200/90">Recommended settings</p>
            <ul className="mt-2 space-y-1 font-mono text-xs text-zinc-400">
              <li>smooth_days = {data.recommended.smooth_days}</li>
              <li>method = {data.recommended.production_method}</li>
              {data.recommended.production_method === "mean_reversion" && (
                <li>
                  mean_reversion window={data.recommended.mean_reversion.window}, speed=
                  {data.recommended.mean_reversion.speed}
                </li>
              )}
              <li>direction hit rate = {(data.recommended.direction_hit_rate * 100).toFixed(0)}%</li>
            </ul>
          </div>

          <p className="text-sm leading-relaxed text-zinc-400">{data.interpretation}</p>

          <button
            type="button"
            onClick={() => void apply()}
            disabled={applying || !data.beats_baseline}
            className="inline-flex items-center gap-2 rounded-xl bg-violet-500/25 px-4 py-2 text-sm font-medium text-violet-100 hover:bg-violet-500/35 disabled:opacity-50"
          >
            {applying ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Apply tuned settings to production
          </button>
        </div>
      )}
    </section>
  );
}

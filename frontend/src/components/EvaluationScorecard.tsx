"use client";

import { useCallback, useEffect, useState } from "react";
import { Gauge, TrendingDown, TrendingUp } from "lucide-react";
import {
  evaluatePrecision,
  getEvaluationHistory,
  type EvaluationResult,
  type EvaluationHistoryRow,
} from "@/lib/api/disruption";

const VERDICT_LABEL: Record<string, string> = {
  on_track: "On track",
  improving: "Improving",
  needs_work: "Needs work",
};

const VERDICT_COLOR: Record<string, string> = {
  on_track: "text-emerald-400",
  improving: "text-amber-400",
  needs_work: "text-red-400",
};

export function EvaluationScorecard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [latest, setLatest] = useState<EvaluationResult | null>(null);
  const [history, setHistory] = useState<EvaluationHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getEvaluationHistory(14);
      if (data.latest) {
        setLatest(data.latest);
        setHistory(
          data.history.map((row) => ({
            evaluation_date: row.evaluation_date,
            precision_score: row.precision_score,
            verdict: row.verdict,
            best_method: row.walk_forward?.best_method,
            walk_forward_mae: row.walk_forward?.methods?.[row.walk_forward?.best_method ?? "bayesian_linear"]
              ?.walk_forward_mae,
          })),
        );
      } else {
        const run = await evaluatePrecision({});
        setLatest(run.evaluation);
        setHistory(run.history ?? []);
      }
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load evaluation";
      if (msg.includes("not found") || msg.includes("404")) {
        setError("Evaluation API not loaded — restart with .\\scripts\\start-dev.ps1");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const runEvaluate = async () => {
    setLoading(true);
    try {
      const data = await evaluatePrecision({});
      setLatest(data.evaluation);
      setHistory(data.history ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setLoading(false);
    }
  };

  const score = latest?.precision_score;
  const verdict = latest?.verdict ?? "needs_work";
  const mae = latest?.walk_forward?.methods?.[latest.walk_forward.best_method]?.walk_forward_mae;
  const prev = history.length > 1 ? history[1]?.precision_score : null;
  const delta = score != null && prev != null ? score - prev : null;

  return (
    <section className="rounded-2xl border border-violet-500/20 bg-violet-950/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-violet-400">
            <Gauge className="h-3.5 w-3.5" />
            Forecast precision (daily)
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            Hybrid panel scorecard — macro + market + news. Discover and explore serve this metric.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void runEvaluate()}
          disabled={loading}
          className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-200 hover:bg-violet-500/20 disabled:opacity-50"
        >
          {loading ? "Measuring…" : "Run today's measure"}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}

      {!error && latest && (
        <div className="mt-4 grid gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Precision score</p>
            <p className="mt-1 text-2xl font-semibold text-zinc-100">
              {score ?? "—"}
              <span className="text-sm font-normal text-zinc-500">/100</span>
            </p>
            {delta != null && (
              <p className={`mt-1 flex items-center gap-1 text-xs ${delta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {delta >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                {delta >= 0 ? "+" : ""}
                {delta} vs prior day
              </p>
            )}
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Verdict</p>
            <p className={`mt-1 text-lg font-medium ${VERDICT_COLOR[verdict] ?? "text-zinc-300"}`}>
              {VERDICT_LABEL[verdict] ?? verdict}
            </p>
            <p className="mt-1 text-xs text-zinc-500">{latest.evaluation_date}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">1-step MAE</p>
            <p className="mt-1 text-lg font-medium text-zinc-200">
              {mae != null ? mae.toFixed(3) : "—"}
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              Best: {latest.walk_forward.best_method}
              {latest.walk_forward.beats_holt ? " · beats Holt" : ""}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Hybrid channels</p>
            <p className="mt-1 text-xs text-zinc-300">
              macro {latest.hybrid.channels.macro.active_count} · market{" "}
              {latest.hybrid.channels.market.active_count} · news{" "}
              {latest.hybrid.channels.news.active_count}
            </p>
          </div>
        </div>
      )}

      {!error && !latest && !loading && (
        <p className="mt-3 text-sm text-zinc-500">
          No daily measurement yet. Refresh data, then run today's measure.
        </p>
      )}

      {latest?.interpretation && (
        <p className="mt-3 text-sm leading-relaxed text-zinc-400">{latest.interpretation}</p>
      )}
    </section>
  );
}

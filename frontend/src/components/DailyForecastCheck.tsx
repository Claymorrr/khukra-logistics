"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Loader2,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { getForecastCheck, type ForecastCheck } from "@/lib/api/disruption";

const VERDICT_STYLES: Record<
  string,
  { ring: string; badge: string; label: string; Icon: typeof CheckCircle2 }
> = {
  hit: {
    ring: "border-emerald-500/35",
    badge: "bg-emerald-500/15 text-emerald-300",
    label: "Hit",
    Icon: CheckCircle2,
  },
  close: {
    ring: "border-amber-500/35",
    badge: "bg-amber-500/15 text-amber-300",
    label: "Close",
    Icon: Target,
  },
  miss: {
    ring: "border-red-500/35",
    badge: "bg-red-500/15 text-red-300",
    label: "Miss",
    Icon: XCircle,
  },
};

function fmt(n: number, d = 2): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(d)}σ`;
}

function StepCard({
  label,
  date,
  value,
  sub,
  accent,
}: {
  label: string;
  date: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-[11px] text-zinc-600">{date}</p>
      <p className={`mt-2 font-mono text-2xl font-semibold ${accent ?? "text-white"}`}>{value}</p>
      {sub && <p className="mt-1 text-[11px] text-zinc-500">{sub}</p>}
    </div>
  );
}

export function DailyForecastCheck({ refreshKey = 0 }: { refreshKey?: number }) {
  const [data, setData] = useState<ForecastCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getForecastCheck());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load forecast check");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const style = VERDICT_STYLES[data?.verdict ?? "close"] ?? VERDICT_STYLES.close;
  const VerdictIcon = style.Icon;

  return (
    <section
      id="forecast-check"
      className={`rounded-2xl border bg-gradient-to-br from-violet-950/25 via-black/50 to-black/60 p-5 ${style.ring}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-violet-300">
            Yesterday&apos;s forecast check
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            Did the 1-day production forecast land on today&apos;s composite?
          </p>
        </div>
        {loading && <Loader2 className="h-5 w-5 animate-spin text-violet-400/60" />}
        {data && !loading && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${style.badge}`}>
            <VerdictIcon className="h-3.5 w-3.5" />
            {style.label}
          </span>
        )}
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-300">
          {error}
          {error.includes("not found") || error.includes("404") ? (
            <span className="block text-xs text-red-200/70">
              Restart with <code className="rounded bg-black/40 px-1">.\scripts\setup.ps1 -Dev</code>
            </span>
          ) : null}
        </p>
      )}

      {data && !error && (
        <div className="mt-5 space-y-4">
          <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr] md:items-center">
            <StepCard
              label="Yesterday"
              date={data.yesterday_date}
              value={fmt(data.yesterday_smoothed)}
              sub="smoothed composite"
            />
            <ArrowRight className="mx-auto hidden h-5 w-5 text-zinc-600 md:block" />
            <StepCard
              label="Forecast for today"
              date={data.today_date}
              value={fmt(data.predicted_today)}
              sub={data.forecast_method}
              accent="text-sky-300"
            />
            <ArrowRight className="mx-auto hidden h-5 w-5 text-zinc-600 md:block" />
            <StepCard
              label="Actual today"
              date={data.today_date}
              value={fmt(data.actual_today_smoothed)}
              sub={`raw ${fmt(data.actual_today_raw)}`}
              accent="text-amber-200"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Error</p>
              <p className="mt-1 font-mono text-xl text-white">{data.error_abs.toFixed(2)}σ</p>
              <p className="mt-1 text-[11px] text-zinc-500">target ≤ {data.mae_target}σ</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Direction</p>
              <p className="mt-1 flex items-center justify-center gap-1 text-sm">
                {data.direction_correct ? (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    <span className="text-emerald-300">Correct</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-4 w-4 text-red-400" />
                    <span className="text-red-300">Missed</span>
                  </>
                )}
              </p>
              <p className="mt-1 text-[11px] text-zinc-500">
                actual {fmt(data.actual_change)} · pred {fmt(data.predicted_change)}
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Move</p>
              <p className="mt-1 flex items-center justify-center gap-1">
                {data.actual_change >= 0 ? (
                  <TrendingUp className="h-4 w-4 text-amber-400" />
                ) : (
                  <TrendingDown className="h-4 w-4 text-emerald-400" />
                )}
                <span className="font-mono text-sm text-zinc-200">{fmt(data.actual_change)}</span>
              </p>
              <p className="mt-1 text-[11px] text-zinc-500">vs yesterday</p>
            </div>
          </div>

          <p className="text-sm leading-relaxed text-zinc-300">{data.interpretation}</p>
        </div>
      )}
    </section>
  );
}

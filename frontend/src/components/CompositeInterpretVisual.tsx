"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Gauge,
  Loader2,
  Minus,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getIndexDecomposition, type IndexDecomposition } from "@/lib/api/disruption";
import { CHART_GRID, CHART_TOOLTIP, COMPOSITE_COLOR } from "@/lib/chartTheme";

const CHANNEL_COLORS: Record<string, string> = {
  macro: "#a78bfa",
  market: "#38bdf8",
  news: "#22d3ee",
};

const REGIME_STYLES: Record<
  string,
  { badge: string; glow: string; icon: typeof TrendingUp }
> = {
  calm: {
    badge: "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40",
    glow: "from-emerald-500/20",
    icon: TrendingDown,
  },
  neutral: {
    badge: "bg-zinc-500/20 text-zinc-300 ring-zinc-500/40",
    glow: "from-zinc-500/10",
    icon: Minus,
  },
  watch: {
    badge: "bg-amber-500/20 text-amber-300 ring-amber-500/40",
    glow: "from-amber-500/20",
    icon: TrendingUp,
  },
  elevated: {
    badge: "bg-red-500/20 text-red-300 ring-red-500/40",
    glow: "from-red-500/25",
    icon: TrendingUp,
  },
};

function fmt(n: number | null | undefined, d = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(d);
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/** Map z-score to 0–100 position on a −2.5…+2.5 stress axis */
function zToPct(z: number): number {
  return clamp(((z + 2.5) / 5) * 100, 0, 100);
}

function StressSpectrum({
  z,
  smoothed,
  p10,
  p90,
  bands,
}: {
  z: number;
  smoothed: number;
  p10: number;
  p90: number;
  bands: IndexDecomposition["interpretation"]["bands"];
}) {
  return (
    <div className="relative mt-2">
      <div className="relative h-3 overflow-hidden rounded-full bg-gradient-to-r from-emerald-600/50 via-zinc-600/40 via-45% to-red-600/60">
        {bands.map((b) => (
          <div
            key={b.id}
            className="pointer-events-none absolute inset-y-0 opacity-20"
            style={{
              left: `${zToPct(b.from)}%`,
              width: `${zToPct(b.to) - zToPct(b.from)}%`,
            }}
          />
        ))}
      </div>
      <div
        className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.8)]"
        style={{ left: `${zToPct(z)}%` }}
        title={`Today C_t = ${fmt(z)}σ`}
      />
      <div
        className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-emerald-300 bg-emerald-950"
        style={{ left: `${zToPct(smoothed)}%` }}
        title={`Smoothed C̃_t = ${fmt(smoothed)}σ`}
      />
      <div
        className="absolute top-4 h-2 w-px bg-zinc-600"
        style={{ left: `${zToPct(p10)}%` }}
        title={`p10 = ${fmt(p10)}σ`}
      />
      <div
        className="absolute top-4 h-2 w-px bg-zinc-600"
        style={{ left: `${zToPct(p90)}%` }}
        title={`p90 = ${fmt(p90)}σ`}
      />
      <div className="mt-3 flex justify-between text-[10px] text-zinc-500">
        <span>Calm −2σ</span>
        <span>0 = recent avg</span>
        <span>Elevated +2σ</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-zinc-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-1 rounded-full bg-amber-300" /> today
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full border border-emerald-300" /> smoothed
        </span>
        <span>p10 {fmt(p10)} · p90 {fmt(p90)}</span>
      </div>
    </div>
  );
}

function PercentileBar({ percentile }: { percentile: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">Historical rank</p>
        <p className="font-mono text-sm text-zinc-200">{fmt(percentile, 0)}th percentile</p>
      </div>
      <div className="relative mt-2 h-2 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-sky-600 to-violet-500"
          style={{ width: `${clamp(percentile, 0, 100)}%` }}
        />
        <div
          className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-white shadow"
          style={{ left: `${clamp(percentile, 0, 100)}%` }}
        />
      </div>
      <p className="mt-1 text-[10px] text-zinc-600">
        Worse than {fmt(percentile, 0)}% of days in the cached history
      </p>
    </div>
  );
}

export function CompositeInterpretVisual({ refreshKey = 0 }: { refreshKey?: number }) {
  const [data, setData] = useState<IndexDecomposition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getIndexDecomposition());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load index interpretation");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const interp = data?.interpretation;
  const missingInterpretation = data != null && !interp;
  const regimeStyle = REGIME_STYLES[interp?.regime ?? "neutral"] ?? REGIME_STYLES.neutral;
  const RegimeIcon = regimeStyle.icon;

  const sparkData = useMemo(() => {
    if (!interp?.series_recent) return [];
    return interp.series_recent.dates.map((d, i) => ({
      date: d,
      raw: interp.series_recent.composite_z[i],
      smooth: interp.series_recent.composite_smoothed[i],
    }));
  }, [interp]);

  const channelStack = useMemo(() => {
    if (!interp?.channel_rank) return [];
    return interp.channel_rank.map((c) => ({
      ...c,
      fill: CHANNEL_COLORS[c.channel] ?? "#888",
      abs: Math.abs(c.contribution),
    }));
  }, [interp]);

  const maxChannelAbs = useMemo(
    () => Math.max(...channelStack.map((c) => c.abs), 0.01),
    [channelStack],
  );

  return (
    <section
      id="composite-interpret"
      className={`rounded-2xl border border-amber-500/30 bg-gradient-to-br ${regimeStyle.glow} via-black/50 to-black/60 p-5 ring-1 ring-amber-500/20`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-amber-200/90">
            <Gauge className="h-4 w-4" />
            What the composite means
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            Stress index in σ vs recent history · {data?.date ?? "…"}
          </p>
        </div>
        {loading && <Loader2 className="h-5 w-5 animate-spin text-amber-400/60" />}
      </div>

      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}

      {missingInterpretation && !error && (
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-3 text-sm text-amber-100">
          <p className="font-medium">Interpretation panel needs a newer API build.</p>
          <p className="mt-1 text-amber-200/80">
            From the project root run{" "}
            <code className="rounded bg-black/40 px-1.5 py-0.5 text-xs">.\scripts\setup.ps1 -Dev</code>{" "}
            (reinstalls the package and restarts API + UI on port 3020).
          </p>
          <p className="mt-2 font-mono text-xs text-zinc-400">
            Today&apos;s composite: {fmt(data.composite_raw)}σ (raw) · {fmt(data.composite_smoothed)}σ
            (smoothed)
          </p>
        </div>
      )}

      {data && interp && !error && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
          {/* Left: headline + gauge + narrative */}
          <div className="space-y-5">
            <div className="flex flex-wrap items-start gap-4">
              <div>
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ring-1 ${regimeStyle.badge}`}
                >
                  <RegimeIcon className="h-3.5 w-3.5" />
                  {interp.regime_label}
                </span>
                <p className="mt-3 font-mono text-4xl font-semibold tracking-tight text-white">
                  {fmt(data.composite_raw)}
                  <span className="ml-1 text-lg text-zinc-500">σ</span>
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  Smoothed forecast level{" "}
                  <span className="font-mono text-emerald-300/90">{fmt(data.composite_smoothed)}σ</span>
                  {" · "}
                  {interp.smoothed_regime_label}
                </p>
              </div>
              <div className="min-w-[200px] flex-1 rounded-xl border border-white/10 bg-black/30 px-4 py-3">
                <PercentileBar percentile={interp.percentile_rank} />
                <p className="mt-3 text-[10px] text-zinc-500">
                  P(elevated &gt;1.5σ) ={" "}
                  <span className="font-mono text-zinc-300">
                    {(interp.prob_elevated * 100).toFixed(0)}%
                  </span>
                  {" · "}
                  95% CI [{fmt(interp.ci_low)}, {fmt(interp.ci_high)}]
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-black/35 px-4 py-4">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Stress spectrum</p>
              <StressSpectrum
                z={data.composite_raw}
                smoothed={data.composite_smoothed}
                p10={interp.p10}
                p90={interp.p90}
                bands={interp.bands}
              />
            </div>

            <p className="text-sm leading-relaxed text-zinc-300">{interp.headline}</p>
            <p className="text-xs leading-relaxed text-zinc-500">{interp.regime_detail}</p>
          </div>

          {/* Right: drivers + channels + sparkline */}
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-black/30 p-4">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Channel push / pull</p>
              <div className="mt-3 space-y-2">
                {channelStack.map((ch) => (
                  <div key={ch.channel} className="flex items-center gap-2">
                    <span
                      className="w-14 text-xs capitalize"
                      style={{ color: ch.fill }}
                    >
                      {ch.channel}
                    </span>
                    <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="absolute top-0 h-full rounded-full opacity-80"
                        style={{
                          backgroundColor: ch.fill,
                          width: `${(ch.abs / maxChannelAbs) * 100}%`,
                          left: ch.contribution >= 0 ? "50%" : `${50 - (ch.abs / maxChannelAbs) * 50}%`,
                        }}
                      />
                      <div className="absolute left-1/2 top-0 h-full w-px bg-white/20" />
                    </div>
                    <span className="w-12 text-right font-mono text-[11px] text-zinc-400">
                      {ch.contribution >= 0 ? "+" : ""}
                      {fmt(ch.contribution)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-black/30 p-4">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Top signal drivers</p>
              <ul className="mt-3 space-y-2">
                {interp.top_drivers.map((d) => (
                  <li
                    key={d.signal_id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs text-zinc-200">{d.label}</p>
                      <p className="text-[10px] capitalize text-zinc-600">{d.channel}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {d.direction === "up" ? (
                        <ArrowUp className="h-3.5 w-3.5 text-red-400" />
                      ) : (
                        <ArrowDown className="h-3.5 w-3.5 text-emerald-400" />
                      )}
                      <span className="font-mono text-xs text-amber-200/90">
                        {d.impact >= 0 ? "+" : ""}
                        {fmt(d.impact)}
                        σ
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-xl border border-white/10 bg-black/30 p-3">
              <p className="mb-2 text-[10px] uppercase tracking-wider text-zinc-500">Recent trajectory</p>
              <div className="h-[140px]">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={sparkData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                    <XAxis dataKey="date" hide />
                    <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9 }} stroke="#555" width={28} />
                    <Tooltip
                      contentStyle={CHART_TOOLTIP}
                      labelFormatter={(d) => String(d)}
                      formatter={(v: number, name: string) => [
                        `${v.toFixed(2)}σ`,
                        name === "smooth" ? "smoothed" : "raw",
                      ]}
                    />
                    <ReferenceArea y1={1.5} y2={3} fill="#ef4444" fillOpacity={0.06} />
                    <ReferenceArea y1={-3} y2={-0.5} fill="#22c55e" fillOpacity={0.06} />
                    <ReferenceLine y={0} stroke="#666" strokeDasharray="4 4" />
                    <ReferenceLine y={1.5} stroke="#ef4444" strokeDasharray="2 4" strokeOpacity={0.5} />
                    <Area
                      type="monotone"
                      dataKey="raw"
                      stroke={COMPOSITE_COLOR}
                      fill={COMPOSITE_COLOR}
                      fillOpacity={0.12}
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="smooth"
                      stroke="#34d399"
                      strokeWidth={2}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

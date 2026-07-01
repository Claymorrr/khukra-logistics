"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { LineChart, Loader2 } from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getEvaluationHistory,
  getProductionModel,
  type EvaluationResult,
  type ProductionModelResult,
} from "@/lib/api/disruption";
import {
  CHART_GRID,
  CHART_TOOLTIP,
  FORECAST_COLOR,
  PRODUCTION_COLOR,
} from "@/lib/chartTheme";

const METHOD_LABEL: Record<string, string> = {
  mean_reversion: "Mean reversion",
  holt: "Holt linear",
  bayesian_linear: "Bayesian linear",
};

function addDays(iso: string, n: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function ProductionModelChart({ refreshKey = 0 }: { refreshKey?: number }) {
  const [model, setModel] = useState<ProductionModelResult | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const history = await getEvaluationHistory(1);
      setEvaluation(history.latest);
      const prod = await getProductionModel(30);
      setModel(prod);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load production model";
      if (msg.includes("not found") || msg.includes("404")) {
        setError("Production model API not loaded — restart with .\\scripts\\start-dev.ps1");
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

  const productionMethod =
    model?.production_method ?? evaluation?.walk_forward?.best_method ?? "mean_reversion";

  const chartData = useMemo(() => {
    if (!model?.production_series?.dates?.length) return [];

    const { dates: histDates, values: histValues } = model.production_series;
    const tail = Math.min(252, histDates.length);
    const dates = histDates.slice(-tail);
    const values = histValues.slice(-tail);
    const lastDate = dates[dates.length - 1];

    const hist = dates.map((date, i) => ({
      date,
      production: values[i],
      projected: null as number | null,
      lower: null as number | null,
      upper: null as number | null,
    }));

    const proj = model.forecast.map((v, i) => ({
      date: addDays(lastDate, i + 1),
      production: null as number | null,
      projected: v,
      lower: model.forecast_lower[i] ?? null,
      upper: model.forecast_upper[i] ?? null,
    }));

    if (hist.length) {
      const bridge = { ...hist[hist.length - 1], projected: hist[hist.length - 1].production };
      return [...hist.slice(0, -1), bridge, ...proj];
    }
    return proj;
  }, [model]);

  const methodRows = useMemo(() => {
    const methods = evaluation?.walk_forward?.methods ?? model?.method_scores ?? {};
    return Object.entries(methods)
      .filter(([name]) => name !== "naive")
      .map(([name, stats]) => ({
        name,
        label: METHOD_LABEL[name] ?? name,
        mae: stats.walk_forward_mae,
        isProduction: name === productionMethod,
      }))
      .sort((a, b) => a.mae - b.mae);
  }, [evaluation, model, productionMethod]);

  const maxMae = methodRows.length ? Math.max(...methodRows.map((r) => r.mae)) : 1;
  const smoothDays = model?.smooth_days ?? 9;
  const productionMae =
    evaluation?.walk_forward?.methods?.[productionMethod]?.walk_forward_mae ?? model?.forecast_mae;

  return (
    <section className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-950/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-emerald-400">
            <LineChart className="h-3.5 w-3.5" />
            Production forecast model
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            {METHOD_LABEL[productionMethod] ?? productionMethod} on {smoothDays}-day smoothed hybrid
            composite — the model behind the daily precision score.
          </p>
        </div>
        {loading && <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />}
      </div>

      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}

      {!error && chartData.length > 0 && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_220px]">
          <div className="h-[min(36vh,320px)] rounded-xl border border-white/10 bg-black/25 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#555" minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} stroke="#555" width={36} />
                <Tooltip contentStyle={CHART_TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#444" />
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill={FORECAST_COLOR}
                  fillOpacity={0.12}
                  connectNulls
                  legendType="none"
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="#0c0f14"
                  fillOpacity={1}
                  connectNulls
                  legendType="none"
                />
                <Line
                  type="monotone"
                  dataKey="production"
                  name={`Production input (${smoothDays}d smooth)`}
                  stroke={PRODUCTION_COLOR}
                  strokeWidth={2.5}
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="projected"
                  name={`${METHOD_LABEL[productionMethod] ?? productionMethod} forecast`}
                  stroke={FORECAST_COLOR}
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={false}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-3">
            <div className="rounded-xl border border-white/10 bg-black/25 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Walk-forward MAE</p>
              <p className="mt-1 text-lg font-semibold text-emerald-300">
                {productionMae != null ? productionMae.toFixed(3) : "—"}
              </p>
              <p className="mt-1 text-xs text-zinc-500">2y tail · lower is better</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-black/25 p-3">
              <p className="mb-2 text-[10px] uppercase tracking-wider text-zinc-500">Model comparison</p>
              <div className="space-y-2">
                {methodRows.map((row) => (
                  <div key={row.name}>
                    <div className="flex items-center justify-between text-[11px]">
                      <span className={row.isProduction ? "font-medium text-emerald-300" : "text-zinc-400"}>
                        {row.label}
                        {row.isProduction ? " · prod" : ""}
                      </span>
                      <span className="text-zinc-500">{row.mae.toFixed(3)}</span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/5">
                      <div
                        className={`h-full rounded-full ${row.isProduction ? "bg-emerald-400" : "bg-zinc-600"}`}
                        style={{ width: `${Math.min(100, (row.mae / maxMae) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {!error && !loading && chartData.length === 0 && (
        <p className="mt-3 text-sm text-zinc-500">Refresh signals, then reload to see the production model.</p>
      )}

      {model?.interpretation && (
        <p className="mt-3 text-xs leading-relaxed text-zinc-500">{model.interpretation}</p>
      )}
    </section>
  );
}

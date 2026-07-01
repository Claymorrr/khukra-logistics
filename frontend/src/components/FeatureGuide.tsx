"use client";

import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Lightbulb,
  ListChecks,
} from "lucide-react";
import type { DisruptionSignal, DisruptionStatus } from "@/lib/api/disruption";

const SIGNAL_GUIDE: Record<
  string,
  { why: string; logisticsLink: string; sourceNote: string }
> = {
  vix: {
    why: "Measures expected equity volatility. When VIX spikes, risk appetite falls, financing tightens, and firms delay inventory and capex — a leading indicator of demand shocks.",
    logisticsLink:
      "High VIX often coincides with freight rate volatility, order cancellations, and supplier payment stress across global supply chains.",
    sourceNote: "FRED series VIXCLS — CBOE Volatility Index, daily close.",
  },
  oil_wti: {
    why: "WTI crude is a direct input cost for transport fuel, plastics, and energy-intensive manufacturing.",
    logisticsLink:
      "Oil shocks raise landed cost of goods, shift routing choices (slow-steam vs air), and stress carriers with fuel surcharges.",
    sourceNote: "FRED series DCOILWTICO — West Texas Intermediate spot price.",
  },
  usd_trade_weighted: {
    why: "A stronger trade-weighted dollar makes imports cheaper for US buyers but hurts exporters and emerging-market debtors.",
    logisticsLink:
      "FX moves affect invoice currency, hedging costs, and cross-border payment timing — especially for Asia–US and EU corridors.",
    sourceNote: "FRED series DTWEXBGS — broad trade-weighted USD index.",
  },
  hy_oas: {
    why: "High-yield option-adjusted spread measures credit risk premium. Widening spreads signal funding stress.",
    logisticsLink:
      "Tighter credit can force smaller 3PLs and suppliers to reduce capacity or extend lead times before macro headlines catch up.",
    sourceNote: "FRED series BAMLH0A0HYM2 — ICE BofA US High Yield OAS.",
  },
  shipping_basket: {
    why: "Equal-weight basket of ZIM, Hapag-Lloyd, and Maersk-B tracks liner equity sentiment more broadly than a single name.",
    logisticsLink:
      "Captures market expectations for freight rates, utilization, and carrier profitability across major container lines.",
    sourceNote: "Yahoo Finance — ZIM, HLAG.DE, MAERSK-B.CO daily close, equal-weight average.",
  },
  gscpi: {
    why: "NY Fed Global Supply Chain Pressure Index combines transport costs, delivery times, and backlogs into one macro logistics stress gauge.",
    logisticsLink:
      "Rising GSCPI precedes inventory build-ups, longer lead times, and spot-rate pressure — a direct supply-chain disruption read.",
    sourceNote: "NY Fed GSCPI CSV — monthly latest vintage, forward-filled to business days.",
  },
  eurusd: {
    why: "EUR/USD captures European trade corridor FX stress and transatlantic relative growth expectations.",
    logisticsLink:
      "Moves affect EU import costs, intra-EU sourcing decisions, and dollar-denominated commodity invoices for European buyers.",
    sourceNote: "Yahoo Finance ticker EURUSD=X — daily FX rate.",
  },
  news_stress: {
    why: "Objective-filtered RSS headlines with tone-adjusted impact scoring.",
    logisticsLink:
      "Keyword judgment plus VADER sentiment — negative logistics tone amplifies impact.",
    sourceNote:
      "Judgment layer on curated feeds; sports/noise dropped; NLP enriches retained stories.",
  },
  news_sentiment: {
    why: "Daily mean VADER compound polarity on retained headlines — captures tone beyond keywords.",
    logisticsLink:
      "Negative sentiment clusters often precede VIX and shipping proxy moves by a few days.",
    sourceNote: "Derived from title + summary of judgment-filtered headlines only.",
  },
};

const GLOSSARY = [
  {
    term: "Composite disruption z-index",
    definition:
      "For each signal, compute a 60-day rolling z-score (how many standard deviations today's level is from its recent mean). Average those z-scores equally across selected signals. Positive values mean broad elevation vs recent norms.",
    howToRead:
      "Compare current value to historical percentile. Above the 90th percentile (p90) suggests multi-factor stress, not just one noisy series.",
  },
  {
    term: "Pearson correlation (r)",
    definition:
      "Linear co-movement between two signals on aligned dates. r near +1 means they rise together; near −1 means inverse; near 0 means weak linear link.",
    howToRead:
      "|r| ≥ 0.5 is strong, 0.3–0.5 moderate. Check 95% credible interval and P(positive | data) instead of p-values.",
  },
  {
    term: "Spearman correlation",
    definition:
      "Rank-based correlation — captures monotonic relationships even when the link is non-linear (e.g. stress spikes in both series but not proportionally).",
    howToRead:
      "If Pearson is weak but Spearman is strong, the signals may move together in direction but not magnitude.",
  },
  {
    term: "Regime shift (z-score flag)",
    definition:
      "Flags when a single signal's current level is |z| ≥ 1.5 vs its 60-day rolling mean and standard deviation.",
    howToRead:
      "Elevated regime = unusually high vs recent history; depressed = unusually low. Useful for spotting which channel is driving stress today.",
  },
  {
    term: "Lead-lag analysis",
    definition:
      "Compares daily *returns* (not levels) of two signals, shifting one series by −20 to +20 days to find the lag with strongest correlation.",
    howToRead:
      "Positive lag means the leader tends to move first. Example: oil leading shipping equities by 5 days hints at fuel-cost transmission into freight sentiment.",
  },
  {
    term: "Holt linear forecast",
    definition:
      "Exponential smoothing with trend — projects the composite z-index forward 30 days using level + slope estimated from history.",
    howToRead:
      "Bayesian linear-trend forecast with 95% posterior predictive bands. Compare holdout MAE to the Holt benchmark.",
  },
  {
    term: "Coverage",
    definition:
      "Percentage of catalog signals that have been downloaded and stored in the local Parquet cache under data/disruption_cache/.",
    howToRead:
      "Discovery and forecast need coverage > 0%. Full coverage (100%) gives the most stable composite index.",
  },
];

const FEATURE_BLOCKS = [
  {
    id: "catalog",
    title: "Signal catalog",
    subtitle: "What feeds are available and why they were chosen",
    body: [
      "The catalog is a curated set of six public macro and market proxies. Each maps to a FRED or Yahoo Finance code — no API keys required.",
      "Signals are grouped by category: financial_stress, energy_logistics, fx_trade, credit_stress, and logistics. Together they approximate different transmission channels into supply-chain disruption risk.",
      "Use checkboxes to include or exclude signals from refresh, discovery, and forecast. Fewer signals = faster runs; all six = richest composite index.",
    ],
    outputs: ["Signal list with labels, sources, and descriptions", "Per-signal cache date range after refresh"],
  },
  {
    id: "refresh",
    title: "Data refresh (ingest)",
    subtitle: "Download and cache historical time series",
    body: [
      "Refresh pulls daily history from FRED (macro) and Yahoo Finance (market proxies) for the selected signals and year window (1–15 years).",
      "Data is stored locally as Parquet files so repeat analysis is fast and reproducible — you are not re-hitting APIs on every discovery run.",
      "After refresh, signals are aligned on a common calendar so correlations and composite scores compare apples-to-apples dates.",
      "First run can take 30–90 seconds depending on history length. Use “Refresh all signals” after initial setup; use “Refresh selected” when tuning a subset.",
    ],
    outputs: ["Updated coverage % and date ranges in the signal table", "Local cache ready for discovery"],
    prerequisites: ["API running on port 8010", "Network access to FRED and Yahoo"],
  },
  {
    id: "discover",
    title: "Statistical discovery",
    subtitle: "Automated insight mining over the aligned panel",
    body: [
      "Discovery profiles each signal (mean, std, missing %), then scans for three insight types: pairwise correlation, single-signal regime shifts, and return lead-lag structure.",
      "News headlines are translated into insights too: stress spikes, sentiment deterioration, dominant themes, top scored stories, and co-movement with macro signals.",
      "Correlation insights when 95% CI excludes zero or P(|r|>0.3) ≥ 70%. Regime insights when P(elevated|data) ≥ 75%. Lead-lag when P(|r|>0.3) ≥ 50%.",
      "Insights are ranked by strength (correlation magnitude, z-score, or lag correlation) and the top results are shown in the cockpit.",
      "The composite disruption z-index is computed on every discovery run — it is the headline single number for “how stressed is the multi-signal environment right now?”",
    ],
    outputs: [
      "Composite z-score, historical percentile, and time-series chart",
      "Ranked insight cards with plain-English interpretation",
      "Methodology summary from the analysis engine",
    ],
    prerequisites: ["Coverage > 0% — run refresh first", "At least ~30 overlapping observations per pair for correlations"],
  },
  {
    id: "forecast",
    title: "Composite risk forecast",
    subtitle: "30-day forward outlook on the disruption index",
    body: [
      "Bayesian linear-trend model on composite z-index with posterior predictive bands; holds out last 25% for predictive score.",
      "MAE (mean absolute error) and RMSE (root mean squared error) on the holdout set tell you how well the model tracked recent composite moves.",
      "Use forecast as an early-warning monitor — not a deterministic prediction. Pair it with discovery insights to understand *which* channels are driving the trend.",
    ],
    outputs: ["30-day point forecast with interpretation", "Holdout MAE and RMSE", "Updated composite risk context"],
    prerequisites: ["Cached composite history (≥40 observations)", "Refresh completed"],
  },
];

interface FeatureGuideProps {
  catalog: DisruptionSignal[];
  status: DisruptionStatus | null;
  hasDiscovery: boolean;
  coveragePct: number;
}

export function FeatureGuide({ catalog, status, hasDiscovery, coveragePct }: FeatureGuideProps) {
  const [openId, setOpenId] = useState<string | null>("catalog");

  const steps = [
    {
      done: (status?.covered_count ?? 0) > 0,
      label: "Refresh data",
      detail: "Download signal history so coverage is above 0%.",
    },
    {
      done: coveragePct >= 100,
      label: "Full coverage",
      detail: "All six signals cached for a stable composite index.",
    },
    {
      done: hasDiscovery,
      label: "Run discovery",
      detail: "Generate correlations, regimes, lead-lag, and composite z.",
    },
    {
      done: hasDiscovery,
      label: "Review & forecast",
      detail: "Read insights, then run 30-day composite forecast.",
    },
  ];

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-violet-500/20 bg-violet-500/[0.04] p-6">
        <p className="flex items-center gap-2 text-sm font-medium text-violet-200">
          <ListChecks className="h-4 w-4" />
          Getting started checklist
        </p>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          Follow these steps in order. The checklist updates automatically as you use the cockpit.
        </p>
        <ol className="mt-4 space-y-3">
          {steps.map((step, i) => (
            <li key={step.label} className="flex gap-3 text-sm">
              <span
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                  step.done
                    ? "bg-emerald-500/20 text-emerald-300"
                    : "border border-white/15 text-zinc-600"
                }`}
              >
                {step.done ? "✓" : i + 1}
              </span>
              <div>
                <p className={step.done ? "text-zinc-300" : "text-zinc-400"}>{step.label}</p>
                <p className="text-xs leading-5 text-zinc-600">{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <p className="flex items-center gap-2 text-sm font-medium text-zinc-300">
          <BookOpen className="h-4 w-4 text-amber-400" />
          Feature reference
        </p>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          Expand each feature to see purpose, prerequisites, outputs, and how to interpret results in
          your disruption risk workflow.
        </p>
        <div className="mt-4 space-y-2">
          {FEATURE_BLOCKS.map((block) => (
            <ExpandableBlock
              key={block.id}
              open={openId === block.id}
              onToggle={() => setOpenId(openId === block.id ? null : block.id)}
              title={block.title}
              subtitle={block.subtitle}
            >
              <div className="space-y-3 text-xs leading-5 text-zinc-500">
                {block.body.map((p) => (
                  <p key={p.slice(0, 40)}>{p}</p>
                ))}
                {block.prerequisites && (
                  <div>
                    <p className="font-medium text-zinc-400">Prerequisites</p>
                    <ul className="mt-1 list-inside list-disc space-y-0.5">
                      {block.prerequisites.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div>
                  <p className="font-medium text-zinc-400">What you get</p>
                  <ul className="mt-1 list-inside list-disc space-y-0.5">
                    {block.outputs.map((o) => (
                      <li key={o}>{o}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </ExpandableBlock>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <p className="flex items-center gap-2 text-sm font-medium text-zinc-300">
          <Lightbulb className="h-4 w-4 text-amber-400" />
          Signal encyclopedia
        </p>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          Why each feed matters for global logistics disruption analysis.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {catalog.map((sig) => {
            const guide = SIGNAL_GUIDE[sig.signal_id];
            return (
              <div
                key={sig.signal_id}
                className="rounded-xl border border-white/10 bg-black/25 p-4"
              >
                <p className="text-sm font-medium text-zinc-200">{sig.label}</p>
                <p className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-600">
                  {sig.category} · {sig.source} · {sig.signal_id}
                </p>
                <p className="mt-3 text-xs leading-5 text-zinc-400">{sig.description}</p>
                {guide && (
                  <>
                    <p className="mt-3 text-[10px] font-medium uppercase tracking-wider text-zinc-600">
                      Why it matters
                    </p>
                    <p className="mt-1 text-xs leading-5 text-zinc-500">{guide.why}</p>
                    <p className="mt-3 text-[10px] font-medium uppercase tracking-wider text-zinc-600">
                      Logistics link
                    </p>
                    <p className="mt-1 text-xs leading-5 text-zinc-500">{guide.logisticsLink}</p>
                    <p className="mt-3 text-[10px] text-zinc-600">{guide.sourceNote}</p>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <p className="flex items-center gap-2 text-sm font-medium text-zinc-300">
          <HelpCircle className="h-4 w-4 text-sky-400" />
          Metrics glossary
        </p>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          Definitions for every number and insight type shown in the cockpit.
        </p>
        <div className="mt-4 space-y-3">
          {GLOSSARY.map((item) => (
            <div key={item.term} className="rounded-xl border border-white/5 bg-black/20 px-4 py-3">
              <p className="text-sm font-medium text-zinc-300">{item.term}</p>
              <p className="mt-2 text-xs leading-5 text-zinc-500">{item.definition}</p>
              <p className="mt-2 text-[11px] leading-5 text-zinc-600">
                <span className="font-medium text-zinc-500">How to read it: </span>
                {item.howToRead}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ExpandableBlock({
  open,
  onToggle,
  title,
  subtitle,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
      >
        {open ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
        )}
        <div>
          <p className="text-sm font-medium text-zinc-200">{title}</p>
          <p className="text-xs text-zinc-600">{subtitle}</p>
        </div>
      </button>
      {open && <div className="border-t border-white/5 px-4 py-4 pl-11">{children}</div>}
    </div>
  );
}

export function ActionGuide({
  action,
  when,
  outcome,
  duration,
}: {
  action: string;
  when: string;
  outcome: string;
  duration?: string;
}) {
  return (
    <div className="rounded-lg border border-white/5 bg-black/15 px-3 py-2.5">
      <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-600">{action}</p>
      <p className="mt-1 text-[11px] leading-4 text-zinc-500">
        <span className="text-zinc-400">When: </span>
        {when}
      </p>
      <p className="mt-1 text-[11px] leading-4 text-zinc-500">
        <span className="text-zinc-400">Result: </span>
        {outcome}
      </p>
      {duration && (
        <p className="mt-1 text-[11px] leading-4 text-zinc-600">
          <span className="text-zinc-500">Typical time: </span>
          {duration}
        </p>
      )}
    </div>
  );
}

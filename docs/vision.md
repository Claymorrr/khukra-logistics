# Khukra Logistics Vision

Khukra Logistics is a **hybrid disruption forecast** platform.

## North star

> **Forecast precision** — measured daily. Is the composite forecast right?

Everything else exists to improve that score:

| Layer | Role |
|-------|------|
| **Hybrid ingest** | Macro (FRED) + market (Yahoo) + news (RSS/NLP) |
| **Discover** | Find lead-lag and structure to tune the panel |
| **Explore** | Test which signals add predictive density |
| **NLP** | Improve news channel relevance and leading power |
| **Simulation** | Stress-test when live data is sparse |

## Hybrid data model

```
macro (FRED)     ─┐
market (Yahoo)   ─┼─► equal-weight z-score composite ─► forecast ─► daily precision score
news (RSS/NLP)   ─┘
```

Three channels, one panel, one measurable outcome.

## Primary workflow

```
refresh (hybrid ingest) → evaluate (daily precision) → forecast → discover/explore (diagnose)
```

### 1. Ingest (hybrid)

- **Macro** — VIX, WTI, USD, HY OAS (FRED)
- **Market** — shipping proxy, EUR/USD (Yahoo)
- **News** — judgment-filtered RSS + VADER (`news_stress`, `news_sentiment`)

### 2. Evaluate (daily)

Walk-forward 1-step MAE on the composite, direction hit rate, channel ablation (macro/market/news lift), precision score 0–100, verdict (`on_track` | `improving` | `needs_work`).

Persisted under `data/disruption_cache/evaluation/evaluation_YYYY-MM-DD.json`.

Runs automatically after **Refresh** and **Poll RSS**. CLI: `khukra-logistics evaluate`.

### 3. Forecast

Bayesian linear-trend projection with credible bands — useful only if daily evaluation says the panel is on track.

### 4. Discover & Explore (servants, not goals)

Correlation, lead-lag, regimes, MI, PCA, predictive screen — use these to answer: *which hybrid channel or signal improves precision?*

## Simulation models (secondary)

Synthetic disruption, quality, and resilience models for scenario stress when empirical coverage is thin.

## Relationship to Khukra

Separate repository from [Khukra](https://github.com/Claymorrr/khukra) (finance). Shared patterns: CLI, API, local cache, reproducible artifacts.

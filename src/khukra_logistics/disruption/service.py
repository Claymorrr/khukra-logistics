"""Disruption data ingest, discovery, and forecast orchestration."""

from __future__ import annotations

import time
import uuid
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from khukra_logistics.disruption.adapters import fred, gscpi, yahoo
from khukra_logistics.disruption.cache import load_panel, repair_signal_dates, save_signal, signal_path, signal_status
from khukra_logistics.disruption.catalog import DISRUPTION_SIGNALS, get_signal, hybrid_channel, list_signals
from khukra_logistics.disruption.evaluation import (
    evaluate_forecast_precision,
    latest_evaluation,
    load_evaluation_history,
    save_daily_evaluation,
)
from khukra_logistics.disruption.exploratory import run_advanced_exploration
from khukra_logistics.disruption.hybrid_composite import SPARSE_SIGNALS
from khukra_logistics.disruption.news.cache import load_headlines
from khukra_logistics.disruption.news.insights import discover_news_insights
from khukra_logistics.disruption.news.service import ingest_news_feeds, news_status
from khukra_logistics.disruption.statistics import (
    composite_risk_index,
    discover_insights,
    forecast_composite,
    profile_panel,
)


class DisruptionIntelligenceService:
    def catalog(self) -> dict[str, Any]:
        signals = list_signals()
        return {
            "focus": "global_disruption_forecast",
            "north_star": "forecast_precision",
            "hybrid_channels": ["macro", "market", "news"],
            "signal_count": len(signals),
            "signals": [
                {
                    "signal_id": s.signal_id,
                    "label": s.label,
                    "category": s.category,
                    "hybrid_channel": hybrid_channel(s),
                    "source": s.source,
                    "description": s.description,
                }
                for s in signals
            ],
            "categories": sorted({s.category for s in signals}),
        }

    def status(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        covered = 0
        for signal in DISRUPTION_SIGNALS:
            meta = signal_status(signal.signal_id)
            if meta is not None:
                covered += 1
                rows.append(
                    {
                        "signal_id": signal.signal_id,
                        "label": signal.label,
                        "category": signal.category,
                        "source": signal.source,
                        **meta,
                        "cache_path": str(signal_path(signal.signal_id)),
                    }
                )
            else:
                rows.append(
                    {
                        "signal_id": signal.signal_id,
                        "label": signal.label,
                        "category": signal.category,
                        "source": signal.source,
                        "first_date": None,
                        "last_date": None,
                        "row_count": None,
                        "cache_path": None,
                    }
                )
        return {
            "signal_count": len(DISRUPTION_SIGNALS),
            "covered_count": covered,
            "signals": rows,
        }

    def refresh(
        self,
        signal_ids: list[str] | None = None,
        years: int = 5,
    ) -> dict[str, Any]:
        end = date.today()
        start = end - timedelta(days=365 * years)
        targets = [get_signal(sid) for sid in signal_ids] if signal_ids else list_signals()
        targets = [t for t in targets if t is not None]

        run_id = str(uuid.uuid4())[:12]
        refreshed = 0
        errors: list[dict[str, str]] = []

        news_ingested = False
        news_result: dict[str, Any] | None = None

        for signal in targets:
            try:
                if signal.source == "news":
                    if not news_ingested:
                        news_result = ingest_news_feeds()
                        news_ingested = True
                    result = news_result or {}
                    if (
                        result.get("stress_days", 0) > 0
                        or result.get("sentiment_days", 0) > 0
                        or result.get("entries_new", 0) > 0
                    ):
                        refreshed += 1
                    else:
                        errors.append(
                            {
                                "signal_id": signal.signal_id,
                                "error": "no headlines ingested",
                            }
                        )
                    continue
                if signal.source == "fred":
                    df = fred.fetch_daily_series(signal.source_code, start, end)
                elif signal.source == "gscpi":
                    monthly = gscpi.fetch_monthly_series(start, end)
                    df = gscpi.expand_to_business_days(monthly)
                elif signal.source == "yahoo_basket":
                    df = yahoo.fetch_shipping_basket(start=start, end=end)
                elif signal.source == "yahoo":
                    df = yahoo.fetch_daily_series(signal.source_code, start, end)
                else:
                    errors.append({"signal_id": signal.signal_id, "error": "unknown source"})
                    continue
                if df.empty:
                    errors.append({"signal_id": signal.signal_id, "error": "no data returned"})
                    continue
                save_signal(signal.signal_id, df)
                refreshed += 1
                time.sleep(0.2)
            except Exception as exc:
                errors.append({"signal_id": signal.signal_id, "error": str(exc)})

        return {
            "run_id": run_id,
            "signals_requested": len(targets),
            "signals_refreshed": refreshed,
            "errors": errors,
            "status": "completed" if refreshed else "failed",
            "evaluation": self._safe_daily_evaluation(),
        }

    def refresh_news(self) -> dict[str, Any]:
        """Fast RSS poll — optimized for low-latency headline ingest."""
        result = ingest_news_feeds()
        result["evaluation"] = self._safe_daily_evaluation()
        return result

    def get_news_status(self) -> dict[str, Any]:
        return news_status()

    def discover(self, signal_ids: list[str] | None = None) -> dict[str, Any]:
        repair_signal_dates()
        panel = load_panel(signal_ids)
        if panel.empty:
            raise ValueError("No cached disruption data. Run refresh first.")
        profile = profile_panel(panel)
        insights = discover_insights(panel)
        headlines = load_headlines()
        news_insights = discover_news_insights(headlines, panel)
        merged = news_insights + insights["insights"]
        merged.sort(
            key=lambda x: abs(
                x.get(
                    "stress_score",
                    x.get("prob_strong", x.get("prob_elevated", x.get("pearson_r", x.get("correlation", 0)))),
                )
            ),
            reverse=True,
        )
        insights = {
            **insights,
            "insight_count": len(merged),
            "insights": merged,
            "methodology": (
                insights["methodology"]
                + " News layer: headline keyword spikes, theme counts, top stories, "
                "and zero-filled news_stress co-movement with macro signals."
            ),
        }
        composite = composite_risk_index(panel)
        return {
            "profile": profile,
            "composite_risk": composite,
            "discovery": insights,
        }

    def explore(self, signal_ids: list[str] | None = None) -> dict[str, Any]:
        repair_signal_dates()
        panel = load_panel(signal_ids)
        if panel.empty:
            raise ValueError("No cached disruption data. Run refresh first.")
        dense_cols = [c for c in panel.columns if c != "date" and c not in SPARSE_SIGNALS]
        signal_scope = "selected"
        if len(dense_cols) < 2:
            panel = load_panel(None)
            signal_scope = "all_cached"
        if panel.empty:
            raise ValueError("No cached disruption data. Run refresh first.")
        if len(panel) > 504:
            panel = panel.tail(504).reset_index(drop=True)
        result = run_advanced_exploration(panel)
        result["signal_scope"] = signal_scope
        result["methods_expected"] = 7
        return result

    def forecast(self, signal_ids: list[str] | None = None, horizon: int = 30) -> dict[str, Any]:
        panel = load_panel(signal_ids)
        if panel.empty:
            raise ValueError("No cached disruption data. Run refresh first.")
        composite = composite_risk_index(panel)
        forecast = forecast_composite(panel, horizon=horizon)
        return {
            "composite_risk": composite,
            "forecast": forecast,
            "evaluation": self._safe_daily_evaluation(signal_ids, horizon),
        }

    def evaluate(
        self,
        signal_ids: list[str] | None = None,
        horizon: int = 30,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Daily forecast-precision measurement on the hybrid panel."""
        repair_signal_dates()
        panel = load_panel(signal_ids)
        if panel.empty:
            raise ValueError("No cached disruption data. Run refresh first.")
        result = evaluate_forecast_precision(panel, horizon_days=horizon)
        path = None
        if persist:
            path = save_daily_evaluation(result)
        history = load_evaluation_history(days=14)
        return {
            "evaluation": result,
            "saved_to": str(path) if path else None,
            "history_days": len(history),
            "history": [
                {
                    "evaluation_date": row.get("evaluation_date"),
                    "precision_score": row.get("precision_score"),
                    "verdict": row.get("verdict"),
                    "best_method": row.get("walk_forward", {}).get("best_method"),
                    "walk_forward_mae": row.get("walk_forward", {})
                    .get("methods", {})
                    .get(
                        row.get("walk_forward", {}).get("best_method", "bayesian_linear"),
                        {},
                    )
                    .get("walk_forward_mae"),
                }
                for row in history
            ],
        }

    def evaluation_history(self, days: int = 30) -> dict[str, Any]:
        history = load_evaluation_history(days=days)
        latest = history[0] if history else latest_evaluation()
        return {"latest": latest, "history": history, "days": days}

    def _safe_daily_evaluation(
        self,
        signal_ids: list[str] | None = None,
        horizon: int = 30,
    ) -> dict[str, Any] | None:
        try:
            return self.evaluate(signal_ids, horizon, persist=True)["evaluation"]
        except ValueError:
            return None

    def panel_data(
        self,
        signal_ids: list[str] | None = None,
        tail_days: int | None = 504,
        scale: str = "raw",
        table_rows: int = 50,
    ) -> dict[str, Any]:
        """Return aligned panel series for charts and tables."""
        repair_signal_dates()
        panel = load_panel(signal_ids)
        if panel.empty:
            raise ValueError("No cached disruption data. Run refresh first.")

        signal_cols = [c for c in panel.columns if c != "date"]
        if tail_days and tail_days > 0:
            panel = panel.tail(tail_days).reset_index(drop=True)

        scaled = panel.copy()
        for col in signal_cols:
            s = scaled[col]
            if scale == "rebased":
                base = s.dropna()
                if len(base):
                    scaled[col] = (s / float(base.iloc[0])) * 100.0
            elif scale == "zscore":
                mean = s.rolling(60, min_periods=20).mean()
                std = s.rolling(60, min_periods=20).std().replace(0, np.nan)
                scaled[col] = (s - mean) / std

        series_rows: list[dict[str, Any]] = []
        for _, row in scaled.iterrows():
            entry: dict[str, Any] = {"date": row["date"].strftime("%Y-%m-%d")}
            for col in signal_cols:
                val = row[col]
                if pd.isna(val):
                    entry[col] = None
                else:
                    entry[col] = round(float(val), 6)
            series_rows.append(entry)

        recent = series_rows[-table_rows:] if table_rows > 0 else []

        missing: dict[str, float] = {}
        for col in signal_cols:
            missing[col] = round(float(panel[col].isna().mean() * 100), 2)

        profile = profile_panel(panel)

        return {
            "scale": scale,
            "tail_days": tail_days,
            "signal_ids": signal_cols,
            "date_range": {
                "start": panel["date"].min().strftime("%Y-%m-%d"),
                "end": panel["date"].max().strftime("%Y-%m-%d"),
            },
            "row_count": int(len(panel)),
            "missing_pct": missing,
            "profile": profile,
            "series": series_rows,
            "recent_rows": recent,
        }


_service: DisruptionIntelligenceService | None = None


def get_disruption_service() -> DisruptionIntelligenceService:
    global _service
    if _service is None:
        _service = DisruptionIntelligenceService()
    return _service

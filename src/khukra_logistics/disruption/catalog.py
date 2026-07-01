"""Curated global disruption signal feeds for ingest and discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceKind = Literal["fred", "yahoo", "yahoo_basket", "gscpi", "news"]
HybridChannel = Literal["macro", "market", "news"]


@dataclass(frozen=True)
class DisruptionSignal:
    signal_id: str
    label: str
    category: str
    source: SourceKind
    source_code: str
    description: str


# Public macro and market proxies for global logistics disruption risk.
DISRUPTION_SIGNALS: tuple[DisruptionSignal, ...] = (
    DisruptionSignal(
        "vix",
        "VIX implied volatility",
        "financial_stress",
        "fred",
        "VIXCLS",
        "Equity volatility — global risk-off sentiment",
    ),
    DisruptionSignal(
        "oil_wti",
        "WTI crude oil",
        "energy_logistics",
        "fred",
        "DCOILWTICO",
        "Energy cost shock proxy for freight and production",
    ),
    DisruptionSignal(
        "usd_trade_weighted",
        "Trade-weighted USD index",
        "fx_trade",
        "fred",
        "DTWEXBGS",
        "Dollar strength — import cost and trade friction",
    ),
    DisruptionSignal(
        "hy_oas",
        "High-yield OAS spread",
        "credit_stress",
        "fred",
        "BAMLH0A0HYM2",
        "Credit stress — funding and supplier distress",
    ),
    DisruptionSignal(
        "gscpi",
        "Global Supply Chain Pressure Index",
        "logistics",
        "gscpi",
        "GSCPI",
        "NY Fed composite of transport cost, delivery times, and backlogs",
    ),
    DisruptionSignal(
        "shipping_basket",
        "Shipping equities basket (ZIM / Hapag / Maersk)",
        "logistics",
        "yahoo_basket",
        "ZIM,HLAG.DE,MAERSK-B.CO",
        "Equal-weight liner shipping sentiment — broader than single-name proxy",
    ),
    DisruptionSignal(
        "eurusd",
        "EUR/USD",
        "fx_trade",
        "yahoo",
        "EURUSD=X",
        "European trade corridor FX stress",
    ),
    DisruptionSignal(
        "news_stress",
        "News disruption stress index",
        "news_intelligence",
        "news",
        "rss_aggregate",
        "Judgment-filtered RSS headlines with tone-adjusted impact scoring",
    ),
    DisruptionSignal(
        "news_sentiment",
        "News sentiment index",
        "news_intelligence",
        "news",
        "rss_sentiment",
        "Daily mean VADER compound polarity on retained headlines (−1 negative … +1 positive)",
    ),
)


def list_signals(category: str | None = None) -> list[DisruptionSignal]:
    if not category:
        return list(DISRUPTION_SIGNALS)
    return [s for s in DISRUPTION_SIGNALS if s.category == category]


def get_signal(signal_id: str) -> DisruptionSignal | None:
    key = signal_id.lower()
    for signal in DISRUPTION_SIGNALS:
        if signal.signal_id == key:
            return signal
    return None


def hybrid_channel(signal: DisruptionSignal) -> HybridChannel:
    """Hybrid data layer: macro (FRED), market (Yahoo), news (RSS/NLP)."""
    if signal.source == "news":
        return "news"
    if signal.source in ("yahoo", "yahoo_basket"):
        return "market"
    return "macro"


def list_hybrid_channels() -> list[HybridChannel]:
    return ["macro", "market", "news"]

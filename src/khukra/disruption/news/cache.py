"""Cache for ingested headlines and derived news stress series."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from khukra.simulation.shared import data_root


def news_cache_dir() -> Path:
    path = data_root() / "news_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def headlines_path() -> Path:
    return news_cache_dir() / "headlines.parquet"


def load_headlines() -> pd.DataFrame:
    path = headlines_path()
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "link",
                "feed_id",
                "title",
                "summary",
                "published_at",
                "stress_score",
                "impact_score",
                "relevance_score",
                "judgment_tier",
                "matched_keywords",
                "judgment_rationale",
                "sentiment_compound",
                "sentiment_positive",
                "sentiment_negative",
                "sentiment_neutral",
                "sentiment_is_negative",
                "entities_json",
                "entity_ports",
                "entity_canals",
                "entity_carriers",
                "entity_countries",
                "entity_commodities",
                "entity_count",
                "ingested_at",
            ]
        )
    df = pd.read_parquet(path)
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    if "ingested_at" in df.columns:
        df["ingested_at"] = pd.to_datetime(df["ingested_at"], utc=True)
    return df


def save_headlines(df: pd.DataFrame) -> Path:
    out = df.copy()
    out["published_at"] = pd.to_datetime(out["published_at"], utc=True)
    out.to_parquet(headlines_path(), index=False)
    return headlines_path()

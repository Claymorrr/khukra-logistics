"""RSS ingest, judgment, NLP enrichment, and daily news signals."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from khukra.disruption.adapters.rss import fetch_feed
from khukra.disruption.cache import normalize_signal_dates, save_signal
from khukra.disruption.news.cache import load_headlines, save_headlines
from khukra.disruption.news.enrich import enrich_headline_row
from khukra.disruption.news.entities import ENTITY_COUNT_SIGNALS, extract_entities
from khukra.disruption.news.feeds import FEEDS_BY_ID, NEWS_FEEDS
from khukra.disruption.news.judgment import OBJECTIVE, judge_headline

STRESS_SIGNAL_ID = "news_stress"
SENTIMENT_SIGNAL_ID = "news_sentiment"
SIGNAL_ID = STRESS_SIGNAL_ID
ENTITY_SIGNAL_IDS = tuple(ENTITY_COUNT_SIGNALS.keys())

HEADLINE_COLUMNS = [
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


def _normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    n = len(title)
    if n >= 4 and n % 2 == 0 and title[: n // 2] == title[n // 2 :]:
        return title[: n // 2]
    return title


def _normalize_link(link: str, title: str) -> str:
    link = (link or title).strip()
    if link.count("http") > 1:
        second = link.find("http", 4)
        if second > 0:
            link = link[:second]
    return link


def _feed_category(feed_id: str) -> str:
    feed = FEEDS_BY_ID.get(feed_id)
    return feed.category if feed else "macro"


def _impact_column(headlines: pd.DataFrame) -> str:
    if "impact_score" in headlines.columns:
        return "impact_score"
    return "stress_score"


def _row_from_verdict(row: pd.Series, verdict: Any, now: datetime) -> dict[str, Any]:
    return enrich_headline_row(
        {
            "link": _normalize_link(str(row["link"]), str(row["title"])),
            "feed_id": str(row["feed_id"]),
            "title": _normalize_title(str(row["title"])),
            "summary": str(row.get("summary", ""))[:500],
            "published_at": row["published_at"],
            "stress_score": verdict.impact_score,
            "impact_score": verdict.impact_score,
            "relevance_score": verdict.relevance_score,
            "judgment_tier": verdict.tier,
            "matched_keywords": ",".join(verdict.channels),
            "judgment_rationale": verdict.rationale,
            "ingested_at": row.get("ingested_at", now),
        }
    )


def _row_from_entry(entry: Any, verdict: Any, now: datetime) -> dict[str, Any]:
    return enrich_headline_row(
        {
            "link": _normalize_link(entry.link, entry.title),
            "feed_id": entry.feed_id,
            "title": _normalize_title(entry.title),
            "summary": entry.summary[:500],
            "published_at": entry.published_at,
            "stress_score": verdict.impact_score,
            "impact_score": verdict.impact_score,
            "relevance_score": verdict.relevance_score,
            "judgment_tier": verdict.tier,
            "matched_keywords": ",".join(verdict.channels),
            "judgment_rationale": verdict.rationale,
            "ingested_at": now,
        }
    )


def _prune_and_enrich_headlines(headlines: pd.DataFrame) -> pd.DataFrame:
    """Re-judge, NLP-enrich, and drop off-objective headlines."""
    if headlines.empty:
        return headlines
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for _, row in headlines.iterrows():
        text = f"{row['title']}. {row.get('summary', '')}"
        verdict = judge_headline(text, _feed_category(str(row["feed_id"])))
        if not verdict.relevant:
            continue
        rows.append(_row_from_verdict(row, verdict, now))
    if not rows:
        return pd.DataFrame(columns=HEADLINE_COLUMNS)
    out = pd.DataFrame(rows)
    out["published_at"] = pd.to_datetime(out["published_at"], utc=True)
    out["ingested_at"] = pd.to_datetime(out["ingested_at"], utc=True)
    return out.drop_duplicates(subset=["link"], keep="first").sort_values(
        "published_at", ascending=False
    )


def _save_daily_signals(
    headlines: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    stress = _build_daily_stress(headlines)
    sentiment = _build_daily_sentiment(headlines)
    entity_counts = _build_daily_entity_counts(headlines)
    if not stress.empty:
        save_signal(STRESS_SIGNAL_ID, stress)
    if not sentiment.empty:
        save_signal(SENTIMENT_SIGNAL_ID, sentiment)
    for signal_id, series in entity_counts.items():
        if not series.empty:
            save_signal(signal_id, series)
    return stress, sentiment, entity_counts


def ingest_news_feeds() -> dict[str, Any]:
    """Poll RSS feeds, judge relevance, enrich with NLP, retain objective-aligned headlines."""
    started = time.perf_counter()
    existing = _prune_and_enrich_headlines(load_headlines())
    known_links = set(existing["link"].astype(str).tolist()) if not existing.empty else set()

    fetched = 0
    retained_new = 0
    rejected_new = 0
    new_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)

    for feed in NEWS_FEEDS:
        try:
            entries = fetch_feed(feed.feed_id, feed.url)
            fetched += len(entries)
            for entry in entries:
                link = _normalize_link(entry.link, entry.title)
                if link in known_links:
                    continue
                text = f"{entry.title}. {entry.summary}"
                verdict = judge_headline(text, feed.category)
                if not verdict.relevant:
                    rejected_new += 1
                    continue
                retained_new += 1
                new_rows.append(_row_from_entry(entry, verdict, now))
                known_links.add(link)
            time.sleep(0.15)
        except Exception as exc:
            errors.append({"feed_id": feed.feed_id, "error": str(exc)})

    merged = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True) if new_rows else existing

    if not merged.empty:
        merged = _prune_and_enrich_headlines(merged)
        save_headlines(merged)

    stress_daily, sentiment_daily, entity_daily = _save_daily_signals(merged)
    negative_count = int(merged["sentiment_is_negative"].sum()) if "sentiment_is_negative" in merged.columns else 0
    entity_headline_count = (
        int((merged["entity_count"].fillna(0).astype(int) > 0).sum())
        if not merged.empty and "entity_count" in merged.columns
        else 0
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "signal_id": STRESS_SIGNAL_ID,
        "sentiment_signal_id": SENTIMENT_SIGNAL_ID,
        "entity_signal_ids": list(ENTITY_SIGNAL_IDS),
        "objective": OBJECTIVE,
        "feeds_polled": len(NEWS_FEEDS),
        "entries_fetched": fetched,
        "entries_new": retained_new,
        "entries_rejected": rejected_new,
        "entries_retained": int(len(merged)),
        "headlines_total": int(len(merged)),
        "negative_headlines": negative_count,
        "entity_headlines": entity_headline_count,
        "stress_days": int(len(stress_daily)),
        "sentiment_days": int(len(sentiment_daily)),
        "entity_signal_days": {sid: int(len(series)) for sid, series in entity_daily.items()},
        "latency_ms": elapsed_ms,
        "errors": errors,
        "recent_headlines": _recent_headlines(merged, limit=20),
        "status": "completed" if not merged.empty or retained_new else "partial",
    }


def _build_daily_stress(headlines: pd.DataFrame) -> pd.DataFrame:
    if headlines.empty:
        return pd.DataFrame(columns=["date", "value"])
    impact_col = _impact_column(headlines)
    hits = headlines[headlines[impact_col] > 0].copy()
    if hits.empty:
        return pd.DataFrame(columns=["date", "value"])
    hits["published_at"] = pd.to_datetime(hits["published_at"], utc=True)
    hits["date"] = hits["published_at"].dt.floor("D")
    daily = hits.groupby("date", as_index=False)[impact_col].sum()
    daily = daily.rename(columns={impact_col: "value"})
    daily["date"] = normalize_signal_dates(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)


def _build_daily_sentiment(headlines: pd.DataFrame) -> pd.DataFrame:
    if headlines.empty or "sentiment_compound" not in headlines.columns:
        return pd.DataFrame(columns=["date", "value"])
    hits = headlines.copy()
    hits["published_at"] = pd.to_datetime(hits["published_at"], utc=True)
    hits["date"] = hits["published_at"].dt.floor("D")
    daily = hits.groupby("date", as_index=False)["sentiment_compound"].mean()
    daily = daily.rename(columns={"sentiment_compound": "value"})
    daily["date"] = normalize_signal_dates(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)


def _headline_has_entity(row: pd.Series, entity_type: str, entity_id: str) -> bool:
    """True if cached columns or live extraction contain the target entity."""
    col_map = {
        "port": "entity_ports",
        "canal": "entity_canals",
        "carrier": "entity_carriers",
        "country": "entity_countries",
        "commodity": "entity_commodities",
    }
    col = col_map.get(entity_type)
    if col and col in row.index and pd.notna(row.get(col)) and str(row.get(col)).strip():
        ids = {part.strip() for part in str(row[col]).split(",") if part.strip()}
        if entity_id == "*":
            return bool(ids)
        return entity_id in ids

    text = f"{row.get('title', '')}. {row.get('summary', '')}"
    extracted = extract_entities(text)
    if entity_id == "*":
        return bool(extracted.ids_for(entity_type))
    return extracted.has(entity_type, entity_id)


def _build_daily_entity_counts(headlines: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Daily mention counts for chokepoint / carrier entity signals."""
    empty = {sid: pd.DataFrame(columns=["date", "value"]) for sid in ENTITY_SIGNAL_IDS}
    if headlines.empty:
        return empty

    work = headlines.copy()
    work["published_at"] = pd.to_datetime(work["published_at"], utc=True)
    work["date"] = work["published_at"].dt.floor("D")

    out: dict[str, pd.DataFrame] = {}
    for signal_id, (entity_type, entity_id) in ENTITY_COUNT_SIGNALS.items():
        mask = work.apply(lambda row: _headline_has_entity(row, entity_type, entity_id), axis=1)
        hits = work.loc[mask]
        if hits.empty:
            out[signal_id] = pd.DataFrame(columns=["date", "value"])
            continue
        daily = hits.groupby("date", as_index=False).size().rename(columns={"size": "value"})
        daily["date"] = normalize_signal_dates(daily["date"])
        out[signal_id] = daily.sort_values("date").reset_index(drop=True)
    return out


def _recent_headlines(headlines: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    if headlines.empty:
        return []
    impact_col = _impact_column(headlines)
    top = headlines.sort_values(impact_col, ascending=False).head(limit)
    out: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        out.append(
            {
                "feed_id": str(row["feed_id"]),
                "title": str(row["title"]),
                "link": str(row["link"]),
                "published_at": row["published_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "stress_score": round(float(row[impact_col]), 2),
                "impact_score": round(float(row.get("impact_score", row[impact_col])), 2),
                "relevance_score": round(float(row.get("relevance_score", 0)), 3),
                "judgment_tier": str(row.get("judgment_tier", "core")),
                "matched_keywords": str(row.get("matched_keywords", "")),
                "judgment_rationale": str(row.get("judgment_rationale", "")),
                "sentiment_compound": round(float(row.get("sentiment_compound", 0)), 3),
                "sentiment_is_negative": bool(row.get("sentiment_is_negative", False)),
                "entity_ports": str(row.get("entity_ports", "") or ""),
                "entity_canals": str(row.get("entity_canals", "") or ""),
                "entity_carriers": str(row.get("entity_carriers", "") or ""),
                "entity_countries": str(row.get("entity_countries", "") or ""),
                "entity_commodities": str(row.get("entity_commodities", "") or ""),
                "entity_count": int(row.get("entity_count", 0) or 0),
            }
        )
    return out


def news_status() -> dict[str, Any]:
    raw = load_headlines()
    headlines = _prune_and_enrich_headlines(raw)
    needs_rewrite = len(headlines) != len(raw) or (
        not headlines.empty
        and (
            "sentiment_compound" not in raw.columns
            or "entities_json" not in raw.columns
        )
    )
    if needs_rewrite:
        save_headlines(headlines)
        _save_daily_signals(headlines)
    stress_daily = _build_daily_stress(headlines)
    sentiment_daily = _build_daily_sentiment(headlines)
    entity_daily = _build_daily_entity_counts(headlines)
    impact_col = _impact_column(headlines) if not headlines.empty else "impact_score"
    negative_count = (
        int(headlines["sentiment_is_negative"].sum())
        if not headlines.empty and "sentiment_is_negative" in headlines.columns
        else 0
    )
    entity_headline_count = (
        int((headlines["entity_count"].fillna(0).astype(int) > 0).sum())
        if not headlines.empty and "entity_count" in headlines.columns
        else 0
    )
    return {
        "signal_id": STRESS_SIGNAL_ID,
        "sentiment_signal_id": SENTIMENT_SIGNAL_ID,
        "entity_signal_ids": list(ENTITY_SIGNAL_IDS),
        "objective": OBJECTIVE,
        "feeds": [{"feed_id": f.feed_id, "label": f.label, "url": f.url} for f in NEWS_FEEDS],
        "headlines_total": int(len(headlines)),
        "stress_headlines": int((headlines[impact_col] > 0).sum()) if not headlines.empty else 0,
        "negative_headlines": negative_count,
        "entity_headlines": entity_headline_count,
        "first_date": str(stress_daily["date"].min().date()) if not stress_daily.empty else None,
        "last_date": str(stress_daily["date"].max().date()) if not stress_daily.empty else None,
        "sentiment_first_date": str(sentiment_daily["date"].min().date())
        if not sentiment_daily.empty
        else None,
        "sentiment_last_date": str(sentiment_daily["date"].max().date())
        if not sentiment_daily.empty
        else None,
        "entity_signal_days": {sid: int(len(series)) for sid, series in entity_daily.items()},
        "recent_headlines": _recent_headlines(headlines, limit=15),
    }

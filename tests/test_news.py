"""Tests for RSS news ingest and news_stress signal."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from xml.etree.ElementTree import Element, SubElement, tostring

import pandas as pd
import pytest

from khukra_logistics.disruption.news.insights import discover_news_insights
from khukra_logistics.disruption.news.judgment import judge_headline
from khukra_logistics.disruption.news.keywords import score_headline
from khukra_logistics.disruption.news.service import ingest_news_feeds


def _sample_rss() -> bytes:
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    item = SubElement(channel, "item")
    SubElement(item, "title").text = "Major port strike causes shipping delays"
    SubElement(item, "link").text = "https://example.com/strike-1"
    SubElement(item, "pubDate").text = "Mon, 01 Jan 2024 12:00:00 GMT"
    SubElement(item, "description").text = "Congestion at container terminal."
    return tostring(rss)


def test_score_headline_matches_keywords():
    score, kws = score_headline("Port strike leads to freight delays and congestion")
    assert score > 0
    assert "strike" in kws
    assert "port" in kws


def test_judge_rejects_off_topic_before_ingest():
    v = judge_headline("Brewery boss who banned phones from pubs dies aged 81", "macro")
    assert v.relevant is False


def test_ingest_filters_irrelevant_headlines(tmp_path, monkeypatch):
    monkeypatch.setenv("KHUKRA_LOGISTICS_DATA_ROOT", str(tmp_path))

    def fake_fetch(feed_id: str, url: str):
        from khukra_logistics.disruption.adapters.rss import RssEntry

        return [
            RssEntry(
                feed_id,
                "Sanctions disrupt shipping lane",
                f"https://example.com/{feed_id}-ok",
                datetime(2024, 1, 2, tzinfo=timezone.utc),
                "Embargo affects canal route.",
            ),
            RssEntry(
                feed_id,
                "World Cup fans celebrate in city centre",
                f"https://example.com/{feed_id}-noise",
                datetime(2024, 1, 2, tzinfo=timezone.utc),
                "Football celebrations continue.",
            ),
        ]

    monkeypatch.setattr("khukra_logistics.disruption.news.service.fetch_feed", fake_fetch)
    result = ingest_news_feeds()
    assert result["entries_new"] == 6
    assert result["entries_rejected"] == 6
    assert result["headlines_total"] == 6


def test_ingest_news_with_mocked_feeds(tmp_path, monkeypatch):
    monkeypatch.setenv("KHUKRA_LOGISTICS_DATA_ROOT", str(tmp_path))

    def fake_fetch(feed_id: str, url: str):
        from khukra_logistics.disruption.adapters.rss import RssEntry

        return [
            RssEntry(
                feed_id,
                "Sanctions disrupt shipping lane",
                f"https://example.com/{feed_id}-1",
                datetime(2024, 1, 2, tzinfo=timezone.utc),
                "Embargo affects canal route.",
            )
        ]

    monkeypatch.setattr("khukra_logistics.disruption.news.service.fetch_feed", fake_fetch)
    result = ingest_news_feeds()
    json.dumps(result)
    assert result["entries_new"] >= 1
    assert result["stress_days"] >= 1

    from khukra_logistics.disruption.cache import load_signal

    series = load_signal("news_stress")
    assert series is not None
    assert not series.empty


def test_discover_news_insights_from_headlines():
    now = datetime.now(timezone.utc)
    headlines = pd.DataFrame(
        [
            {
                "feed_id": "freightwaves",
                "title": "Port strike causes major shipping delays",
                "link": "https://example.com/1",
                "summary": "Congestion at container terminal.",
                "published_at": now - timedelta(hours=2),
                "stress_score": 3.0,
                "impact_score": 3.0,
                "matched_keywords": "strike,port,shipping,delay",
                "ingested_at": now,
            },
            {
                "feed_id": "bbc_business",
                "title": "Markets steady as earnings beat forecasts",
                "link": "https://example.com/2",
                "summary": "No disruption.",
                "published_at": now - timedelta(days=1),
                "stress_score": 0.0,
                "matched_keywords": "",
                "ingested_at": now,
            },
        ]
    )
    insights = discover_news_insights(headlines)
    types = {i["type"] for i in insights}
    assert "news_theme" in types or "news_headline" in types
    assert all("interpretation" in i for i in insights)

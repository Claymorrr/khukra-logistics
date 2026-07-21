"""Tests for gazetteer NER entity extraction."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from khukra.disruption.news.enrich import enrich_headline_row
from khukra.disruption.news.entities import extract_entities
from khukra.disruption.news.service import _build_daily_entity_counts, ingest_news_feeds


def test_extract_suez_and_carrier_entities():
    text = "Maersk diverts ships from Suez Canal after Red Sea corridor attacks"
    result = extract_entities(text)
    assert "suez" in result.canals
    assert "maersk" in result.carriers
    assert result.has("canal", "suez")
    assert "canal:suez" in result.to_row_fields()["entities_json"]


def test_extract_ports_and_commodities():
    text = "Port of Los Angeles congestion delays container TEU moves and crude oil tankers"
    result = extract_entities(text)
    assert "port_of_los_angeles" in result.ports
    assert "containers" in result.commodities
    assert "crude_oil" in result.commodities


def test_enrich_attaches_entity_columns():
    row = enrich_headline_row(
        {
            "title": "Panama Canal draft cuts hit MSC sailings",
            "summary": "Drought restricts Panama transit for container ships.",
            "impact_score": 2.0,
            "stress_score": 2.0,
        }
    )
    assert "panama" in row["entity_canals"]
    assert "msc" in row["entity_carriers"]
    assert int(row["entity_count"]) >= 2
    assert "sentiment_compound" in row


def test_daily_entity_count_signals():
    headlines = pd.DataFrame(
        [
            {
                "title": "Suez Canal traffic disrupted",
                "summary": "Attacks near Bab el-Mandeb.",
                "published_at": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "entity_canals": "suez",
                "entity_ports": "",
                "entity_carriers": "",
                "entity_countries": "",
                "entity_commodities": "",
                "entity_count": 1,
            },
            {
                "title": "Port of Rotterdam backlog clears",
                "summary": "Hapag-Lloyd schedules normalize.",
                "published_at": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "entity_canals": "",
                "entity_ports": "port_of_rotterdam",
                "entity_carriers": "hapag_lloyd",
                "entity_countries": "",
                "entity_commodities": "",
                "entity_count": 2,
            },
            {
                "title": "Markets quiet",
                "summary": "No logistics entities.",
                "published_at": datetime(2024, 2, 2, tzinfo=timezone.utc),
                "entity_canals": "",
                "entity_ports": "",
                "entity_carriers": "",
                "entity_countries": "",
                "entity_commodities": "",
                "entity_count": 0,
            },
        ]
    )
    counts = _build_daily_entity_counts(headlines)
    suez = counts["news_suez_mentions"]
    assert len(suez) == 1
    assert float(suez.iloc[0]["value"]) == 1.0
    ports = counts["news_port_mentions"]
    assert float(ports.iloc[0]["value"]) == 1.0
    carriers = counts["news_carrier_mentions"]
    assert float(carriers.iloc[0]["value"]) == 1.0


def test_ingest_persists_entity_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("KHUKRA_DATA_ROOT", str(tmp_path))

    def fake_fetch(feed_id: str, url: str):
        from khukra.disruption.adapters.rss import RssEntry

        return [
            RssEntry(
                feed_id,
                "Suez Canal blockage forces Maersk reroute",
                f"https://example.com/{feed_id}-suez",
                datetime(2024, 3, 5, tzinfo=timezone.utc),
                "Container ships divert around Cape of Good Hope.",
            )
        ]

    monkeypatch.setattr("khukra.disruption.news.service.fetch_feed", fake_fetch)
    result = ingest_news_feeds()
    assert result["entity_headlines"] >= 1
    assert "news_suez_mentions" in result["entity_signal_ids"]

    from khukra.disruption.cache import load_signal
    from khukra.disruption.news.cache import load_headlines

    headlines = load_headlines()
    assert "entity_canals" in headlines.columns
    assert any("suez" in str(v) for v in headlines["entity_canals"].tolist())

    suez = load_signal("news_suez_mentions")
    assert suez is not None
    assert not suez.empty
    assert float(suez["value"].iloc[-1]) >= 1.0

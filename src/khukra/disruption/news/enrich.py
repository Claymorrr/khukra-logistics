"""NLP enrichment applied after objective judgment."""

from __future__ import annotations

from typing import Any

from khukra.disruption.news.entities import extract_entities
from khukra.disruption.news.sentiment import score_sentiment


def enrich_headline_row(row: dict[str, Any]) -> dict[str, Any]:
    """Attach VADER sentiment, entity tags, and tone-adjusted impact to a headline."""
    text = f"{row.get('title', '')}. {row.get('summary', '')}"
    sent = score_sentiment(text)
    entities = extract_entities(text)
    base_impact = float(row.get("impact_score", row.get("stress_score", 0.0)))
    # Negative tone amplifies disruption impact; positive tone dampens slightly.
    tone_multiplier = 1.0
    if sent.compound < -0.05:
        tone_multiplier = 1.0 + min(0.6, abs(sent.compound))
    elif sent.compound > 0.25:
        tone_multiplier = max(0.7, 1.0 - sent.compound * 0.3)

    adjusted = round(base_impact * tone_multiplier, 2)
    return {
        **row,
        "sentiment_compound": sent.compound,
        "sentiment_positive": sent.positive,
        "sentiment_negative": sent.negative,
        "sentiment_neutral": sent.neutral,
        "sentiment_is_negative": sent.is_negative,
        **entities.to_row_fields(),
        "impact_score": adjusted,
        "stress_score": adjusted,
    }

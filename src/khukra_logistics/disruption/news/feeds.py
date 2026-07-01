"""Curated logistics-native RSS feeds for disruption headlines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsFeed:
    feed_id: str
    label: str
    url: str
    category: str


# Logistics-heavy feeds first — higher retention vs broad business wires.
NEWS_FEEDS: tuple[NewsFeed, ...] = (
    NewsFeed("freightwaves", "FreightWaves", "https://www.freightwaves.com/feed", "shipping"),
    NewsFeed(
        "supplychain_dive",
        "Supply Chain Dive",
        "https://www.supplychaindive.com/feeds/news/",
        "logistics",
    ),
    NewsFeed("the_loadstar", "The Loadstar", "https://theloadstar.com/feed/", "logistics"),
    NewsFeed("gcaptain", "gCaptain", "https://gcaptain.com/feed/", "shipping"),
    NewsFeed("splash247", "Splash247", "https://splash247.com/feed/", "shipping"),
    NewsFeed(
        "maritime_exec",
        "Maritime Executive",
        "https://maritime-executive.com/rss",
        "shipping",
    ),
)

FEEDS_BY_ID: dict[str, NewsFeed] = {f.feed_id: f for f in NEWS_FEEDS}

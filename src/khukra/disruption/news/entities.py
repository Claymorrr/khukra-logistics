"""Gazetteer + rule NER for logistics disruption headlines.

CPU-only entity extraction for ports, canals, carriers, countries, and
commodities. Designed to run after judgment inside enrich.py — no spaCy/GPU.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Canonical entity id → aliases (matched case-insensitively with word boundaries).
# Keep aliases specific enough to avoid false positives in broad RSS feeds.

PORT_GAZETTEER: dict[str, tuple[str, ...]] = {
    "port_of_los_angeles": ("port of los angeles", "los angeles port", "l.a. port", "la port"),
    "port_of_long_beach": ("port of long beach", "long beach port"),
    "port_of_shanghai": ("port of shanghai", "shanghai port"),
    "port_of_singapore": ("port of singapore", "singapore port", "psa singapore"),
    "port_of_rotterdam": ("port of rotterdam", "rotterdam port"),
    "port_of_hamburg": ("port of hamburg", "hamburg port"),
    "port_of_antwerp": ("port of antwerp", "antwerp port", "antwerp-bruges"),
    "port_of_busan": ("port of busan", "busan port"),
    "port_of_ningbo": ("port of ningbo", "ningbo port", "ningbo-zhoushan"),
    "port_of_felixstowe": ("port of felixstowe", "felixstowe port"),
    "port_of_houston": ("port of houston", "houston port"),
    "port_of_new_york": ("port of new york", "new york/new jersey port", "ny/nj port"),
    "port_of_dubai": ("port of dubai", "jebel ali", "dp world jebel ali"),
    "port_of_qingdao": ("port of qingdao", "qingdao port"),
}

CANAL_GAZETTEER: dict[str, tuple[str, ...]] = {
    "suez": ("suez canal", "suez", "bab el-mandeb", "bab el mandeb", "red sea corridor"),
    "panama": ("panama canal", "panama", "gatun lake"),
    "kiel": ("kiel canal", "nord-ostsee-kanal"),
    "bosphorus": ("bosphorus", "bosporus", "turkish straits"),
}

CARRIER_GAZETTEER: dict[str, tuple[str, ...]] = {
    "maersk": ("maersk", "a.p. moller", "ap moller"),
    "msc": ("mediterranean shipping", "msc"),
    "cma_cgm": ("cma cgm", "cma-cgm"),
    "cosco": ("cosco", "china cosco"),
    "hapag_lloyd": ("hapag-lloyd", "hapag lloyd"),
    "evergreen": ("evergreen marine", "evergreen line", "evergreen"),
    "one": ("ocean network express", "one line"),
    "yang_ming": ("yang ming", "yangming"),
    "zim": ("zim integrated", "zim lines", "zim"),
    "hmm": ("hyundai merchant", "hmm"),
}

COUNTRY_GAZETTEER: dict[str, tuple[str, ...]] = {
    "china": ("china", "chinese", "prc"),
    "united_states": ("united states", "u.s.", "usa", "american"),
    "germany": ("germany", "german"),
    "united_kingdom": ("united kingdom", "u.k.", "britain", "british"),
    "iran": ("iran", "iranian"),
    "yemen": ("yemen", "houthi", "houthis"),
    "russia": ("russia", "russian"),
    "ukraine": ("ukraine", "ukrainian"),
    "israel": ("israel", "israeli"),
    "egypt": ("egypt", "egyptian"),
    "panama_country": ("panama", "panamanian"),
    "singapore": ("singapore", "singaporean"),
    "india": ("india", "indian"),
    "saudi_arabia": ("saudi arabia", "saudi"),
}

COMMODITY_GAZETTEER: dict[str, tuple[str, ...]] = {
    "crude_oil": ("crude oil", "brent", "wti", "oil tanker", "petroleum"),
    "lng": ("lng", "liquefied natural gas", "natural gas"),
    "containers": ("container", "containers", "teu", "boxship", "box ship"),
    "grain": ("grain", "wheat", "corn shipment", "soybean"),
    "coal": ("coal", "thermal coal"),
    "iron_ore": ("iron ore", "iron-ore"),
    "semiconductors": ("semiconductor", "chip", "chips", "foundry"),
    "fertilizer": ("fertilizer", "fertiliser", "urea", "ammonia"),
}

ENTITY_GAZETTEERS: dict[str, dict[str, tuple[str, ...]]] = {
    "port": PORT_GAZETTEER,
    "canal": CANAL_GAZETTEER,
    "carrier": CARRIER_GAZETTEER,
    "country": COUNTRY_GAZETTEER,
    "commodity": COMMODITY_GAZETTEER,
}

# Daily count signals for high-ROI corridor / chokepoint monitoring.
ENTITY_COUNT_SIGNALS: dict[str, tuple[str, str]] = {
    # signal_id → (entity_type, canonical_id)
    "news_suez_mentions": ("canal", "suez"),
    "news_panama_mentions": ("canal", "panama"),
    "news_carrier_mentions": ("carrier", "*"),
    "news_port_mentions": ("port", "*"),
}


@dataclass(frozen=True)
class ExtractedEntity:
    entity_type: str
    entity_id: str
    matched_alias: str


@dataclass(frozen=True)
class EntityExtraction:
    entities: tuple[ExtractedEntity, ...]
    ports: tuple[str, ...]
    canals: tuple[str, ...]
    carriers: tuple[str, ...]
    countries: tuple[str, ...]
    commodities: tuple[str, ...]

    def ids_for(self, entity_type: str) -> tuple[str, ...]:
        mapping = {
            "port": self.ports,
            "canal": self.canals,
            "carrier": self.carriers,
            "country": self.countries,
            "commodity": self.commodities,
        }
        return mapping.get(entity_type, ())

    def has(self, entity_type: str, entity_id: str) -> bool:
        return entity_id in self.ids_for(entity_type)

    def to_row_fields(self) -> dict[str, str]:
        """Serialize for parquet headline cache columns."""
        return {
            "entities_json": _serialize_entities(self.entities),
            "entity_ports": ",".join(self.ports),
            "entity_canals": ",".join(self.canals),
            "entity_carriers": ",".join(self.carriers),
            "entity_countries": ",".join(self.countries),
            "entity_commodities": ",".join(self.commodities),
            "entity_count": len(self.entities),
        }


def _alias_pattern(alias: str) -> re.Pattern[str]:
    # Allow optional periods in abbreviations already present in alias text.
    escaped = re.escape(alias).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)


_COMPILED: dict[str, list[tuple[str, str, re.Pattern[str]]]] = {}
for _etype, _gaz in ENTITY_GAZETTEERS.items():
    compiled: list[tuple[str, str, re.Pattern[str]]] = []
    for entity_id, aliases in _gaz.items():
        # Longer aliases first to prefer "suez canal" over bare "suez" when both match.
        for alias in sorted(aliases, key=len, reverse=True):
            compiled.append((entity_id, alias, _alias_pattern(alias)))
    _COMPILED[_etype] = compiled


def _serialize_entities(entities: Iterable[ExtractedEntity]) -> str:
    parts = [f"{e.entity_type}:{e.entity_id}" for e in entities]
    return "|".join(parts)


def extract_entities(text: str) -> EntityExtraction:
    """Tag logistics entities in headline/summary text via gazetteer rules."""
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return EntityExtraction((), (), (), (), (), ())

    found: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    for entity_type, patterns in _COMPILED.items():
        for entity_id, alias, pattern in patterns:
            key = (entity_type, entity_id)
            if key in seen:
                continue
            if pattern.search(clean):
                seen.add(key)
                found.append(
                    ExtractedEntity(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        matched_alias=alias,
                    )
                )

    by_type: dict[str, list[str]] = {
        "port": [],
        "canal": [],
        "carrier": [],
        "country": [],
        "commodity": [],
    }
    for ent in found:
        by_type[ent.entity_type].append(ent.entity_id)

    return EntityExtraction(
        entities=tuple(found),
        ports=tuple(by_type["port"]),
        canals=tuple(by_type["canal"]),
        carriers=tuple(by_type["carrier"]),
        countries=tuple(by_type["country"]),
        commodities=tuple(by_type["commodity"]),
    )

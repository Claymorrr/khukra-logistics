# Khukra Operations Board

**Last updated:** 2026-07-21

Single tracker for suggestions, decisions, and work across **Khukra Finance**, **Khukra Physics**, and **Khukra**.  
The chat is not the source of truth — **this file and the GitHub Project are**.

| Resource | Location |
|----------|----------|
| Machine-readable items | [`board.manifest.json`](../board.manifest.json) |
| Sync to GitHub | `.\scripts\sync-operations-board.ps1` |
| GitHub Project | **Khukra Operations** — [open board](https://github.com/users/Claymorrr/projects/4) |

---

## North star

**Forecast precision** — measured daily on the hybrid panel (macro + market + news). Discover, explore, and NLP exist to raise the precision score.

---

## Todo

| ID | Item | Repo |
|----|------|------|
| ops-016 | Event typing (strike, closure, cyber, …) | logistics |

---

## In Progress

| ID | Item | Repo |
|----|------|------|
| ops-013 | Maintain Operations board as canonical tracker | ops |

---

## Backlog — NLP roadmap (Logistics)

High-ROI order: **ops-016 → ops-017 → ops-018**, then Phase 3–4.

| ID | Phase | Item | Repo |
|----|-------|------|------|
| ops-016 | 2 | Event typing (strike, closure, cyber, …) | logistics |
| ops-017 | 2 | Headline dedup (MinHash / embeddings) | logistics |
| ops-018 | 2 | Aspect / logistics-targeted sentiment | logistics |
| ops-019 | 3 | FinBERT or zero-shot relevance augment | logistics |
| ops-020 | 3 | Embedding theme clustering + novelty | logistics |
| ops-021 | 4 | LLM event extraction + RAG analyst (optional) | logistics |
| ops-022 | — | NLP validation via lead-lag vs macro signals | logistics |

**Phase 1 (done):** ops-014 — RSS judgment → VADER → `news_stress` + `news_sentiment`.  
**Phase 2 (partial):** ops-015 — gazetteer NER + entity-count signals.

---

## Backlog — other

| ID | Item | Repo |
|----|------|------|
| ops-004 | Macro regime feeds (FRED/ECB + VSTOXX) | khukra |
| ops-005 | Corporate actions for .DE backtests | khukra |
| ops-006 | Expand beyond DAX 32 (MDAX / Euro Stoxx) | khukra |
| ops-010 | Port congestion + geopolitical event feeds | logistics |
| ops-011 | Calibrate sim model from composite risk panel | logistics |

---

## Done (recent)

| ID | Item | Repo |
|----|------|------|
| ops-001 | Stabilize local dev (startup sync, DuckDB locks) | khukra |
| ops-002 | DAX data: Stooq → Yahoo Finance | khukra |
| ops-003 | Full-universe refresh + 15y history | khukra |
| ops-007 | Scaffold khukra repo | logistics |
| ops-008 | Disruption ingest + statistical discovery | logistics |
| ops-009 | Discovery cockpit UI | logistics |
| ops-012 | Push repos to GitHub (finance, physics, logistics) | logistics |
| ops-014 | NLP Phase 1 — judgment + VADER + news signals | logistics |
| ops-023 | Daily forecast precision scorecard (hybrid) | logistics |
| ops-024 | GSCPI + logistics RSS + shipping basket | logistics |
| ops-025 | Inverse-variance hybrid composite + news weight tune | logistics |
| ops-015 | NER + entity extraction (gazetteer) + entity-count signals | logistics |

---

## Backlog — forecast & hybrid data

| ID | Item | Repo |
|----|------|------|
| _empty — next tier: event typing (ops-016+) and GSCPI vintage tracking_ | | |

---

## How to add items

1. Add an entry to `board.manifest.json` (`status`: Backlog | Todo | In Progress | Done).
2. Run `.\scripts\sync-operations-board.ps1` to create/update GitHub issues and the project board.
3. Move cards in GitHub Project as work progresses.

## Columns (GitHub Project)

`Backlog` → `Todo` → `In Progress` → `Done` (or `Won't do`)

# Khukra Logistics

**Global disruption forecast and statistical risk analysis** — ingest public macro/shipping/news signals, discover Bayesian insights, and explore composite disruption risk.

Sibling product to [Khukra](https://github.com/Claymorrr/khukra) (finance quant R&D).

## Quick start (clone → run)

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ (includes `npm`) |
| Git | any recent |

Network access is required for first data ingest (FRED, Yahoo, RSS).

### Windows (recommended)

```powershell
git clone <your-repo-url> khukra-logistics
cd khukra-logistics

# One-time: venv + dependencies (+ optional demo data)
.\scripts\setup.ps1
# Or with pre-cached signals: .\scripts\setup.ps1 -SeedData

# Start API + cockpit UI (auto-seeds on first run if cache is empty)
.\scripts\start-dev.ps1
```

- **Cockpit:** http://localhost:3020  
- **API docs:** http://127.0.0.1:8010/docs  

### Mac / Linux

```bash
git clone <your-repo-url> khukra-logistics
cd khukra-logistics
chmod +x scripts/*.sh

./scripts/setup.sh              # one-time
./scripts/setup.sh --seed-data  # optional: pre-load 5y history
./scripts/start-dev.sh
```

### Verify install

```powershell
.\scripts\smoke-test.ps1      # Windows
./scripts/smoke-test.sh       # Mac/Linux
```

Or: `make test`

## What gets created locally

| Path | Purpose |
|------|---------|
| `.venv/` | Python env + `khukra-logistics` CLI |
| `frontend/node_modules/` | Next.js deps |
| `frontend/.env.local` | API URL (auto-written by start-dev) |
| `data/disruption_cache/` | Cached FRED/Yahoo signal parquet |
| `data/news_cache/` | Judged RSS headlines |

`data/` is gitignored — each clone builds its own cache on first **Refresh** or auto-seed.

## Configuration

Copy `.env.example` to `.env` if you need custom ports:

```
KHUKRA_LOGISTICS_API_PORT=8010
KHUKRA_LOGISTICS_UI_PORT=3020
```

## Primary workflow

```
catalog → refresh (hybrid ingest) → evaluate (daily precision) → forecast → discover/explore (diagnose)
         ↘ refresh-news (RSS + NLP) — also runs daily evaluation
```

| Step | CLI | UI |
|------|-----|-----|
| Ingest macro + news | `khukra-logistics refresh --years 10` | Refresh |
| **Daily precision** | `khukra-logistics evaluate` | Forecast precision card |
| Forecast | `khukra-logistics forecast --horizon 30` | Forecast |
| Diagnose panel | `khukra-logistics discover` / `explore` | Discover / Explore |

### Data sources

- **FRED** (no API key): VIX, WTI oil, USD index, HY OAS  
- **Yahoo Finance**: shipping proxy (ZIM), EUR/USD  
- **RSS** (judgment + VADER NLP): BBC, FreightWaves, Supply Chain Dive, Reuters, Al Jazeera  

### Signals (8)

`vix`, `oil_wti`, `usd_trade_weighted`, `hy_oas`, `gscpi`, `shipping_basket`, `eurusd`, `news_stress`, `news_sentiment`

## API endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Version + capabilities |
| `GET /api/disruption/catalog` | Signal catalog |
| `GET /api/disruption/status` | Cache coverage |
| `POST /api/disruption/refresh` | Ingest macro signals |
| `POST /api/disruption/refresh-news` | RSS poll + NLP |
| `POST /api/disruption/discover` | Bayesian insights |
| `POST /api/disruption/explore` | 7 advanced methods |
| `POST /api/disruption/forecast` | Composite forecast + evaluation |
| `POST /api/disruption/evaluate` | Daily precision scorecard |
| `GET /api/disruption/evaluation` | Evaluation history |
| `POST /api/disruption/panel` | Chart panel data |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Connection failed` / 502 | API not running → `.\scripts\start-dev.ps1` |
| `/explore` 404 or 1 method | Stale API process → restart `start-dev` |
| Empty charts | Click **Refresh**, wait ~1 min for FRED/Yahoo |
| `datetime64` merge error | Restart API (runs `repair_signal_dates`) |
| Advanced shows 1/7 methods | Click **Explore** again after **Refresh** (needs macro cache) |

## Simulation models (secondary)

Synthetic stress scenarios: `disruption_risk_forecast`, `defect_rate_forecast`, `recovery_time_forecast`

```powershell
khukra-logistics run disruption_risk_forecast
```

See [`docs/vision.md`](docs/vision.md) for product direction.

## Development

```powershell
pip install -e ".[dev]"
pytest tests/
cd frontend && npm run typecheck
```

## Sharing the repo

To let someone run from a fresh clone:

1. Commit **source only** (`.gitignore` excludes `data/`, `.venv/`, `node_modules/`, `.env.local`)  
2. Point them to **Quick start** above  
3. Optional: `.\scripts\setup.ps1 -SeedData` for a faster first cockpit load  

For containerized deploy later, add `Dockerfile` + `docker-compose.yml` — not included yet.

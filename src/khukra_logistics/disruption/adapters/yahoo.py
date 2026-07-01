"""Yahoo Finance daily series adapter."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?period1={period1}&period2={period2}&interval=1d"
)

SHIPPING_BASKET_TICKERS: tuple[str, ...] = ("ZIM", "HLAG.DE", "MAERSK-B.CO")


def fetch_daily_series(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    end = end or date.today()
    start = start or (end - timedelta(days=365 * 5))
    period1 = int(datetime.combine(start, datetime.min.time()).timestamp())
    period2 = int(datetime.combine(end, datetime.max.time()).timestamp())
    url = YAHOO_CHART_URL.format(symbol=quote(ticker), period1=period1, period2=period2)
    req = Request(url, headers={"User-Agent": "KhukraLogistics/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to fetch {ticker} from Yahoo: {exc}") from exc

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["date", "value"])

    block = result[0]
    timestamps = block.get("timestamp") or []
    quotes = (block.get("indicators") or {}).get("quote") or [{}]
    bar = quotes[0] if quotes else {}
    if not timestamps:
        return pd.DataFrame(columns=["date", "value"])

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None).normalize(),
            "value": bar.get("close"),
        }
    )
    return df.dropna(subset=["date", "value"]).sort_values("date").reset_index(drop=True)


def fetch_shipping_basket(
    tickers: tuple[str, ...] = SHIPPING_BASKET_TICKERS,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Equal-weight average close across liner shipping equities."""
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        series = fetch_daily_series(ticker, start, end)
        if series.empty:
            continue
        frames.append(series.rename(columns={"value": ticker}).set_index("date"))

    if not frames:
        return pd.DataFrame(columns=["date", "value"])

    panel = pd.concat(frames, axis=1).sort_index()
    basket = panel.mean(axis=1, skipna=True).dropna()
    return pd.DataFrame({"date": basket.index, "value": basket.values}).reset_index(drop=True)

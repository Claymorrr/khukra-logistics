"""NY Fed Global Supply Chain Pressure Index (monthly, no API key)."""

from __future__ import annotations

from datetime import date
from io import StringIO
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd

GSCPI_CSV_URL = (
    "https://www.newyorkfed.org/medialibrary/research/interactives/data/gscpi/"
    "gscpi_interactive_data.csv"
)


def fetch_monthly_series(
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Return monthly GSCPI levels (latest vintage column)."""
    req = Request(GSCPI_CSV_URL, headers={"User-Agent": "KhukraLogistics/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch GSCPI: {exc}") from exc

    if raw.lstrip().startswith("<"):
        raise RuntimeError("GSCPI endpoint returned HTML instead of CSV")

    wide = pd.read_csv(StringIO(raw))
    if wide.empty or "Date" not in wide.columns:
        return pd.DataFrame(columns=["date", "value"])

    value_col = wide.columns[-1]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(wide["Date"], format="%d-%b-%Y", errors="coerce"),
            "value": pd.to_numeric(wide[value_col], errors="coerce"),
        }
    )
    df = df.dropna(subset=["date", "value"]).sort_values("date")
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def expand_to_business_days(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill monthly GSCPI onto business-day calendar for panel merge."""
    if df.empty:
        return df
    work = df.sort_values("date").drop_duplicates("date", keep="last")
    start = work["date"].min()
    end = work["date"].max()
    bdays = pd.bdate_range(start, end)
    filled = (
        work.set_index("date")
        .reindex(bdays)
        .ffill()
        .reset_index()
        .rename(columns={"index": "date"})
    )
    return filled.dropna(subset=["value"]).reset_index(drop=True)

"""
src/fundamentals.py — Fundamental factor extraction from yfinance.

Fetches valuation ratios, profitability metrics, and growth indicators for
each ticker via `yfinance.Ticker(t).info`. Results are cached to disk for
7 days (`data/fundamentals_cache.json`) to avoid rate-limiting Yahoo.

Column names are the stable contract consumed by src/scoring.py — do not
rename `pe_forward`, `roe`, `debt_equity`, `gross_margin`, `revenue_growth`
or `operating_margin` without updating the scoring layer.
"""

from __future__ import annotations
import json
import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

CACHE_PATH = Path("data/fundamentals_cache.json")
CACHE_MAX_AGE_DAYS = 7

# yfinance .info key -> our column name
_FIELD_MAP: Dict[str, str] = {
    "forwardPE":         "pe_forward",
    "trailingPE":        "pe_trailing",
    "priceToSalesTrailing12Months": "ps_ratio",
    "priceToBook":       "price_to_book",
    "enterpriseToEbitda": "ev_ebitda",
    "returnOnEquity":    "roe",
    "returnOnAssets":    "roa",
    "debtToEquity":      "debt_equity",
    "grossMargins":      "gross_margin",
    "operatingMargins":  "operating_margin",
    "profitMargins":     "profit_margin",
    "revenueGrowth":     "revenue_growth",
    "pegRatio":          "peg_ratio",
    "dividendYield":     "dividend_yield",
    "marketCap":         "market_cap",
    "ebitda":            "ebitda",
    "beta":              "beta",
}
_COLUMNS: List[str] = list(_FIELD_MAP.values())


def _load_cache() -> dict | None:
    """Return the cache dict if it exists and parses, else None."""
    if not CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        datetime.date.fromisoformat(cache["date"])  # validate shape
        assert isinstance(cache["data"], dict)
        return cache
    except (json.JSONDecodeError, KeyError, ValueError, AssertionError):
        print(f"[fundamentals] cache at {CACHE_PATH} unreadable — refetching.")
        return None


def get_fundamentals(tickers: List[str]) -> pd.DataFrame:
    """
    Fetch fundamental ratios for a list of tickers.
    Returns a DataFrame indexed by ticker with columns from _COLUMNS
    (pe_forward, pe_trailing, ps_ratio, price_to_book, ev_ebitda, roe, roa,
    debt_equity, gross_margin, operating_margin, profit_margin,
    revenue_growth, peg_ratio, dividend_yield, market_cap, ebitda, beta).

    A 7-day disk cache is used; it is honoured only when it is fresh AND
    covers every requested ticker. Individual ticker failures are skipped
    (row of NaNs) so one bad symbol never sinks the whole fetch.
    """
    cache = _load_cache()
    if cache is not None:
        age = (datetime.date.today()
               - datetime.date.fromisoformat(cache["date"])).days
        if age < CACHE_MAX_AGE_DAYS and set(tickers).issubset(cache["data"]):
            return (pd.DataFrame.from_dict(cache["data"], orient="index")
                    .reindex(index=tickers, columns=_COLUMNS))

    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError(f"yfinance is required for fundamentals: {e}") from e

    result: Dict[str, Dict[str, float | None]] = dict(cache["data"]) if cache else {}
    failed: List[str] = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
            result[ticker] = {col: info.get(key)
                              for key, col in _FIELD_MAP.items()}
        except Exception as e:
            failed.append(ticker)
            print(f"[fundamentals] {ticker} failed ({e}) — skipping.")
            result.setdefault(ticker, {col: None for col in _COLUMNS})

    if failed:
        print(f"[fundamentals] {len(failed)} of {len(tickers)} tickers "
              f"failed: {', '.join(failed[:10])}"
              f"{' …' if len(failed) > 10 else ''}")

    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"date": str(datetime.date.today()), "data": result},
                       indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        print(f"[fundamentals] could not write cache ({e}) — continuing.")

    return (pd.DataFrame.from_dict(result, orient="index")
            .reindex(index=tickers, columns=_COLUMNS))

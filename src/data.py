"""
src/data.py — free price data.

Real data comes from yfinance (Yahoo Finance), cached locally to parquet so
you don't re-download on every run.

There is also an EXPLICIT synthetic mode (`source="synthetic"`), used only for
offline testing / CI. It is never used silently: if a live fetch fails you get
an error, not fake data. (Silently substituting fake data is exactly the bug
that made the previous engine's results meaningless.)
"""

from __future__ import annotations
import os
from pathlib import Path

import numpy as np
import pandas as pd

from config import CFG


# ──────────────────────────────────────────────────────────────────────────
# Real data via yfinance (cached)
# ──────────────────────────────────────────────────────────────────────────
def _download_yf(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf  # imported lazily so the package imports without it
    raw = yf.download(
        tickers, start=start, end=end,
        auto_adjust=True, progress=False, group_by="column",
    )
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:                       # single ticker
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})
    return prices


def load_prices(
    tickers: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    source: str = "yfinance",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Return a wide DataFrame of adjusted closes: index=Date, columns=tickers
    (universe + benchmark). `source` is "yfinance" (default) or "synthetic".
    """
    tickers = tickers or (CFG.universe.tickers + [CFG.universe.benchmark_ticker])
    start = start or CFG.universe.start_date
    end = end or CFG.universe.end_date

    if source == "synthetic":
        return _synthetic_prices(tickers, start, end)

    cache = Path(CFG.paths.price_cache)
    if use_cache and cache.exists():
        cached = pd.read_parquet(cache)
        if set(tickers).issubset(cached.columns) and \
           cached.index.min() <= pd.Timestamp(start) and \
           cached.index.max() >= pd.Timestamp(end) - pd.Timedelta(days=7):
            print(f"[data] using cached prices ({cache})")
            return cached.loc[start:end, tickers].ffill().dropna(how="all")

    print(f"[data] downloading {len(tickers)} tickers from yfinance "
          f"({start} -> {end}) ...")
    prices = _download_yf(tickers, start, end).ffill().dropna(how="all")
    if prices.empty:
        raise RuntimeError(
            "yfinance returned no data. Check your internet connection / tickers. "
            "For offline testing use source='synthetic'."
        )
    if use_cache:
        os.makedirs(cache.parent, exist_ok=True)
        prices.to_parquet(cache)
        print(f"[data] cached prices -> {cache}")
    return prices


def split_universe_benchmark(prices: pd.DataFrame):
    """Split a wide price frame into (universe_prices, benchmark_series)."""
    bench = CFG.universe.benchmark_ticker
    benchmark = prices[bench] if bench in prices.columns else None
    cols = [t for t in CFG.universe.tickers if t in prices.columns]
    return prices[cols], benchmark


# ──────────────────────────────────────────────────────────────────────────
# Synthetic prices (explicit, for offline tests only)
# ──────────────────────────────────────────────────────────────────────────
def _synthetic_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Deterministic GBM with a common market factor and two regime shifts."""
    rng = np.random.default_rng(CFG.backtest.random_seed)
    days = pd.bdate_range(start, end)
    n = len(days)
    mkt = np.zeros(n)
    drift = np.where(np.arange(n) < n * 0.35, 0.0005,
            np.where(np.arange(n) < n * 0.45, -0.0014, 0.0006))
    for i in range(1, n):
        mkt[i] = mkt[i - 1] + drift[i] + rng.normal(0, 0.009)
    cols = {}
    for t in tickers:
        beta = rng.uniform(0.6, 1.4)
        idio = np.cumsum(rng.normal(0, 0.011, n))
        cols[t] = np.exp(np.log(rng.uniform(30, 300)) + beta * mkt + idio)
    print(f"[data] SYNTHETIC prices generated ({n} days, {len(tickers)} tickers) "
          f"— for testing only, not real markets.")
    return pd.DataFrame(cols, index=days)

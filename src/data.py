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
def _download_yf(tickers: list[str], start: str, end: str | None) -> pd.DataFrame:
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


def _env_key(name: str) -> str | None:
    """Read a key from the environment, falling back to the .env file.
    Placeholder values ("your_...") count as absent."""
    val = os.environ.get(name, "").strip()
    if not val:
        env = Path(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith(name):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return None if (not val or val.startswith("your_")) else val


# ──────────────────────────────────────────────────────────────────────────
# Twelve Data fallback (free tier: 800 credits/day, 8 requests/min;
# one symbol = one credit regardless of date range)
# ──────────────────────────────────────────────────────────────────────────
_TD_URL = "https://api.twelvedata.com/time_series"


def _download_twelvedata(tickers: list[str], start: str, end: str | None,
                         api_key: str, batch_size: int = 8,
                         pause: float = 61.0) -> pd.DataFrame:
    """Daily closes from Twelve Data. Batches of 8 with a pause between
    them to respect the free-tier 8-credits/min limit, so a full universe
    takes ~1 min per 8 tickers. Best used for tail top-ups or as a
    fallback, not routine full downloads."""
    import time
    import requests

    frames: dict[str, pd.Series] = {}
    total = len(tickers)
    for i in range(0, total, batch_size):
        batch = list(tickers[i:i + batch_size])
        params = {
            "symbol": ",".join(batch),
            "interval": "1day",
            "start_date": start,
            "outputsize": "5000",
            "apikey": api_key,
        }
        if end:
            params["end_date"] = end
        data = requests.get(_TD_URL, params=params, timeout=30).json()
        if len(batch) == 1:
            data = {batch[0]: data}
        for t in batch:
            node = data.get(t) or {}
            vals = node.get("values")
            if not vals:
                msg = node.get("message") or (data.get("message")
                                              if isinstance(data, dict) else None)
                print(f"[data] twelvedata: no data for {t}"
                      + (f" ({msg})" if msg else ""))
                continue
            frames[t] = pd.Series(
                {pd.Timestamp(v["datetime"]): float(v["close"]) for v in vals}
            ).sort_index()
        if i + batch_size < total:
            print(f"[data] twelvedata: {min(i + batch_size, total)}/{total} "
                  f"tickers fetched, pausing {int(pause)}s (free-tier limit)...")
            time.sleep(pause)
    return pd.DataFrame(frames)


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
    try:
        prices = _download_yf(tickers, start, end).ffill().dropna(how="all")
    except Exception as e:
        print(f"[data] yfinance failed: {e}")
        prices = pd.DataFrame()
    if prices.empty:
        td_key = _env_key("TWELVEDATA_API_KEY")
        if td_key:
            print("[data] falling back to Twelve Data (free tier is paced: "
                  "~1 min per 8 tickers)...")
            prices = (_download_twelvedata(tickers, start, end, td_key)
                      .ffill().dropna(how="all"))
    if prices.empty:
        raise RuntimeError(
            "No price data: yfinance failed and no Twelve Data fallback was "
            "available (set TWELVEDATA_API_KEY in .env for a free backup "
            "source). For offline testing use source='synthetic'."
        )
    if use_cache:
        os.makedirs(cache.parent, exist_ok=True)
        prices.to_parquet(cache)
        print(f"[data] cached prices -> {cache}")
    return prices


def refresh_price_cache(max_age_days: int = 3) -> bool:
    """
    Bring data/price_cache.parquet up to today (tail-only top-up).
    yfinance first; Twelve Data fallback if a TWELVEDATA_API_KEY is set.
    Meant for the scheduled daily job, so the dashboard/API always find a
    fresh cache. Returns True when the cache is fresh afterwards.
    """
    cache = Path(CFG.paths.price_cache)
    if not cache.exists():
        load_prices()          # full build, with its own TD fallback
        return True
    px = pd.read_parquet(cache).ffill().dropna(how="all")
    age = (pd.Timestamp.today().normalize() - px.index.max()).days
    if age <= max_age_days:
        print(f"[data] price cache fresh (through {px.index.max().date()}).")
        return True

    cols = px.columns.tolist()
    start = (px.index.max() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    tail = pd.DataFrame()
    try:
        tail = _download_yf(cols, start, None)
    except Exception as e:
        print(f"[data] yfinance tail fetch failed: {e}")
    if tail.dropna(how="all").empty:
        td_key = _env_key("TWELVEDATA_API_KEY")
        if td_key:
            print("[data] topping up price cache via Twelve Data...")
            tail = _download_twelvedata(cols, start, None, td_key)
    tail = tail.reindex(columns=px.columns).dropna(how="all")
    if tail.empty:
        print("[data] could not refresh price cache (all sources failed); "
              "keeping existing cache.")
        return False
    merged = pd.concat([px.loc[:tail.index.min() - pd.Timedelta(days=1)], tail])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index().ffill()
    merged.to_parquet(cache)
    print(f"[data] price cache refreshed through {merged.index.max().date()}.")
    return True


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

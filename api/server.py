"""
FastAPI backend for the Next.js frontend.

Wraps the existing pipeline (src/momentum, src/scoring, src/fundamentals)
and exposes JSON endpoints. Read-only. Run from the repo root:

    uvicorn api.server:app --reload --port 8000

Optional: set T212_API_KEY (Trading212 Settings > API (Beta)) to enable
/api/portfolio. Read-only scopes are enough; never grant order permissions.
"""
from __future__ import annotations

import base64
import math
import os
import time
from pathlib import Path

# Load .env before reading any keys (T212_*, ALPHAVANTAGE_*, …)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import CFG, SECTORS, TICKER_SLEEVE
from src import momentum
from src.data import load_prices
from src.scoring import compute_ai_score

try:
    from src.fundamentals import get_fundamentals
    _HAS_FUND = True
except Exception:
    _HAS_FUND = False

app = FastAPI(title="Momentum+Sentiment API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_SPARK = 252         # ~1 year of dailies; frontend slices per timeframe
_TTL = 15 * 60       # screener cache TTL (seconds)
_cache: dict = {}


def _clean(v):
    """JSON-safe scalar (numpy -> native, NaN/inf -> None)."""
    if v is None:
        return None
    if isinstance(v, np.generic):   # np.int64/float64/bool_ break json encoding
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _load_px() -> pd.DataFrame:
    """
    Load prices, keeping them CURRENT without ever fabricating data:
    1. If the cache is fresh (<=3 calendar days old) use it as-is.
    2. If stale, fetch ONLY the missing tail from yfinance (a few weeks —
       tiny request, rarely rate-limited, unlike a full 11-year re-download),
       append it and rewrite the cache.
    3. If that fails, fall back to load_prices() (full fetch), then the raw
       cache. Never synthetic (see CLAUDE.md).
    """
    cache_path = Path(CFG.paths.price_cache)
    cached = None
    if cache_path.exists():
        cached = pd.read_parquet(cache_path).ffill().dropna(how="all")
        age_days = (pd.Timestamp.today().normalize() - cached.index.max()).days
        if age_days <= 3:
            return cached
        # Incremental tail update
        try:
            import yfinance as yf
            start = (cached.index.max() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
            raw = yf.download(
                cached.columns.tolist(), start=start,
                auto_adjust=True, progress=False, group_by="column",
            )
            tail = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
            tail = tail.reindex(columns=cached.columns)
            if not tail.dropna(how="all").empty:
                px = pd.concat([cached.loc[:tail.index.min() - pd.Timedelta(days=1)], tail])
                px = px[~px.index.duplicated(keep="last")].sort_index().ffill()
                px.to_parquet(cache_path)
                return px
        except Exception:
            pass
    try:
        return load_prices(use_cache=True)
    except Exception:
        if cached is not None:
            return cached
        raise HTTPException(503, "No price data: network down and no cache.")


def _build_screener() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replicates the dashboard SCREENER tab table build."""
    px = _load_px()
    bench = CFG.universe.benchmark_ticker
    if bench in px.columns:
        px = px.drop(columns=[bench])
    panels = momentum.build_panels(px)
    rows = []
    for t in px.columns:
        rows.append({
            "ticker": t,
            "sector": SECTORS.get(t, "Other"),
            "sleeve": TICKER_SLEEVE.get(t, "core"),
            "last_price": float(px[t].iloc[-1]),
            "mom_12m": float(panels["tsm"][t].iloc[-1]) if t in panels["tsm"].columns else None,
            "ratio_52w": float(panels["ratio52"][t].iloc[-1]) if t in panels["ratio52"].columns else None,
            "rsi": float(panels["rsi"][t].iloc[-1]) if t in panels["rsi"].columns else None,
            "above_long_ma": int(px[t].iloc[-1] > panels["ma_long"][t].iloc[-1]) if t in panels["ma_long"].columns else 0,
            "volatility": float(panels["vol"][t].iloc[-1]) if t in panels["vol"].columns else None,
            "price_trend": [round(float(v), 4) for v in px[t].tail(_SPARK).dropna()],
        })
    df = pd.DataFrame(rows).set_index("ticker")
    if "macd_hist" in panels:
        df["macd_hist"] = panels["macd_hist"].iloc[-1].reindex(df.index)

    # Latest sentiment snapshot from history log
    try:
        p = Path(CFG.paths.sentiment_log)
        if p.exists():
            hist = pd.read_csv(p, parse_dates=["date"])
            latest = hist.loc[hist.date == hist.date.max()]
            df["sentiment_score"] = (
                latest.groupby("ticker")["score"].mean().reindex(df.index).fillna(0)
            )
    except Exception:
        pass

    if _HAS_FUND:
        try:
            df = df.join(get_fundamentals(df.index.tolist()), how="left")
        except Exception:
            pass

    df = compute_ai_score(df)
    return df, px


def _screener_df() -> tuple[pd.DataFrame, str]:
    now = time.time()
    if "df" not in _cache or now - _cache.get("ts", 0) > _TTL:
        df, px = _build_screener()
        _cache.update(df=df, px=px, ts=now,
                      as_of=str(px.index[-1].date()))
    return _cache["df"], _cache["as_of"]


@app.get("/api/screener")
def screener():
    df, as_of = _screener_df()
    records = []
    for t, row in df.iterrows():
        rec = {k: _clean(v) for k, v in row.items() if k != "price_trend"}
        rec["ticker"] = t
        rec["price_trend"] = row.get("price_trend") or []
        records.append(rec)
    return {"as_of": as_of, "count": len(records), "stocks": records}


@app.get("/api/stock/{ticker}")
def stock(ticker: str):
    df, as_of = _screener_df()
    t = ticker.upper()
    if t not in df.index:
        raise HTTPException(404, f"{t} not in universe")
    px = _cache["px"]
    row = {k: _clean(v) for k, v in df.loc[t].items() if k != "price_trend"}
    series = px[t].dropna().tail(504)  # ~2y
    row.update(
        ticker=t, as_of=as_of,
        prices={"dates": [str(d.date()) for d in series.index],
                "close": [round(float(v), 4) for v in series]},
    )
    return row


@app.get("/api/portfolio")
def portfolio():
    """Trading212 open positions joined against AI Scores (read-only)."""
    key = os.environ.get("T212_API_KEY", "").strip()
    secret = os.environ.get("T212_API_SECRET", "").strip()
    placeholder = key.startswith("your_") or secret.startswith("your_")
    if not key or placeholder:
        return {"connected": False,
                "message": "Set T212_API_KEY and T212_API_SECRET in .env "
                           "to connect Trading212."}
    env = os.environ.get("T212_ENV", "live").strip().lower()
    host = "demo" if env == "demo" else "live"
    if secret:
        # Current beta auth: Basic base64(key:secret)
        token = base64.b64encode(f"{key}:{secret}".encode()).decode()
        auth = f"Basic {token}"
    else:
        auth = key  # legacy single-key header
    import urllib.request, json
    req = urllib.request.Request(
        f"https://{host}.trading212.com/api/v0/equity/positions",
        headers={"Authorization": auth},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            positions = json.load(r)
    except Exception as e:
        raise HTTPException(502, f"Trading212 request failed: {e}")

    df, as_of = _screener_df()
    out = []
    for p in positions:
        raw = p.get("ticker", "")          # e.g. "AAPL_US_EQ"
        sym = raw.split("_")[0]
        score_row = df.loc[sym] if sym in df.index else None
        out.append({
            "ticker": sym, "t212_ticker": raw,
            "quantity": _clean(p.get("quantity")),
            "average_price": _clean(p.get("averagePrice")),
            "current_price": _clean(p.get("currentPrice")),
            "ppl": _clean(p.get("ppl")),
            "ai_score": _clean(score_row["ai_score"]) if score_row is not None else None,
            "action": score_row["action"] if score_row is not None else None,
            "in_universe": score_row is not None,
        })
    return {"connected": True, "as_of": as_of, "positions": out}


@app.get("/api/meta")
def meta():
    df, as_of = _screener_df()
    return {
        "as_of": as_of,
        "sleeves": sorted(df["sleeve"].unique().tolist()),
        "sectors": sorted(df["sector"].unique().tolist()),
        "buy": int((df["action"] == "BUY").sum()),
        "hold": int((df["action"] == "HOLD").sum()),
        "avoid": int((df["action"] == "AVOID").sum()),
        "avg_score": round(float(df["ai_score"].mean()), 2),
    }

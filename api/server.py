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
import re
import threading
import time
from pathlib import Path

# Load .env before reading any keys (T212_*, ALPHAVANTAGE_*, OPENAI_*, …).
# override=True so .env is always authoritative — otherwise a stray
# already-set shell env var (e.g. a leftover $env:T212_ENV from an earlier
# session) silently wins over what .env says, since load_dotenv() defaults
# to never overwriting existing os.environ entries.
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import CFG, SECTORS, TICKER_SLEEVE, TICKER_NAMES
from src import momentum, signals
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
    allow_methods=["GET", "POST"],
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
            "name": TICKER_NAMES.get(t, t),
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
    series = px[t].dropna()  # full available history (cache back to 2015 / IPO)
    row.update(
        ticker=t, as_of=as_of,
        prices={"dates": [str(d.date()) for d in series.index],
                "close": [round(float(v), 4) for v in series]},
    )
    return row


# Trading212 rate-limits /equity/positions to 1 request/second. The dev
# frontend fires the fetch twice on mount (React StrictMode), so the second
# call gets rate-limited and 502s. A short cache + one retry absorbs both.
_T212_TTL = 20
_t212_cache: dict = {}


def _fetch_t212_positions(host: str, auth: str) -> list:
    now = time.time()
    cached = _t212_cache.get("positions")
    if cached is not None and now - _t212_cache.get("ts", 0) < _T212_TTL:
        return cached
    import urllib.request, json
    req = urllib.request.Request(
        f"https://{host}.trading212.com/api/v0/equity/positions",
        headers={"Authorization": auth},
    )
    last_err = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                positions = json.load(r)
            _t212_cache.update(positions=positions, ts=time.time())
            return positions
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(1.2)   # respect the 1 req/sec limit, then retry once
    if cached is not None:        # live call failed but we have a recent copy
        return cached
    raise HTTPException(502, f"Trading212 request failed: {last_err}")


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

    positions = _fetch_t212_positions(host, auth)

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


_T212_ORDERS_TTL = 60
_t212_orders_cache: dict = {}


def _fetch_t212_order_history(host: str, auth: str, max_pages: int = 5) -> list:
    """Paginates GET /equity/history/orders (cursor-based). Read-only —
    reports fills, never places orders. Respects the ~1 req/sec T212 rate
    limit with a short sleep between pages."""
    now = time.time()
    cached = _t212_orders_cache.get("items")
    if cached is not None and now - _t212_orders_cache.get("ts", 0) < _T212_ORDERS_TTL:
        return cached

    import urllib.request, json, urllib.parse
    items: list = []
    cursor = None
    for page in range(max_pages):
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        url = f"https://{host}.trading212.com/api/v0/equity/history/orders?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": auth})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                page_data = json.load(r)
        except Exception as e:
            if not items:
                raise HTTPException(502, f"Trading212 order history request failed: {e}")
            break
        items.extend(page_data.get("items", []))
        next_path = page_data.get("nextPagePath")
        if not next_path:
            break
        parsed = urllib.parse.urlparse(next_path)
        cursor = urllib.parse.parse_qs(parsed.query).get("cursor", [None])[0]
        if not cursor:
            break
        time.sleep(1.1)  # respect 1 req/sec

    _t212_orders_cache.update(items=items, ts=time.time())
    return items


def _normalise_order(raw: dict) -> dict:
    """Best-effort field mapping for a T212 order. Field names confirmed
    live against GET /equity/orders (working orders) on the demo account
    2026-07-21: {ticker: "C_US_EQ", side: "BUY", status: "NEW", value: 4930,
    filledValue: 0, createdAt: "...", ...} — notably T212 market orders can
    be *value*-based (a £ amount, no share quantity at all) rather than
    quantity-based, and `side` is explicit, not something to infer from a
    quantity sign. /equity/history/orders (filled/cancelled orders) hasn't
    been observed with real data yet, so extra candidate keys are kept for
    that endpoint's possibly-different naming. `raw` is passed through in
    full so nothing is silently dropped if a field name turns out to be
    off once a fill is observed."""
    def pick(*keys):
        for k in keys:
            if k in raw and raw[k] is not None:
                return raw[k]
        return None

    qty = pick("filledQuantity", "quantity", "orderedQuantity")
    value = pick("filledValue", "value", "orderedValue")
    side = pick("side")
    ticker_raw = pick("ticker") or ""
    price = pick("fillPrice", "averagePrice", "limitPrice", "stopPrice")
    if price is None and isinstance(qty, (int, float)) and qty and isinstance(value, (int, float)):
        price = value / qty  # derive when only value + quantity are known
    return {
        "id": pick("id", "orderId"),
        "ticker": str(ticker_raw).split("_")[0],
        "t212_ticker": ticker_raw,
        "status": pick("status"),
        "side": side or ("SELL" if isinstance(qty, (int, float)) and qty < 0 else "BUY"),
        "quantity": _clean(abs(qty)) if isinstance(qty, (int, float)) else None,
        "fill_price": _clean(price),
        "fill_value": _clean(value),
        "date": pick("dateExecuted", "dateModified", "dateCreated", "createdAt", "updatedAt"),
        "order_type": pick("type"),
        "raw": {k: _clean(v) if not isinstance(v, (dict, list)) else v
                for k, v in raw.items()},
    }


@app.get("/api/journal")
def journal():
    """Trade journal: your actual FILLED T212 orders (demo or live,
    whichever T212_ENV points at), cross-checked against the model's
    current AI Score/action for that ticker. Read-only — never places
    orders, even though the configured key may have order permissions."""
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
        token = base64.b64encode(f"{key}:{secret}".encode()).decode()
        auth = f"Basic {token}"
    else:
        auth = key

    raw_orders = _fetch_t212_order_history(host, auth)
    orders = [_normalise_order(o) for o in raw_orders]
    orders = [o for o in orders if o["status"] in (None, "FILLED")]
    orders.sort(key=lambda o: o["date"] or "", reverse=True)

    df, as_of = _screener_df()
    for o in orders:
        t = o["ticker"]
        row = df.loc[t] if t in df.index else None
        o["ai_score"] = _clean(row["ai_score"]) if row is not None else None
        o["action"] = row["action"] if row is not None else None
        o["in_universe"] = row is not None

    return {"connected": True, "env": env, "as_of": as_of,
            "count": len(orders), "trades": orders}


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


@app.get("/api/signals")
def signals_endpoint(capital: float = 100_000.0):
    """Today's Signal Book: names passing the entry filter (src/signals.py),
    inverse-vol weighted, with a suggested £ allocation and share count for
    the given capital. Read-only — mirrors the dashboard SIGNALS tab, using
    the same cached sentiment snapshot as the screener (no live re-fetch)."""
    df, as_of = _screener_df()
    px = _cache["px"]
    panels = momentum.build_panels(px)
    today = px.index[-1]
    sent_row = (df["sentiment_score"] if "sentiment_score" in df.columns
                else pd.Series(0.0, index=df.index)).reindex(px.columns).fillna(0.0)

    w = signals.weights_for_date(today, px, panels, sentiment=sent_row,
                                  use_sentiment=True)
    longs = w[w > 0].sort_values(ascending=False)

    positions = []
    for t, wgt in longs.items():
        price = float(px[t].iloc[-1])
        alloc = float(wgt) * capital
        positions.append({
            "ticker": t,
            "name": TICKER_NAMES.get(t, t),
            "sector": SECTORS.get(t, "Other"),
            "sleeve": TICKER_SLEEVE.get(t, "core"),
            "weight_pct": _clean(round(float(wgt) * 100, 2)),
            "last_price": _clean(round(price, 2)),
            "alloc_gbp": _clean(round(alloc, 2)),
            "suggested_shares": int(alloc // price) if price > 0 else 0,
            "mom_12m": _clean(panels["tsm"][t].iloc[-1]) if t in panels["tsm"].columns else None,
            "ratio_52w": _clean(panels["ratio52"][t].iloc[-1]) if t in panels["ratio52"].columns else None,
            "rsi": _clean(panels["rsi"][t].iloc[-1]) if t in panels["rsi"].columns else None,
            "sentiment_score": _clean(sent_row.get(t, 0.0)),
        })

    return {
        "as_of": as_of,
        "capital": capital,
        "gross_long_pct": round(float(w[w > 0].sum()) * 100, 1),
        "count": len(positions),
        "positions": positions,
    }


# ──────────────────────────────────────────────────────────────────────────
# Backtest — runs the real vector backtest (src/backtest.py) on the cached
# price history. A full run takes ~30-60s, far too long for one HTTP
# round-trip through the Next.js proxy, so it computes in a background
# thread and the frontend polls: first call returns {"status": "running"},
# later calls return the finished payload (cached for an hour per variant).
# ──────────────────────────────────────────────────────────────────────────
_BT_TTL = 60 * 60
_bt_lock = threading.Lock()
_bt_jobs: dict = {}   # "sent=True/False" -> {"status", "ts", "result"|"message"}


def _run_backtest_job(key: str, use_sentiment: bool) -> None:
    try:
        from src.backtest import run_backtest
        from src.data import split_universe_benchmark
        px = _load_px()
        uni, bench = split_universe_benchmark(px)
        if bench is None:
            raise RuntimeError("Benchmark (SPY) missing from the price cache.")
        res = run_backtest(uni, bench, use_sentiment=use_sentiment)

        eq = res.equity.resample("W-FRI").last().dropna()
        bm = (res.benchmark.resample("W-FRI").last()
              .reindex(eq.index).ffill())
        trades = res.trades.tail(25).copy()
        trades["entry_date"] = trades["entry_date"].astype(str)
        trades["exit_date"] = trades["exit_date"].astype(str)

        result = {
            "as_of": str(px.index[-1].date()),
            "use_sentiment": use_sentiment,
            "metrics": {k: _clean(v) for k, v in res.metrics.items()},
            "equity": {
                "dates": [str(d.date()) for d in eq.index],
                "strategy": [round(float(v), 2) for v in eq],
                "benchmark": [round(float(v), 2) for v in bm],
            },
            "walk_forward": res.walk_forward,
            "duration": res.duration,
            "trades": [
                {k: _clean(v) for k, v in row.items()}
                for row in trades.to_dict("records")
            ],
        }
        with _bt_lock:
            _bt_jobs[key] = {"status": "done", "ts": time.time(),
                             "result": result}
    except Exception as e:
        with _bt_lock:
            _bt_jobs[key] = {"status": "error", "ts": time.time(),
                             "message": str(e)}


@app.get("/api/backtest")
def backtest(sentiment: bool = False):
    key = f"sent={sentiment}"
    with _bt_lock:
        job = _bt_jobs.get(key)
        if job:
            if job["status"] == "done" and time.time() - job["ts"] < _BT_TTL:
                return {"status": "done", **job["result"]}
            if job["status"] == "running":
                return {"status": "running"}
            if job["status"] == "error":
                # report once, then allow a retry on the next call
                _bt_jobs.pop(key, None)
                return {"status": "error", "message": job.get("message", "")}
        _bt_jobs[key] = {"status": "running", "ts": time.time()}
    threading.Thread(target=_run_backtest_job, args=(key, sentiment),
                     daemon=True).start()
    return {"status": "running"}


# ──────────────────────────────────────────────────────────────────────────
# AI Copilot — GPT-4.1 Mini, grounded strictly in this app's own data
# (screener scores, Yahoo Finance fundamentals, Alpha Vantage + free
# sentiment history). Ported from the Streamlit dashboard's copilot panel.
# ──────────────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str


class CopilotRequest(BaseModel):
    messages: list[ChatMessage]


_COPILOT_CTX_COLS = [
    "sector", "sleeve", "ai_score", "action", "tech_score", "sent_score",
    "fund_score", "value_score", "under_radar", "last_price", "mom_12m",
    "rsi", "sentiment_score", "pe_forward", "roe",
]


def _ticker_deep_dive(ticker: str, df: pd.DataFrame) -> str:
    """Full Yahoo Finance fundamentals + Alpha Vantage/free sentiment
    history for one ticker, for when a question names it specifically.

    Repeats the screener/scoring fields as explicit "key: value" lines
    (not just relying on the big whitespace-aligned table) because GPT-4.1
    Mini was unreliable at reading a single cell out of a 130+ row, 15
    column fixed-width dump — e.g. it misread META's under_radar=True as
    False even though the raw table text was correct. One-ticker-at-a-time
    key: value pairs are far more reliable for the model to quote exactly.
    """
    if ticker not in df.index:
        return ""
    row = df.loc[ticker]
    lines = [f"\n--- DETAILED DATA FOR {ticker} ({row.get('sector', '?')}, "
             f"{row.get('sleeve', '?')} sleeve) ---",
             "This is the authoritative data for this ticker; prefer it "
             "over the summary table above for any of these fields."]

    score_cols = ["ai_score", "action", "tech_score", "sent_score",
                  "fund_score", "value_score", "under_radar", "last_price",
                  "mom_12m", "rsi", "sentiment_score"]
    score_present = {c: row[c] for c in score_cols if c in df.columns and pd.notna(row.get(c))}
    if score_present:
        lines.append("Scoring: " +
                     ", ".join(f"{k}={v}" for k, v in score_present.items()))

    fund_cols = ["pe_forward", "pe_trailing", "ps_ratio", "price_to_book",
                 "ev_ebitda", "roe", "roa", "debt_equity", "gross_margin",
                 "operating_margin", "profit_margin", "revenue_growth",
                 "peg_ratio", "dividend_yield", "market_cap", "beta"]
    fund_present = {c: row[c] for c in fund_cols if c in df.columns and pd.notna(row.get(c))}
    if fund_present:
        lines.append("Yahoo Finance fundamentals: " +
                     ", ".join(f"{k}={v:.4g}" for k, v in fund_present.items()))

    try:
        p = Path(CFG.paths.sentiment_log)
        if p.exists():
            hist = pd.read_csv(p, parse_dates=["date"])
            tick_hist = (hist[hist.ticker == ticker]
                        .sort_values("date", ascending=False).head(10))
            if not tick_hist.empty:
                lines.append("Recent sentiment history (Alpha Vantage historical + "
                             "free daily snapshots, newest first):")
                for _, r in tick_hist.iterrows():
                    lines.append(
                        f"  {r['date'].date()}: score={r['score']:.3f} "
                        f"label={r['label']} n_headlines={int(r['n_headlines'])} "
                        f"source={r['source']}"
                    )
            else:
                lines.append("No logged sentiment history yet for this ticker "
                             "(Alpha Vantage backfill for its sleeve may still be "
                             "in progress).")
    except Exception:
        pass
    return "\n".join(lines)


def _mentioned_tickers(text: str, universe: list[str], limit: int = 5) -> list[str]:
    words = set(re.findall(r"[A-Za-z]{2,6}", text.upper()))
    return [t for t in universe if t in words][:limit]


@app.post("/api/copilot")
def copilot(req: CopilotRequest):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key.startswith("your_"):
        key = ""
    if not key:
        return {"reply": None,
                "message": "Set OPENAI_API_KEY in .env to enable the AI Copilot."}
    try:
        from openai import OpenAI
    except ImportError:
        return {"reply": None,
                "message": "Run: pip install openai (in the backend environment)."}

    df, as_of = _screener_df()
    ctx_df = df[[c for c in _COPILOT_CTX_COLS if c in df.columns]]
    data_ctx = ctx_df.to_string(max_rows=150)

    last_user_msg = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), "")
    deep_dives = [_ticker_deep_dive(t, df)
                  for t in _mentioned_tickers(last_user_msg, df.index.tolist())]
    deep_dive_text = "\n".join(d for d in deep_dives if d)

    system_prompt = (
        "You are a quantitative stock analysis assistant for a momentum + "
        "sentiment + fundamentals screener. Answer ONLY using the data below "
        "(Yahoo Finance prices/fundamentals, Alpha Vantage + free news "
        "sentiment history, and the computed AI Scores). Never use outside "
        "knowledge, general opinions, or facts about the company you were "
        "not given here. Always cite specific numbers from the data. If "
        "asked about sentiment, refer to the actual historical scores and "
        "label them by source (alphavantage = historical, free = today's "
        "snapshot). The big table below is whitespace-aligned and easy to "
        "misread across columns for a single row — when a 'DETAILED DATA' "
        "section is present for a ticker, treat its key: value lines as the "
        "authoritative source for that ticker and do not contradict them. "
        "In replies, write field and sleeve names in plain English with no "
        "underscores: say 'under the radar' not 'under_radar', 'Quality "
        "Value sleeve' not 'quality_value', 'Niche Growth' not "
        "'niche_growth'.\n\n"
        f"SCREENER DATA AS OF {as_of} (one row per stock):\n{data_ctx}"
        + (f"\n{deep_dive_text}" if deep_dive_text else "")
    )

    try:
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in req.messages],
            max_tokens=600,
            temperature=0.2,
        )
        return {"reply": resp.choices[0].message.content}
    except Exception as e:
        raise HTTPException(502, f"OpenAI request failed: {e}")

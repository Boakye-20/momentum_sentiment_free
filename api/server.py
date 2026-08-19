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
import collections
import hmac
import logging
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
from fastapi import Depends, FastAPI, HTTPException, Request
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

# ──────────────────────────────────────────────────────────────────────────
# Security headers — set on every response.
# No HSTS: this server runs over plain HTTP on localhost; HSTS would pin the
# browser to HTTPS and break the app.
# ──────────────────────────────────────────────────────────────────────────
from starlette.responses import Response as _StarResponse

@app.middleware("http")
async def _security_headers(request: Request, call_next) -> _StarResponse:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ──────────────────────────────────────────────────────────────────────────
# Logging — rotating file handler so the log cannot grow unbounded.
# ──────────────────────────────────────────────────────────────────────────
import logging.handlers as _lh

_log = logging.getLogger("api.server")
_log.setLevel(logging.INFO)
if not _log.handlers:
    _rh = _lh.RotatingFileHandler(
        "api-server.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    _rh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _log.addHandler(_rh)

# ──────────────────────────────────────────────────────────────────────────
# Auth. Every route requires `Authorization: Bearer $API_SECRET_KEY`.
#
# Fails CLOSED: with no API_SECRET_KEY set, every request is refused rather
# than served openly. Binding to 127.0.0.1 is not a security boundary — one
# `--host 0.0.0.0`, port forward or tunnel turns this into a public endpoint
# serving real Trading212 positions and an OpenAI key that costs money per
# call. Generate a key with:  python -c "import secrets;print(secrets.token_hex(32))"
# ──────────────────────────────────────────────────────────────────────────
def require_auth(request: Request) -> None:
    expected = os.environ.get("API_SECRET_KEY", "").strip()
    if not expected or expected.startswith("your_"):
        raise HTTPException(
            503,
            "API_SECRET_KEY is not set in .env — the API refuses to serve "
            "unauthenticated requests. Generate one with: "
            'python -c "import secrets;print(secrets.token_hex(32))"',
        )
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    # compare_digest keeps the check constant-time (no early-exit timing leak)
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), expected):
        raise HTTPException(401, "Invalid or missing API key.")


# ──────────────────────────────────────────────────────────────────────────
# Rate limiting. Only /api/copilot needs it — it is the one route that spends
# real money (an OpenAI call per request) and the one an unbounded loop could
# drain a credit balance through. Fixed-window counter per client IP, kept in
# memory: this is a single-process local server, so a shared store would be
# ceremony without benefit.
# ──────────────────────────────────────────────────────────────────────────
_COPILOT_RATE_LIMIT = 20        # requests …
_COPILOT_RATE_WINDOW = 60       # … per this many seconds, per IP
_rate_lock = threading.Lock()
_rate_hits: dict[str, collections.deque] = {}


def rate_limit_copilot(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _rate_lock:
        hits = _rate_hits.setdefault(ip, collections.deque())
        while hits and now - hits[0] > _COPILOT_RATE_WINDOW:
            hits.popleft()
        if len(hits) >= _COPILOT_RATE_LIMIT:
            retry = int(_COPILOT_RATE_WINDOW - (now - hits[0])) + 1
            raise HTTPException(
                429,
                f"Rate limit reached ({_COPILOT_RATE_LIMIT} copilot requests "
                f"per {_COPILOT_RATE_WINDOW}s). Try again in {retry}s.",
            )
        hits.append(now)


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


def _tradeable_cols(px: pd.DataFrame) -> pd.DataFrame:
    """Restrict a price frame to the configured universe + the benchmark.

    The price cache legitimately holds columns that are NOT tradeable stocks:
    the EM comparison ETFs (EEM/EMXC/FRDM, see
    UniverseConfig.em_benchmark_tickers) and any ticker since retired from a
    sleeve. Every caller of _load_px treats a cache column as a stock, so
    without this filter adding a benchmark to the cache silently turned it into
    a screener row AND a backtest holding — EEM/EMXC/FRDM were being scored and
    could have been recommended as picks.

    Filtering once here (an intersection, not a drop-list) means a future cache
    addition cannot leak in either.
    """
    keep = [t for t in list(CFG.universe.tickers)
            + [CFG.universe.benchmark_ticker] if t in px.columns]
    return px[keep]


def _load_px() -> pd.DataFrame:
    """Tradeable-universe prices. See _load_px_raw for the cache mechanics."""
    return _tradeable_cols(_load_px_raw())


def _load_px_raw() -> pd.DataFrame:
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
            scores = latest.groupby("ticker")["score"].mean().reindex(df.index)
            # Missing sentiment means "average", not 0.0. scoring.py min-max
            # normalises this column into a 25%-weighted layer of the AI Score,
            # and news sentiment is mildly positive by nature (mean ~+0.17), so
            # a 0.0 fill pinned every uncovered ticker to the BOTTOM of the
            # sentiment layer. That silently depressed the displayed AI Score
            # for all 25 EM names and all 19 global ADRs, none of which have
            # Alpha Vantage coverage yet. Same fix as
            # sentiment.load_sentiment_panel and executor.execute_trades.
            mean = scores.mean()
            df["sentiment_score"] = scores.fillna(
                mean if pd.notna(mean) else 0.0)
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


@app.get("/api/screener", dependencies=[Depends(require_auth)])
def screener():
    df, as_of = _screener_df()
    records = []
    for t, row in df.iterrows():
        rec = {k: _clean(v) for k, v in row.items() if k != "price_trend"}
        rec["ticker"] = t
        rec["price_trend"] = row.get("price_trend") or []
        records.append(rec)
    return {"as_of": as_of, "count": len(records), "stocks": records}


@app.get("/api/stock/{ticker}", dependencies=[Depends(require_auth)])
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


@app.get("/api/portfolio", dependencies=[Depends(require_auth)])
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
    px = _cache["px"]
    # Signal Book is the app's one rating system now (see /api/journal) — the
    # composite AI Score/action is no longer surfaced here.
    w_now = _signal_weights_at(str(pd.Timestamp.today().normalize().date()))
    out = []
    for p in positions:
        # Confirmed live against GET /equity/positions on the demo account
        # 2026-07-21: ticker lives under instrument.ticker (not top-level
        # "ticker"), avg price is "averagePricePaid", and P/L is nested
        # under walletImpact.unrealizedProfitLoss — not top-level "ppl".
        raw = p.get("instrument", {}).get("ticker", "")   # e.g. "AAPL_US_EQ"
        sym = raw.split("_")[0]
        wallet = p.get("walletImpact", {})
        out.append({
            "ticker": sym, "t212_ticker": raw,
            "quantity": _clean(p.get("quantity")),
            "average_price": _clean(p.get("averagePricePaid")),
            "current_price": _clean(p.get("currentPrice")),
            "market_value": _clean(wallet.get("currentValue")),
            "opened_at": p.get("createdAt"),
            "ppl": _clean(wallet.get("unrealizedProfitLoss")),
            "signal_weight": (
                _clean(round(float(w_now[sym]) * 100, 2))
                if sym in w_now.index and w_now[sym] > 0 else None
            ),
            "in_universe": sym in df.index,
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
    """Field mapping for a T212 order, confirmed live on the demo account
    2026-07-21 against two DIFFERENT schemas:

    GET /equity/orders (working/pending orders) — flat:
      {ticker, side, status: "NEW", value, filledValue: 0, createdAt, ...}

    GET /equity/history/orders (what /api/journal actually calls) — items
    are nested {"order": {...same shape as above...}, "fill": {"quantity",
    "price", "filledAt", "walletImpact": {...}}}. The order's own ticker/
    side/status/value live under "order"; the actual executed quantity and
    per-share price only exist under "fill" (order.filledValue is the £
    amount, not a share count — T212 market orders here were value-based).

    Handles both shapes so this survives if ever pointed at /equity/orders
    too. `raw` is passed through in full (nested dicts kept as-is) so
    nothing is silently dropped if a field turns out to be named
    differently in a case this hasn't seen yet (e.g. a SELL, a LIMIT order,
    a partial fill)."""
    order = raw.get("order", raw)   # nested (history) vs flat (working orders)
    fill = raw.get("fill") or {}

    def pick(d, *keys):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return None

    ticker_raw = (pick(order, "ticker")
                  or order.get("instrument", {}).get("ticker", ""))
    qty = pick(fill, "quantity") or pick(order, "filledQuantity", "quantity")
    value = pick(order, "filledValue", "value", "orderedValue")
    price = pick(fill, "price") or pick(order, "fillPrice", "averagePrice",
                                         "limitPrice", "stopPrice")
    if price is None and isinstance(qty, (int, float)) and qty and isinstance(value, (int, float)):
        price = value / qty  # derive when only value + quantity are known
    date = pick(fill, "filledAt") or pick(order, "dateExecuted",
                                           "dateModified", "dateCreated",
                                           "createdAt", "updatedAt")
    side = pick(order, "side")

    return {
        "id": pick(order, "id", "orderId"),
        "ticker": str(ticker_raw).split("_")[0],
        "t212_ticker": ticker_raw,
        "status": pick(order, "status"),
        "side": side or ("SELL" if isinstance(qty, (int, float)) and qty < 0 else "BUY"),
        "quantity": _clean(abs(qty)) if isinstance(qty, (int, float)) else None,
        "fill_price": _clean(price),
        "fill_value": _clean(value),
        "date": date,
        "order_type": pick(order, "type"),
        "raw": {k: _clean(v) if not isinstance(v, (dict, list)) else v
                for k, v in raw.items()},
    }


_SIGNAL_WEIGHTS_CACHE: dict = {}
_SIGNAL_WEIGHTS_TTL = 60 * 60  # a past date's weights never change; "today" is hourly-enough


def _signal_weights_at(date_key: str) -> pd.Series:
    """Target Signal Book weights (src/signals.py's entry filter + inverse-vol
    sizing) as of `date_key` — the nearest available close ON OR BEFORE that
    date, matching the T+1 execution rule used throughout this app (an order
    filled intraday was actually built from the PRIOR close). Shared by
    /api/signals ("today") and /api/journal ("was this ticker a pick when I
    traded it"), so both endpoints always agree with each other and with the
    real backtest engine — one signal system, not two.

    Sentiment is looked up from data/sentiment_history.csv (nearest logged
    snapshot per ticker on/before the date; neutral 0.0 if none logged that
    far back yet — never fabricated, per the project's own rule). Cached per
    date, since a past date's weights never change.

    Price/technical panels and sentiment are bounded DIFFERENTLY on purpose:
    price panels can only reflect a completed close, so they're clamped to
    the nearest available bar on/before `date_key` (the T+1 constraint — a
    hard data limit, today's close doesn't exist yet). Sentiment isn't
    bar-based; it's a same-day "what's the news saying right now" reading
    that the scheduled fetch already updates same-day, so it's bounded to
    the actual `date_key` itself, not clamped to the last price close. For
    any real historical date this is a no-op (price data already exists for
    that date, so the two bounds coincide) — it only matters for "today",
    when price necessarily lags but sentiment doesn't have to."""
    now = time.time()
    cached = _SIGNAL_WEIGHTS_CACHE.get(date_key)
    if cached is not None and now - cached["ts"] < _SIGNAL_WEIGHTS_TTL:
        return cached["w"]

    px = _cache["px"]
    query_date = pd.Timestamp(date_key)
    target = min(query_date, px.index.max())   # price/panel bound (hard constraint)
    panels = momentum.build_panels(px)

    sent_row = pd.Series(0.0, index=px.columns)
    try:
        p = Path(CFG.paths.sentiment_log)
        if p.exists():
            hist = pd.read_csv(p, parse_dates=["date"])
            hist = hist[hist.date <= query_date]   # sentiment bound (no such constraint)
            if not hist.empty:
                latest = hist.sort_values("date").groupby("ticker").tail(1)
                sent_row = (latest.set_index("ticker")["score"]
                            .reindex(px.columns).fillna(0.0))
    except Exception:
        pass

    w = signals.weights_for_date(target, px, panels, sentiment=sent_row,
                                  use_sentiment=True)
    _SIGNAL_WEIGHTS_CACHE[date_key] = {"w": w, "ts": now}
    return w


@app.get("/api/journal", dependencies=[Depends(require_auth)])
def journal():
    """Trade journal: your actual FILLED T212 orders (demo or live,
    whichever T212_ENV points at), cross-checked against the Signal Book
    (the SAME entry-filter/weighting system as /api/signals and the
    backtest — not the Screener's separate composite AI Score, which uses
    different criteria and can legitimately disagree with what the Signal
    Book picked). Read-only — never places orders, even though the
    configured key may have order permissions."""
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
    # "Now" = today's real calendar date, not the price cache's last close —
    # so today's own sentiment fetch is picked up even before the market
    # closes (see _signal_weights_at's docstring on the two different bounds).
    w_now = _signal_weights_at(str(pd.Timestamp.today().normalize().date()))

    bot_file = Path(CFG.paths.data_dir) / "bot_orders.json"
    bot_orders = set()
    if bot_file.exists():
        try:
            import json
            with open(bot_file, "r") as f:
                # Store as strings for easy matching
                bot_orders = set(str(x) for x in json.load(f))
        except Exception:
            pass

    for o in orders:
        t = o["ticker"]
        o["in_universe"] = t in df.index
        o["is_bot"] = str(o.get("id")) in bot_orders

        o["signal_weight_now"] = (
            _clean(round(float(w_now[t]) * 100, 2))
            if t in w_now.index and w_now[t] > 0 else None
        )

        o["signal_weight_at_trade"] = None
        if o["date"]:
            try:
                date_key = str(pd.Timestamp(o["date"]).date())
                w_trade = _signal_weights_at(date_key)
                if t in w_trade.index and w_trade[t] > 0:
                    o["signal_weight_at_trade"] = _clean(round(float(w_trade[t]) * 100, 2))
            except Exception:
                pass

    return {"connected": True, "env": env, "as_of": as_of,
            "count": len(orders), "trades": orders}


@app.get("/api/meta", dependencies=[Depends(require_auth)])
def meta():
    df, as_of = _screener_df()
    px = _cache["px"]
    w = _signal_weights_at(str(px.index[-1].date()))
    return {
        "as_of": as_of,
        "universe_size": len(df),
        "sleeves": sorted(df["sleeve"].unique().tolist()),
        "sectors": sorted(df["sector"].unique().tolist()),
        "signal_count": int((w > 0).sum()),
        "gross_long_pct": round(float(w[w > 0].sum()) * 100, 1),
    }


@app.get("/api/signals", dependencies=[Depends(require_auth)])
def signals_endpoint(capital: float = 100_000.0):
    """Today's Signal Book: names passing the entry filter (src/signals.py),
    inverse-vol weighted, with a suggested £ allocation and share count for
    the given capital. Read-only — mirrors the dashboard SIGNALS tab. Weight
    computation is shared with /api/journal via _signal_weights_at, so both
    always agree on what the Signal Book actually picked on a given date."""
    df, as_of = _screener_df()
    px = _cache["px"]
    panels = momentum.build_panels(px)   # still needed here for the display-only
                                          # mom_12m/ratio_52w/rsi fields below
    sent_row = (df["sentiment_score"] if "sentiment_score" in df.columns
                else pd.Series(0.0, index=df.index)).reindex(px.columns).fillna(0.0)

    # Today's real calendar date, not the price cache's last close — see
    # _signal_weights_at's docstring on why sentiment isn't clamped to price.
    w = _signal_weights_at(str(pd.Timestamp.today().normalize().date()))
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
        _log.exception("Backtest job %s failed: %s", key, e)
        with _bt_lock:
            _bt_jobs[key] = {"status": "error", "ts": time.time(),
                             "message": "Backtest failed. Check server logs.",
                             "detail": str(e)}


@app.get("/api/backtest", dependencies=[Depends(require_auth)])
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


@app.post("/api/copilot",
          dependencies=[Depends(require_auth), Depends(rate_limit_copilot)])
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

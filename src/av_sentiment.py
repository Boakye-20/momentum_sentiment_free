"""
src/av_sentiment.py — Alpha Vantage NEWS_SENTIMENT (free tier).

Why this matters: unlike RSS/yfinance (recent only), Alpha Vantage's
NEWS_SENTIMENT archive reaches back to ~March 2022, so you can pull a few YEARS
of real, point-in-time, per-ticker sentiment for free and actually run
`backtest --use-sentiment`.

Free-tier limits (be realistic):
  * ~25 requests/day. One request = one ticker over one time window (<=1000
    articles, newest first). A 30-stock multi-year history therefore can't be
    pulled in a single day — so everything is CACHED to data/av_sentiment_history.csv
    and fetched incrementally. Re-runs never re-download what you already have.

Scores: Alpha Vantage returns `ticker_sentiment_score` per article, roughly
  <=-0.35 bearish ... >=0.35 bullish. We aggregate per day, weighting each
  article by its `relevance_score` for that ticker.

Get a free key at https://www.alphavantage.co/support/#api-key and put it in a
`.env` file as  ALPHAVANTAGE_API_KEY=yourkey  (see .env.example).
"""

from __future__ import annotations
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from config import CFG
from src.sentiment import append_sentiment_rows

AV_URL = "https://www.alphavantage.co/query"
AV_SOURCE = "alphavantage"


def get_api_key(explicit: str | None = None) -> str | None:
    """Key precedence: explicit arg -> env var -> config -> .env file."""
    if explicit:
        return explicit
    key = os.environ.get("ALPHAVANTAGE_API_KEY") or CFG.sentiment.alphavantage_api_key
    if not key:
        env = Path(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("ALPHAVANTAGE_API_KEY"):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key or None


# ──────────────────────────────────────────────────────────────────────────
# Parsing (pure function — unit-tested offline)
# ──────────────────────────────────────────────────────────────────────────
def parse_feed(feed: list[dict], universe: set[str]) -> pd.DataFrame:
    """
    Turn an Alpha Vantage `feed` list into tidy rows:
    (date, ticker, score, relevance) — one row per (article, tracked ticker).
    """
    rows = []
    for art in feed:
        tp = art.get("time_published", "")
        try:
            date = datetime.strptime(tp[:8], "%Y%m%d").date()
        except ValueError:
            continue
        for ts in art.get("ticker_sentiment", []):
            tk = ts.get("ticker", "")
            if tk not in universe:
                continue
            try:
                score = float(ts.get("ticker_sentiment_score", 0.0))
                rel = float(ts.get("relevance_score", 0.0))
            except (TypeError, ValueError):
                continue
            rows.append({"date": date, "ticker": tk, "score": score, "relevance": rel})
    return pd.DataFrame(rows, columns=["date", "ticker", "score", "relevance"])


def aggregate_daily(rows: pd.DataFrame) -> pd.DataFrame:
    """Relevance-weighted daily sentiment per ticker: (date, ticker, score, n)."""
    if rows.empty:
        return pd.DataFrame(columns=["date", "ticker", "score", "n_headlines"])

    def _wavg(g):
        w = g["relevance"].clip(lower=1e-6)
        return pd.Series({"score": round((g["score"] * w).sum() / w.sum(), 4),
                          "n_headlines": len(g)})

    out = (rows.groupby(["date", "ticker"], group_keys=False)[["score", "relevance"]]
           .apply(_wavg).reset_index())
    return out


def _label(score: float) -> str:
    if score >= CFG.sentiment.positive_threshold:
        return "positive"
    if score <= CFG.sentiment.negative_threshold:
        return "negative"
    return "neutral"


# ──────────────────────────────────────────────────────────────────────────
# Network fetch
# ──────────────────────────────────────────────────────────────────────────
def _request(params: dict) -> dict:
    import requests
    r = requests.get(AV_URL, params=params, timeout=30)
    data = r.json()
    # Alpha Vantage signals problems with these keys instead of HTTP errors.
    for k in ("Note", "Information", "Error Message"):
        if k in data:
            raise RuntimeError(f"Alpha Vantage: {data[k]}")
    return data


def fetch_ticker(ticker: str, api_key: str,
                 time_from: str | None = None, time_to: str | None = None,
                 limit: int = 1000, sort: str = "EARLIEST") -> pd.DataFrame:
    """One API call for one ticker; returns tidy rows (date,ticker,score,relevance)."""
    params = {"function": "NEWS_SENTIMENT", "tickers": ticker,
              "apikey": api_key, "limit": str(limit), "sort": sort}
    if time_from:
        params["time_from"] = time_from
    if time_to:
        params["time_to"] = time_to
    data = _request(params)
    return parse_feed(data.get("feed", []), {ticker})


def fetch_today(tickers: list[str] | None = None, api_key: str | None = None,
                max_requests: int = 25, pause: float = 1.0) -> pd.DataFrame:
    """Latest sentiment snapshot for the universe (one request per ticker)."""
    tickers = tickers or CFG.universe.tickers
    api_key = get_api_key(api_key)
    if not api_key:
        raise RuntimeError("No Alpha Vantage API key (set ALPHAVANTAGE_API_KEY in .env).")

    all_rows = []
    for i, t in enumerate(tickers[:max_requests]):
        print(f"  [AV] {t} ...")
        try:
            all_rows.append(fetch_ticker(t, api_key, sort="LATEST", limit=200))
        except RuntimeError as e:
            print(f"  [AV] stopped at {t}: {e}")
            break
        time.sleep(pause)
    rows = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    daily = aggregate_daily(rows)
    if daily.empty:
        return daily
    # collapse to the most recent day per ticker for a "today" snapshot
    snap = (daily.sort_values("date").groupby("ticker").tail(1).copy())
    snap["label"] = snap["score"].map(_label)
    return snap


def fetch_history(tickers: list[str], start: str, end: str,
                  api_key: str | None = None, max_requests: int = 25,
                  pause: float = 1.0) -> pd.DataFrame:
    """
    Pull historical daily sentiment and append to the rolling log (cached).
    Spends at most `max_requests` API calls. Each ticker RESUMES from the end
    of its contiguous cached history: the 1000-article request cap truncates
    busy tickers early, so covering the full window can take several calls,
    spread across daily budgets. Fully covered tickers cost nothing. Returns
    the daily rows fetched this run.
    """
    api_key = get_api_key(api_key)
    if not api_key:
        raise RuntimeError("No Alpha Vantage API key (set ALPHAVANTAGE_API_KEY in .env).")
    tt = pd.Timestamp(end).strftime("%Y%m%dT2359")

    resume = _resume_from(set(tickers), start, end)
    todo = [(t, resume[t]) for t in tickers if resume[t] is not None]
    if not todo:
        print("[AV] history already cached for all requested tickers.")
        return pd.DataFrame()
    print(f"[AV] fetching history for {min(len(todo), max_requests)} ticker(s) "
          f"(of {len(todo)} incomplete), window end {end} ...")

    fetched = []
    for t, frm in todo[:max_requests]:
        print(f"  [AV] {t} (from {frm:%Y-%m-%d}) ...")
        try:
            rows = fetch_ticker(t, api_key,
                                time_from=frm.strftime("%Y%m%dT0000"), time_to=tt,
                                sort="EARLIEST", limit=1000)
        except RuntimeError as e:
            print(f"  [AV] stopped at {t}: {e}")
            break
        daily = aggregate_daily(rows)
        if not daily.empty:
            daily["label"] = daily["score"].map(_label)
            append_sentiment_rows(daily, source=AV_SOURCE)
            fetched.append(daily)
        time.sleep(pause)

    remaining = len(todo) - len(fetched)
    if remaining > 0:
        print(f"[AV] {remaining} ticker(s) still incomplete — run again tomorrow "
              f"(free tier is ~25 requests/day). Cached data is reused "
              f"automatically and each run resumes where the last stopped.")
    return pd.concat(fetched, ignore_index=True) if fetched else pd.DataFrame()


# A hole bigger than this in a ticker's cached dates marks the end of its
# contiguous history block (isolated fetch_today snapshot rows sit beyond it).
_GAP_DAYS = 60
# Treat history as complete once it reaches within this of the window end,
# so sparse news around the tail can't trigger a re-fetch every day.
_TAIL_TOLERANCE_DAYS = 30


def _resume_from(tickers: set[str], start: str, end: str,
                 path: str | None = None) -> dict:
    """
    Per ticker, where the next history fetch should start:
      pd.Timestamp -> fetch from this date (window start, or the day after the
                      contiguous cached block ends — i.e. the truncation point)
      None         -> window already covered, skip.
    A lone fetch_today snapshot row is dated ~today; the gap rule keeps it out
    of the contiguous block, so it can never mask missing history.
    """
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    done_from = end_ts - pd.Timedelta(days=_TAIL_TOLERANCE_DAYS)
    out = {t: start_ts for t in tickers}

    path = path or CFG.paths.sentiment_log
    if not Path(path).exists():
        return out
    df = pd.read_csv(path, parse_dates=["date"])
    if "source" not in df.columns:
        return out
    av = df[df["source"] == AV_SOURCE]

    for t, g in av.groupby("ticker"):
        if t not in out:
            continue
        dates = pd.DatetimeIndex(g["date"].sort_values().unique())
        if dates[0] > start_ts + pd.Timedelta(days=90):
            continue                      # snapshot rows only -> fetch from start
        gaps = np.where(np.diff(dates.values)
                        > np.timedelta64(_GAP_DAYS, "D"))[0]
        block_end = dates[gaps[0]] if len(gaps) else dates[-1]
        out[t] = None if block_end >= done_from else block_end + pd.Timedelta(days=1)
    return out

"""
src/sentiment.py — Module 2: free news sentiment.

Pipeline (all free, no API keys):
  1. fetch recent headlines per ticker
       - yfinance Ticker.news  (ticker-specific)
       - finance RSS feeds      (attributed to tickers by company keywords)
  2. score each headline with VADER  -> compound in [-1, +1]
  3. collapse to ONE score per ticker for "today" (recency-decayed mean)
  4. append today's scores to data/sentiment_history.csv

IMPORTANT (see README): free news is only available for *recent* dates, so this
gives you a *live* signal, not 10 years of history. Step 4 means that every day
you run it you accumulate a little more real history — which you can later feed
back into the backtest.
"""

from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config import CFG, COMPANY_KEYWORDS

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VADER = SentimentIntensityAnalyzer()
except Exception:                       # pragma: no cover
    _VADER = None


# ──────────────────────────────────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────────────────────────────────
def score_text(text: str) -> float:
    """VADER compound score for one headline, in [-1, +1]. 0.0 if unavailable."""
    if not text or _VADER is None:
        return 0.0
    return float(_VADER.polarity_scores(text)["compound"])


def decay_weight(age_days: float, half_life: float | None = None) -> float:
    """Exponential recency weight: 0.5 at one half-life old."""
    half_life = half_life or CFG.sentiment.news_half_life_days
    lam = np.log(2.0) / max(half_life, 1e-9)
    return float(np.exp(-lam * max(age_days, 0.0)))


# ──────────────────────────────────────────────────────────────────────────
# Free news fetchers
# ──────────────────────────────────────────────────────────────────────────
def _yf_news(ticker: str) -> list[dict]:
    """Ticker-specific headlines via yfinance (free)."""
    out = []
    try:
        import yfinance as yf
        for item in (yf.Ticker(ticker).news or []):
            content = item.get("content", item)        # yfinance schema varies
            title = content.get("title") or item.get("title", "")
            ts = (content.get("pubDate") or item.get("providerPublishTime"))
            if isinstance(ts, (int, float)):
                published = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, str):
                published = pd.to_datetime(ts, utc=True, errors="coerce")
            else:
                published = pd.Timestamp.now(tz="UTC")
            if title:
                out.append({"title": title, "published": published, "source": "yfinance"})
    except Exception as e:
        print(f"  [sentiment] yfinance news failed for {ticker}: {e}")
    return out


def _rss_news() -> list[dict]:
    """General finance RSS headlines (free). Attributed to tickers later."""
    items = []
    try:
        import feedparser
    except Exception:
        return items
    for source, url in CFG.sentiment.rss_feeds.items():
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:50]:
                pub = e.get("published_parsed")
                published = (pd.Timestamp(time.mktime(pub), unit="s", tz="UTC")
                             if pub else pd.Timestamp.now(tz="UTC"))
                items.append({
                    "title": e.get("title", ""),
                    "summary": e.get("summary", ""),
                    "published": published,
                    "source": source,
                })
        except Exception as e:
            print(f"  [sentiment] RSS '{source}' failed: {e}")
    return items


def _attribute(rss_items: list[dict], ticker: str) -> list[dict]:
    """Keep RSS items whose title/summary mention the ticker or its company."""
    variants = [ticker.lower()] + COMPANY_KEYWORDS.get(ticker, [])
    hits = []
    for it in rss_items:
        blob = f"{it.get('title','')} {it.get('summary','')}".lower()
        if any(v in blob for v in variants):
            hits.append({"title": it["title"], "published": it["published"],
                         "source": it["source"]})
    return hits


# ──────────────────────────────────────────────────────────────────────────
# Per-ticker daily score
# ──────────────────────────────────────────────────────────────────────────
def ticker_sentiment_today(ticker: str, rss_items: list[dict] | None = None) -> dict:
    """
    Recency-decayed mean VADER score for a ticker's recent headlines.
    Returns {score, n_headlines, label}.
    """
    rss_items = rss_items if rss_items is not None else _rss_news()
    headlines = _yf_news(ticker) + _attribute(rss_items, ticker)
    headlines = headlines[: CFG.sentiment.max_headlines_per_ticker]
    if not headlines:
        return {"score": 0.0, "n_headlines": 0, "label": "neutral"}

    now = pd.Timestamp.now(tz="UTC")
    num, den = 0.0, 0.0
    for h in headlines:
        s = score_text(h["title"])
        pub = h.get("published")
        age = (now - pub).total_seconds() / 86_400.0 if pd.notna(pub) else 0.0
        w = decay_weight(age)
        num += w * s
        den += w
    score = num / den if den else 0.0
    label = ("positive" if score >= CFG.sentiment.positive_threshold
             else "negative" if score <= CFG.sentiment.negative_threshold
             else "neutral")
    return {"score": round(score, 4), "n_headlines": len(headlines), "label": label}


def fetch_all_sentiment(tickers: list[str] | None = None) -> pd.DataFrame:
    """Today's sentiment snapshot for the whole universe (one RSS pull, reused)."""
    tickers = tickers or CFG.universe.tickers
    rss_items = _rss_news()
    rows = []
    for t in tickers:
        print(f"  [sentiment] scoring {t} ...")
        r = ticker_sentiment_today(t, rss_items)
        rows.append({"ticker": t, **r})
    df = pd.DataFrame(rows).set_index("ticker")
    df["date"] = pd.Timestamp.now().strftime("%Y-%m-%d")
    return df


# ──────────────────────────────────────────────────────────────────────────
# History store (grows over time)
# ──────────────────────────────────────────────────────────────────────────
def append_sentiment_rows(rows: pd.DataFrame, source: str = "free",
                          path: str | None = None) -> str:
    """
    Append/replace (date, ticker, source) rows in the rolling history CSV.
    `rows` must have columns: date, ticker, score, n_headlines, label.
    """
    path = path or CFG.paths.sentiment_log
    os.makedirs(Path(path).parent, exist_ok=True)
    cols = ["date", "ticker", "score", "n_headlines", "label", "source"]
    new = rows.copy()
    new["source"] = source
    new["date"] = pd.to_datetime(new["date"]).dt.strftime("%Y-%m-%d")
    new = new.reindex(columns=cols)

    if Path(path).exists():
        hist = pd.read_csv(path)
        if "source" not in hist.columns:
            hist["source"] = "free"
        hist_keys = pd.MultiIndex.from_arrays(
            [hist["date"].astype(str), hist["ticker"], hist["source"]])
        new_keys = pd.MultiIndex.from_arrays(
            [new["date"], new["ticker"], new["source"]])
        out = pd.concat([hist[~hist_keys.isin(new_keys)], new], ignore_index=True)
    else:
        out = new
    out.to_csv(path, index=False)
    print(f"[sentiment] +{len(new)} '{source}' rows -> {path} (total {len(out)})")
    return path


def log_sentiment(snapshot: pd.DataFrame, source: str = "free",
                  path: str | None = None) -> str:
    """Append a 'today' snapshot (index=ticker) to the rolling history CSV."""
    today = snapshot.reset_index()
    today["date"] = today.get("date", pd.Timestamp.now().strftime("%Y-%m-%d"))
    return append_sentiment_rows(today, source=source, path=path)


def load_sentiment_panel(
    trading_days: pd.DatetimeIndex,
    tickers: list[str],
    path: str | None = None,
    source: str | None = None,
) -> pd.DataFrame:
    """
    Build a wide daily sentiment panel (index=trading_days, columns=tickers)
    from logged history, forward-filled within a short window. `source` filters
    to one provider (e.g. 'alphavantage'); None blends all. Returns an all-zero
    panel if no history exists yet (so the backtest still runs).
    """
    path = path or CFG.paths.sentiment_log
    panel = pd.DataFrame(0.0, index=trading_days, columns=tickers)
    if not Path(path).exists():
        return panel
    hist = pd.read_csv(path, parse_dates=["date"])
    if source and "source" in hist.columns:
        hist = hist[hist["source"] == source]
    if hist.empty:
        return panel
    wide = hist.pivot_table(index="date", columns="ticker", values="score",
                            aggfunc="mean")
    wide = wide.reindex(columns=tickers)
    wide = wide.reindex(trading_days.union(wide.index)).sort_index().ffill(limit=5)
    return wide.reindex(trading_days).reindex(columns=tickers).fillna(0.0)

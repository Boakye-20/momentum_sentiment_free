"""
config.py — all tunable parameters in one place.

Everything the strategy needs is here so you can edit behaviour without
touching the engine. Grouped into dataclasses and exposed as a single
`CFG` object. Edit values here (or override at runtime in your own code).

Data is 100% free:
  - Prices  : yfinance (Yahoo Finance)            -> historical, multi-year
  - News    : yfinance .news + finance RSS feeds  -> recent only (see README)
  - Scoring : VADER (vaderSentiment)              -> offline, no API key
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


# ──────────────────────────────────────────────────────────────────────────
# Universe
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class UniverseConfig:
    # A liquid, large-cap default set (DJIA-style). Edit freely.
    tickers: List[str] = field(default_factory=lambda: [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "JPM", "BAC", "GS", "V",
        "HD", "MCD", "KO", "PG", "JNJ", "MRK", "CVX", "CAT", "CRM", "CSCO",
        "DIS", "NKE", "WMT", "UNH", "HON", "IBM", "INTC", "VZ", "AXP", "TRV",
    ])
    benchmark_ticker: str = "SPY"          # free ETF proxy for the market
    # Backtest window (prices are free and historical for these dates).
    start_date: str = "2015-01-01"
    end_date: str = "2025-12-31"


# ──────────────────────────────────────────────────────────────────────────
# Module 1 — Momentum / price engine
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class MomentumConfig:
    tsm_lookback: int = 252          # 12-month trailing return window (days)
    tsm_skip: int = 21               # skip most recent month ("12-1" momentum —
                                     # sidesteps the 1-month reversal effect)
    high_52w_window: int = 252       # 52-week-high lookback
    rsi_period: int = 14
    vol_lookback: int = 63           # realised-vol window for position sizing
    short_ma: int = 20
    long_ma: int = 150               # long-trend filter MA
    breadth_ma: int = 200            # MA used for market-breadth regime


# ──────────────────────────────────────────────────────────────────────────
# Module 2 — Sentiment (free news)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class SentimentConfig:
    news_half_life_days: float = 3.0     # exponential decay of a headline's impact
    score_window_days: int = 5           # rolling window for the per-ticker score
    # VADER compound is in [-1, +1]. Thresholds below are on that scale.
    positive_threshold: float = 0.05
    negative_threshold: float = -0.05
    max_headlines_per_ticker: int = 40   # cap per fetch (politeness / speed)
    # Sentiment provider for live signals: "free" (RSS + yfinance) or
    # "alphavantage" (NEWS_SENTIMENT, ~2022+ history, free key).
    source: str = "free"
    alphavantage_api_key: str = ""       # or set ALPHAVANTAGE_API_KEY in .env
    # Free finance RSS feeds (no key). Stale feeds are skipped silently.
    rss_feeds: Dict[str, str] = field(default_factory=lambda: {
        "Yahoo Finance":  "https://finance.yahoo.com/news/rssindex",
        "CNBC Business":  "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "MarketWatch":    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "Investing.com":  "https://www.investing.com/rss/news_25.rss",
    })


# ──────────────────────────────────────────────────────────────────────────
# Module 3 — Signal rules (the FIXED double-filter)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class SignalConfig:
    # ---- LONG gate (a pullback *within* an uptrend; NOT "at the high & oversold") ----
    trend_tsm_min: float = 0.0          # 12m return must be > 0  (winner)
    near_floor_52w: float = 0.70        # within 30% of 52w high  (real uptrend)
    require_above_long_ma: bool = True  # close > long_ma         (trend confirmation)
    rsi_pullback_max: float = 55.0      # RSI below this = a dip we can buy ...
    rsi_pullback_min: float = 25.0      # ... but above this, so we don't catch crashes
    long_sentiment_min: float = 0.0     # news score must be >= this for a LONG

    # ---- SHORT gate (optional; off by default for a free, long-biased model) ----
    enable_shorts: bool = False
    loser_tsm_max: float = 0.0
    short_ratio_52w_max: float = 0.85
    rsi_bounce_min: float = 55.0
    short_sentiment_max: float = -0.05

    # ---- Ranking when there are more candidates than slots ----
    rank_sentiment_weight: float = 0.5  # blend momentum strength with sentiment


# ──────────────────────────────────────────────────────────────────────────
# Portfolio / backtest mechanics
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class PortfolioConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 10
    max_gross_short: float = 0.30        # 30% gross short cap
    rebalance: str = "M"                 # monthly
    use_inverse_vol_weights: bool = True # size longs ~ 1/realised vol (else equal)
    transaction_cost_bps: float = 10.0   # 10 bps per unit turnover
    execution_delay_days: int = 1        # T+1 (no look-ahead)
    use_breadth_regime: bool = True      # scale exposure with market breadth


@dataclass
class BacktestConfig:
    in_sample_years: int = 5
    out_sample_years: int = 1
    min_history_days: int = 260
    random_seed: int = 42
    # Backtests use price/momentum signals (fully historical & free).
    # Set True only once you have accumulated real logged sentiment history
    # (see README -> "An honest note on free sentiment data").
    use_sentiment_in_backtest: bool = False


@dataclass
class Paths:
    data_dir: str = "data"
    price_cache: str = "data/price_cache.parquet"
    sentiment_log: str = "data/sentiment_history.csv"
    outputs_dir: str = "outputs"


@dataclass
class Config:
    universe:  UniverseConfig  = field(default_factory=UniverseConfig)
    momentum:  MomentumConfig  = field(default_factory=MomentumConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    signal:    SignalConfig    = field(default_factory=SignalConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    backtest:  BacktestConfig  = field(default_factory=BacktestConfig)
    paths:     Paths           = field(default_factory=Paths)


CFG = Config()

# Ticker -> name variants used to attribute free headlines to a stock.
COMPANY_KEYWORDS: Dict[str, List[str]] = {
    "AAPL": ["apple", "iphone", "tim cook"],
    "MSFT": ["microsoft", "azure", "satya nadella"],
    "GOOGL": ["google", "alphabet", "android", "sundar pichai"],
    "AMZN": ["amazon", "aws", "andy jassy"],
    "NVDA": ["nvidia", "jensen huang"],
    "META": ["meta", "facebook", "instagram", "zuckerberg"],
    "JPM": ["jpmorgan", "jp morgan", "jamie dimon"],
    "BAC": ["bank of america", "bofa"],
    "GS": ["goldman sachs", "goldman"],
    "V": ["visa inc"],
    "HD": ["home depot"],
    "MCD": ["mcdonald", "mcdonald's"],
    "KO": ["coca-cola", "coca cola"],
    "PG": ["procter & gamble", "procter and gamble"],
    "JNJ": ["johnson & johnson", "johnson and johnson"],
    "MRK": ["merck"],
    "CVX": ["chevron"],
    "CAT": ["caterpillar"],
    "CRM": ["salesforce", "marc benioff"],
    "CSCO": ["cisco"],
    "DIS": ["disney", "walt disney"],
    "NKE": ["nike"],
    "WMT": ["walmart"],
    "UNH": ["unitedhealth", "united health"],
    "HON": ["honeywell"],
    "IBM": ["ibm", "international business machines"],
    "INTC": ["intel"],
    "VZ": ["verizon"],
    "AXP": ["american express", "amex"],
    "TRV": ["travelers companies"],
}

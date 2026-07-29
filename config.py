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
import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List


# ──────────────────────────────────────────────────────────────────────────
# Universe
# ──────────────────────────────────────────────────────────────────────────
# Five-sleeve universe design (core / quality-value / niche growth / global / em).
# CORE keeps every ticker that already has Alpha Vantage sentiment history
# banked — dropping one throws away weeks of fetched daily budget.
SLEEVE_CORE: List[str] = [
    # ── Mega-cap tech ──────────────────────────────────────────────────────
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD",
    "ORCL", "ADBE", "CRM", "NOW", "UBER", "AVGO", "QCOM", "TXN", "CSCO",
    "IBM", "INTC",
    # ── Financials ─────────────────────────────────────────────────────────
    "JPM", "BAC", "GS", "V", "MA", "AXP", "MS", "C", "WFC", "BLK",
    "SCHW", "TRV",
    # ── Healthcare ─────────────────────────────────────────────────────────
    "JNJ", "MRK", "UNH", "LLY", "ABBV", "AMGN",
    # ── Consumer ───────────────────────────────────────────────────────────
    "HD", "MCD", "KO", "PG", "WMT", "NKE", "DIS", "COST",
    # ── Energy ─────────────────────────────────────────────────────────────
    "CVX", "XOM", "COP", "EOG",
    # ── Industrials / comms ────────────────────────────────────────────────
    "CAT", "HON", "GE", "BA", "RTX", "LMT", "DE", "VZ",
]

# Underrated quality/value: high-ROE, reasonable-multiple compounders with
# thin media coverage — the sleeve where the sentiment + fundamentals layers
# have the most room to add signal.
SLEEVE_QUALITY_VALUE: List[str] = [
    # ── Healthcare plumbing + cheap pharma ─────────────────────────────────
    "MCK", "COR", "CAH", "CI", "ELV", "BMY", "GILD", "VRTX",
    # ── Insurers ───────────────────────────────────────────────────────────
    "CB", "AFL", "ALL", "MET",
    # ── Boring dominators / distribution ───────────────────────────────────
    "AZO", "ORLY", "CASY", "TXRH", "MUSA", "GWW", "FAST", "WSO",
    # ── Industrial compounders ─────────────────────────────────────────────
    "EME", "FIX", "LECO",
    # ── Cyclical-value semis ───────────────────────────────────────────────
    "MU", "ON", "SWKS",
    # ── Homebuilders ───────────────────────────────────────────────────────
    "DHI", "LEN", "PHM", "TOL",
    # ── Consumer quality ───────────────────────────────────────────────────
    "DECK", "WSM",
]

# Moderate niche growth: liquid, profitable (or near it), covered-but-not-
# saturated. Deliberately excludes the most speculative story stocks
# (COIN/RBLX/ROKU tier) — see CLAUDE.md on survivorship bias.
SLEEVE_NICHE_GROWTH: List[str] = [
    "CRWD", "NET", "DDOG", "FTNT", "ZS", "AXON", "MDB", "TTD", "HUBS",
    "SNOW", "PLTR", "SHOP", "SE", "SPOT", "CELH", "LULU", "CMG",
    "KLAC", "AMAT", "LRCX", "MRVL", "NXPI",
]

# Global (ex-US) exposure via US-listed ADRs ONLY — native listings (.L,
# .T, .DE …) break Alpha Vantage sentiment and yfinance fundamentals, and
# LSE quotes are in pence. ADRs keep every data layer working and in USD.
SLEEVE_GLOBAL: List[str] = [
    # ── Europe ─────────────────────────────────────────────────────────────
    "ASML", "SAP", "NVO", "AZN", "GSK", "SNY", "SHEL", "BP", "TTE", "UL",
    "RIO",
    # European value (Lightman holdings) via OTC ADRs — cheap + high ROE, but
    # thin Alpha Vantage sentiment coverage, so they lean on fundamentals.
    "RHHBY", "NSRGY", "DANOY", "KKPNY", "DHLGY",
    # ── Developed Asia-Pacific ─────────────────────────────────────────────
    "SONY", "TM", "BHP",
]
# NOTE: TSM/BABA/INFY/MELI/NU/VALE used to live here. They moved to
# SLEEVE_EM so the EM-specific risk gates (country cap, volatility-adjusted
# momentum) apply only to genuine emerging markets and not to developed
# ex-US names like ASML or Toyota. Ticker symbols are unchanged, so banked
# Alpha Vantage sentiment history for them is untouched.

# Emerging markets via US-listed ADRs ONLY (same rule as SLEEVE_GLOBAL —
# native listings break Alpha Vantage sentiment + yfinance fundamentals).
# Liquid large/mid caps first, per the EM guidance: frontier and illiquid
# names come later, if ever.
#
# Deliberate omissions despite being obvious EM bellwethers: Tencent (TCEHY)
# and Samsung (SSNLF) have no liquid US ADR — both trade on pink sheets with
# stale/erratic quotes, which is exactly the data-quality failure the
# ADR-only rule exists to prevent. Their exposure comes indirectly through
# the Taiwan/Korea semis and the China platform names below.
SLEEVE_EM: List[str] = [
    # ── Taiwan ─────────────────────────────────────────────────────────────
    "TSM", "UMC", "ASX", "CHT",
    # ── China ──────────────────────────────────────────────────────────────
    "BABA", "PDD", "TCOM", "YUMC",
    # ── India ──────────────────────────────────────────────────────────────
    "HDB", "IBN", "INFY",
    # ── South Korea ────────────────────────────────────────────────────────
    "KB", "SHG",
    # ── Latin America ──────────────────────────────────────────────────────
    "MELI", "NU", "VALE", "GGB", "BAP", "SQM",
    # ERJ (Embraer) was selected but DROPPED: yfinance returns
    # YFTzMissingError for ERJ, ERJ.SA and EMBR3.SA alike, so there is no
    # free price series for it despite the company trading normally. Re-add
    # if the upstream data gap is ever fixed.
    "ITUB", "PBR",           # Brazil — the two most liquid LatAm ADRs
    "AMX", "FMX",            # Mexico
    "CIB",                   # Colombia
    # ── Africa ─────────────────────────────────────────────────────────────
    "GFI",                   # South Africa
]

SLEEVES: Dict[str, List[str]] = {
    "core":          SLEEVE_CORE,
    "quality_value": SLEEVE_QUALITY_VALUE,
    "niche_growth":  SLEEVE_NICHE_GROWTH,
    "global":        SLEEVE_GLOBAL,
    "em":            SLEEVE_EM,
}

# Ticker -> sleeve name, for screener views and fetch prioritisation.
TICKER_SLEEVE: Dict[str, str] = {
    t: name for name, ts in SLEEVES.items() for t in ts
}


def av_fetch_order() -> List[str]:
    """Ticker order for the daily Alpha Vantage budget: quality-value and
    niche sleeves first — sentiment history is worth most where coverage is
    thinnest — then EM, then global ADRs, then core (whose completed tickers
    cost nothing anyway).

    EM has zero banked history so it is the thinnest sleeve of all, but it sits
    BEHIND quality_value/niche deliberately: those two gate the separate
    sentiment-overlay A/B (see scripts/coverage_check.py), and jumping EM ahead
    would stall that for weeks. The EM A/B is momentum-only, so it does not
    wait on sentiment coverage."""
    return (SLEEVE_QUALITY_VALUE + SLEEVE_NICHE_GROWTH
            + SLEEVE_EM + SLEEVE_GLOBAL + SLEEVE_CORE)


@dataclass
class UniverseConfig:
    # Full five-sleeve universe (~156 names). Edit the sleeve lists above.
    tickers: List[str] = field(default_factory=lambda: (
        SLEEVE_CORE + SLEEVE_QUALITY_VALUE
        + SLEEVE_NICHE_GROWTH + SLEEVE_GLOBAL + SLEEVE_EM
    ))
    benchmark_ticker: str = "SPY"          # free ETF proxy for the market
    # EM comparison benchmarks (free ETFs). EMXC/FRDM exclude China, which is
    # the main axis of dispersion across EM funds — worth reporting separately
    # rather than judging an EM sleeve against SPY alone.
    em_benchmark_tickers: List[str] = field(
        default_factory=lambda: ["EEM", "EMXC", "FRDM"])
    # Price window. end_date is dynamic (today) so the screener always shows
    # current prices — a hardcoded end once left the app 7 months stale.
    start_date: str = "2015-01-01"
    end_date: str = field(
        default_factory=lambda: _dt.date.today().isoformat())


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
    long_ma: int = 200               # long-trend filter MA (200d = institutional standard)
    breadth_ma: int = 200            # MA used for market-breadth regime
    # Market-regime detector: "breadth" (fraction of universe above its long
    # MA — free, simple, default) or "hmm" (3-state Gaussian HMM on market
    # return/vol/dispersion, walk-forward refit — needs `pip install hmmlearn`,
    # falls back to breadth if unavailable). See src/regime.py.
    regime_method: str = "breadth"
    # CHANGE SET 3 (Blitz/Huij/Martens 2011, Residual Momentum). When True,
    # rank on factor-residual momentum instead of raw TSM. Default False =
    # existing behaviour (spec suggests enabling; kept off for reproducibility).
    use_residual_momentum: bool = False
    # EM guidance §9: rank on return/vol rather than raw return, because
    # emerging-market and small-cap momentum is noisier than US large-cap
    # momentum. Applied to RANKING ONLY, never to the `trend_tsm_min` gate —
    # that threshold is denominated in return units (0.05 == "5% trailing
    # return") and would mean something entirely different against a
    # return/vol ratio. Default False = existing behaviour.
    use_vol_adjusted_momentum: bool = False


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
    trend_tsm_min: float = 0.05         # 12m return > 5% (a real winner, not barely positive)
    near_floor_52w: float = 0.75        # within 25% of 52w high  (tighter uptrend)
    require_above_long_ma: bool = True  # close > long_ma         (trend confirmation)
    rsi_pullback_max: float = 50.0      # RSI below this = a dip we can buy ...
    rsi_pullback_min: float = 30.0      # ... but above this, so we don't catch crashes
    long_sentiment_min: float = 0.0     # news score must be >= this for a LONG

    # ---- SHORT gate (optional; off by default for a free, long-biased model) ----
    enable_shorts: bool = False
    loser_tsm_max: float = 0.0
    short_ratio_52w_max: float = 0.85
    rsi_bounce_min: float = 55.0
    short_sentiment_max: float = -0.05

    # ---- Ranking when there are more candidates than slots ----
    rank_sentiment_weight: float = 0.3  # momentum leads, noisy free sentiment confirms

    # ---- CHANGE SET 5 (Gray & Vogel 2016, Quantitative Momentum) ----
    # "Path of momentum" quality gate: min fraction of positive monthly returns
    # over the formation window. Spec suggests 0.55; default 0.0 = no filtering
    # (preserves existing behaviour per the final-instruction reproducibility rule).
    momentum_quality_min: float = 0.0

    # ---- CHANGE SET 6 (Chen/Chou/Hsieh, Consistent Momentum) ----
    # Require this rebalance's longs to be either held last rebalance too
    # (consistent winners) or fresh names in the top X% by momentum. Spec
    # suggests True; default False preserves existing behaviour.
    require_consistent_momentum: bool = False
    consistent_momentum_top_pct: float = 0.30


# ──────────────────────────────────────────────────────────────────────────
# Portfolio / backtest mechanics
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class PortfolioConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 15              # 15 (was 10) spreads single-name risk
    max_gross_short: float = 0.30        # 30% gross short cap
    rebalance: str = "M"                 # monthly
    use_inverse_vol_weights: bool = True # size longs ~ 1/realised vol (else equal)
    transaction_cost_bps: float = 10.0   # 10 bps per unit turnover
    execution_delay_days: int = 1        # T+1 (no look-ahead)
    use_breadth_regime: bool = True      # scale exposure with market breadth
    # CHANGE SET 1 (Barroso & Santa-Clara 2015, Momentum Has Its Moments):
    # portfolio-level volatility targeting. Spec suggests True; defaults False
    # per the final-instruction rule that defaults preserve existing behaviour.
    use_vol_targeting: bool = False
    vol_target_pct: float = 12.0         # annualised vol target when enabled
    # CHANGE SET 2 (Daniel & Moskowitz 2016, Momentum Crashes): cap long gross
    # at 0.3 when crash risk is elevated (bear market + rebound beginning).
    use_crash_risk_filter: bool = False
    # EM guidance §9: cap any single country's share of gross long exposure, so
    # one region's macro or policy shock (a China delisting scare, a Brazilian
    # election) can't take the whole book with it. Applies to NON-US countries
    # only — capping the US at 20% would rewrite the strategy rather than add
    # an EM risk gate.
    #
    # Default TRUE after the A/B (scripts/em_ab_test.py, 2016-2026): the Sharpe
    # gain is noise (+0.009), but the tail protection is not — unconstrained,
    # Brazil reached 100% of gross long and China 31.5% in isolated months. It
    # binds on only ~1.8% of days and never changes trade SELECTION (identical
    # trade count, win rate, avg win and avg loss with it on) — it only
    # reweights. Cheap insurance against a single-country blowup.
    use_country_cap: bool = True
    max_country_weight: float = 0.20

    # ---- LIVE EXECUTION ONLY (src/executor.py) — the backtest ignores this ----
    # Minimum trade size, as a fraction of book value. The executor used to fire
    # an order on any delta above 0.01 SHARES, so ordinary daily price drift
    # generated round-trips that were pure spread. 0.5% of a £50k book ≈ £250.
    # Full exits (target weight 0) bypass this — otherwise dust accumulates
    # permanently.
    #
    # Note the REBALANCE CADENCE is deliberately NOT a separate setting: the bot
    # derives it from `rebalance` above, so the backtest and live trading can
    # never silently diverge again (they had — backtest monthly, bot daily).
    min_trade_pct_of_book: float = 0.005


@dataclass
class BacktestConfig:
    # CHANGE SET 4 (Lopez de Prado 2018, ch.7): purged walk-forward folds.
    wf_n_folds: int = 6
    wf_embargo_days: int = 10
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

# Ticker -> sector, used for screener filtering and sector-relative views.
# Mirrors the groupings of UniverseConfig.tickers above — keep in sync.
SECTORS: Dict[str, str] = {
    **{t: "Tech" for t in [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX",
        "AMD", "ORCL", "ADBE", "CRM", "NOW", "UBER", "AVGO", "QCOM", "TXN",
        "CSCO", "IBM", "INTC"]},
    **{t: "Financials" for t in [
        "JPM", "BAC", "GS", "V", "MA", "AXP", "MS", "C", "WFC", "BLK",
        "SCHW", "TRV", "CB", "AFL", "ALL", "MET"]},
    **{t: "Healthcare" for t in [
        "JNJ", "MRK", "UNH", "LLY", "ABBV", "AMGN", "BMY", "GILD", "VRTX",
        "MCK", "COR", "CAH", "CI", "ELV", "RHHBY"]},
    **{t: "Consumer" for t in [
        "HD", "MCD", "KO", "PG", "WMT", "NKE", "DIS", "COST", "CMG", "LULU",
        "AZO", "ORLY", "CASY", "TXRH", "MUSA", "DECK", "WSM",
        "NSRGY", "DANOY"]},
    **{t: "Energy" for t in ["CVX", "XOM", "COP", "EOG"]},
    **{t: "Industrials" for t in [
        "CAT", "HON", "GE", "BA", "RTX", "LMT", "DE", "VZ",
        "GWW", "FAST", "WSO", "EME", "FIX", "LECO",
        "DHI", "LEN", "PHM", "TOL", "KKPNY", "DHLGY"]},
    **{t: "Semis" for t in [
        "KLAC", "AMAT", "LRCX", "MRVL", "NXPI", "MU", "ON", "SWKS",
        "ASML", "TSM"]},
    **{t: "Growth" for t in [
        "CRWD", "NET", "DDOG", "FTNT", "ZS", "AXON", "MDB", "CELH", "TTD",
        "SPOT", "HUBS", "SNOW", "PLTR", "SHOP", "SE", "MELI", "NU"]},
    **{t: "Tech" for t in ["SAP", "INFY"]},
    **{t: "Healthcare" for t in ["NVO", "AZN", "GSK", "SNY"]},
    **{t: "Energy" for t in ["SHEL", "BP", "TTE"]},
    **{t: "Consumer" for t in ["UL", "TM", "SONY", "BABA"]},
    **{t: "Materials" for t in ["RIO", "BHP", "VALE"]},
    # ── EM sleeve ──────────────────────────────────────────────────────────
    **{t: "Financials" for t in ["HDB", "IBN", "KB", "SHG", "BAP", "ITUB", "CIB"]},
    **{t: "Semis" for t in ["UMC", "ASX"]},
    **{t: "Tech" for t in ["CHT", "AMX"]},
    **{t: "Growth" for t in ["PDD", "TCOM"]},
    **{t: "Consumer" for t in ["YUMC", "FMX"]},
    **{t: "Materials" for t in ["GGB", "SQM", "GFI"]},
    **{t: "Energy" for t in ["PBR"]},
}

# Ticker -> country of primary economic exposure, for the optional country cap
# (PortfolioConfig.use_country_cap). Only EM names need entries — everything
# else resolves to "US" via .get(t, "US"), which is what keeps the cap from
# binding on the developed book. Note these are exposure labels, not domiciles:
# NU is Cayman-incorporated but a Brazilian bank, and MELI is Uruguay-HQ but
# indexed as Argentina.
COUNTRIES: Dict[str, str] = {
    **{t: "Taiwan" for t in ["TSM", "UMC", "ASX", "CHT"]},
    **{t: "China" for t in ["BABA", "PDD", "TCOM", "YUMC"]},
    **{t: "India" for t in ["HDB", "IBN", "INFY"]},
    **{t: "South Korea" for t in ["KB", "SHG"]},
    **{t: "Brazil" for t in ["NU", "VALE", "GGB", "ITUB", "PBR"]},
    **{t: "Mexico" for t in ["AMX", "FMX"]},
    **{t: "Argentina" for t in ["MELI"]},
    **{t: "Chile" for t in ["SQM"]},
    **{t: "Peru" for t in ["BAP"]},
    **{t: "Colombia" for t in ["CIB"]},
    **{t: "South Africa" for t in ["GFI"]},
}

# Ticker -> human-readable company name (shared by both UIs).
TICKER_NAMES: Dict[str, str] = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta Platforms",
    "TSLA": "Tesla", "NFLX": "Netflix", "AMD": "AMD",
    "ORCL": "Oracle", "ADBE": "Adobe", "CRM": "Salesforce",
    "NOW": "ServiceNow", "UBER": "Uber", "AVGO": "Broadcom",
    "QCOM": "Qualcomm", "TXN": "Texas Instruments", "CSCO": "Cisco",
    "IBM": "IBM", "INTC": "Intel",
    "JPM": "JPMorgan", "BAC": "Bank of America", "GS": "Goldman Sachs",
    "V": "Visa", "MA": "Mastercard", "AXP": "American Express",
    "MS": "Morgan Stanley", "C": "Citigroup", "WFC": "Wells Fargo",
    "BLK": "BlackRock", "SCHW": "Charles Schwab", "TRV": "Travelers",
    "JNJ": "Johnson & Johnson", "MRK": "Merck", "UNH": "UnitedHealth",
    "LLY": "Eli Lilly", "ABBV": "AbbVie", "AMGN": "Amgen",
    "GILD": "Gilead", "VRTX": "Vertex", "BMY": "Bristol Myers",
    "HD": "Home Depot", "MCD": "McDonald's", "KO": "Coca-Cola",
    "PG": "Procter & Gamble", "WMT": "Walmart", "NKE": "Nike",
    "DIS": "Disney", "COST": "Costco", "CMG": "Chipotle",
    "LULU": "Lululemon",
    "CVX": "Chevron", "XOM": "ExxonMobil", "COP": "ConocoPhillips",
    "EOG": "EOG Resources",
    "CAT": "Caterpillar", "HON": "Honeywell", "GE": "GE Aerospace",
    "BA": "Boeing", "RTX": "RTX Corp", "LMT": "Lockheed Martin",
    "DE": "John Deere", "VZ": "Verizon",
    "KLAC": "KLA Corp", "AMAT": "Applied Materials", "LRCX": "Lam Research",
    "MRVL": "Marvell", "NXPI": "NXP Semiconductors",
    "CRWD": "CrowdStrike", "NET": "Cloudflare", "DDOG": "Datadog",
    "FTNT": "Fortinet", "ZS": "Zscaler", "AXON": "Axon Enterprise",
    "MDB": "MongoDB", "CELH": "Celsius Holdings", "TTD": "Trade Desk",
    "SPOT": "Spotify", "HUBS": "HubSpot", "SNOW": "Snowflake",
    "PLTR": "Palantir", "SHOP": "Shopify", "SE": "Sea Limited",
    "MCK": "McKesson", "COR": "Cencora", "CAH": "Cardinal Health",
    "CI": "Cigna", "ELV": "Elevance Health",
    "CB": "Chubb", "AFL": "Aflac", "ALL": "Allstate", "MET": "MetLife",
    "AZO": "AutoZone", "ORLY": "O'Reilly Auto", "CASY": "Casey's",
    "TXRH": "Texas Roadhouse", "MUSA": "Murphy USA",
    "GWW": "Grainger", "FAST": "Fastenal", "WSO": "Watsco",
    "EME": "EMCOR Group", "FIX": "Comfort Systems", "LECO": "Lincoln Electric",
    "MU": "Micron", "ON": "onsemi", "SWKS": "Skyworks",
    "DHI": "D.R. Horton", "LEN": "Lennar", "PHM": "PulteGroup",
    "TOL": "Toll Brothers", "DECK": "Deckers", "WSM": "Williams-Sonoma",
    "ASML": "ASML Holding", "SAP": "SAP SE", "NVO": "Novo Nordisk",
    "AZN": "AstraZeneca", "GSK": "GSK plc", "SNY": "Sanofi",
    "SHEL": "Shell", "BP": "BP plc", "TTE": "TotalEnergies",
    "UL": "Unilever", "RIO": "Rio Tinto",
    "TSM": "TSMC", "SONY": "Sony", "TM": "Toyota", "BABA": "Alibaba",
    "INFY": "Infosys", "BHP": "BHP Group",
    "MELI": "MercadoLibre", "NU": "Nu Holdings", "VALE": "Vale",
    "RHHBY": "Roche", "NSRGY": "Nestle", "DANOY": "Danone",
    "KKPNY": "KPN", "DHLGY": "DHL Group",
    # ── EM sleeve ──────────────────────────────────────────────────────────
    "UMC": "United Microelectronics", "ASX": "ASE Technology",
    "CHT": "Chunghwa Telecom", "PDD": "PDD Holdings",
    "TCOM": "Trip.com", "YUMC": "Yum China",
    "HDB": "HDFC Bank", "IBN": "ICICI Bank",
    "KB": "KB Financial", "SHG": "Shinhan Financial",
    "GGB": "Gerdau", "BAP": "Credicorp",
    "SQM": "Sociedad Quimica y Minera", "ITUB": "Itau Unibanco",
    "PBR": "Petrobras", "AMX": "America Movil",
    "FMX": "FEMSA", "CIB": "Bancolombia", "GFI": "Gold Fields",
}

# Ticker -> name variants used to attribute free headlines to a stock.
COMPANY_KEYWORDS: Dict[str, List[str]] = {
    # ── Mega-cap tech ──────────────────────────────────────────────────────────
    "AAPL":  ["apple", "iphone", "tim cook", "app store"],
    "MSFT":  ["microsoft", "azure", "satya nadella", "windows", "copilot"],
    "GOOGL": ["google", "alphabet", "android", "sundar pichai", "youtube", "gemini"],
    "AMZN":  ["amazon", "aws", "andy jassy", "prime"],
    "NVDA":  ["nvidia", "jensen huang", "cuda", "h100", "blackwell"],
    "META":  ["meta", "facebook", "instagram", "zuckerberg", "whatsapp", "threads"],
    "TSLA":  ["tesla", "elon musk", "cybertruck", "model 3", "model y", "model s"],
    "NFLX":  ["netflix", "reed hastings", "streaming"],
    "AMD":   ["amd", "advanced micro devices", "lisa su", "ryzen", "epyc"],
    "ORCL":  ["oracle", "larry ellison", "cloud infrastructure"],
    "ADBE":  ["adobe", "photoshop", "creative cloud", "firefly"],
    "CRM":   ["salesforce", "marc benioff", "slack"],
    "NOW":   ["servicenow", "service now"],
    "UBER":  ["uber", "dara khosrowshahi", "uber eats"],
    "AVGO":  ["broadcom", "hock tan"],
    "QCOM":  ["qualcomm", "snapdragon"],
    "TXN":   ["texas instruments"],
    "CSCO":  ["cisco"],
    "IBM":   ["ibm", "international business machines", "watsonx"],
    "INTC":  ["intel", "pat gelsinger", "foundry"],
    # ── Financials ─────────────────────────────────────────────────────────────
    "JPM":   ["jpmorgan", "jp morgan", "jamie dimon"],
    "BAC":   ["bank of america", "bofa"],
    "GS":    ["goldman sachs", "goldman"],
    "V":     ["visa"],
    "MA":    ["mastercard"],
    "AXP":   ["american express", "amex"],
    "MS":    ["morgan stanley"],
    "C":     ["citigroup", "citibank", "citi group"],
    "WFC":   ["wells fargo"],
    "BLK":   ["blackrock", "larry fink", "aladdin"],
    "SCHW":  ["charles schwab", "schwab"],
    "TRV":   ["travelers companies", "travelers insurance"],
    "CB":    ["chubb"],
    "AFL":   ["aflac"],
    "ALL":   ["allstate"],
    "MET":   ["metlife"],
    # ── Healthcare / Biotech ───────────────────────────────────────────────────
    "JNJ":   ["johnson & johnson", "johnson and johnson", "j&j"],
    "MRK":   ["merck", "keytruda"],
    "UNH":   ["unitedhealth", "united health", "optum"],
    "LLY":   ["eli lilly", "lilly", "mounjaro", "tirzepatide", "zepbound"],
    "ABBV":  ["abbvie", "humira", "skyrizi", "rinvoq"],
    "AMGN":  ["amgen", "repatha"],
    "GILD":  ["gilead", "gilead sciences", "biktarvy"],
    "VRTX":  ["vertex pharmaceuticals", "vertex pharma", "trikafta"],
    "BMY":   ["bristol myers squibb", "bristol-myers", "opdivo"],
    "MCK":   ["mckesson"],
    "COR":   ["cencora", "amerisourcebergen"],
    "CAH":   ["cardinal health"],
    "CI":    ["cigna"],
    "ELV":   ["elevance", "elevance health", "anthem blue cross"],
    # ── Consumer ───────────────────────────────────────────────────────────────
    "HD":    ["home depot"],
    "MCD":   ["mcdonald", "mcdonald's", "big mac"],
    "KO":    ["coca-cola", "coca cola", "coke"],
    "PG":    ["procter & gamble", "procter and gamble", "p&g"],
    "WMT":   ["walmart"],
    "NKE":   ["nike"],
    "DIS":   ["disney", "walt disney", "espn", "disney+"],
    "COST":  ["costco"],
    "CMG":   ["chipotle"],
    "LULU":  ["lululemon"],
    "AZO":   ["autozone"],
    "ORLY":  ["o'reilly automotive", "oreilly automotive", "o'reilly auto"],
    "CASY":  ["casey's general", "caseys general"],
    "TXRH":  ["texas roadhouse"],
    "MUSA":  ["murphy usa"],
    "DECK":  ["deckers", "hoka", "ugg"],
    "WSM":   ["williams-sonoma", "williams sonoma", "pottery barn"],
    # ── Energy ─────────────────────────────────────────────────────────────────
    "CVX":   ["chevron"],
    "XOM":   ["exxon", "exxonmobil"],
    "COP":   ["conocophillips", "conoco phillips"],
    "EOG":   ["eog resources"],
    # ── Industrials ────────────────────────────────────────────────────────────
    "CAT":   ["caterpillar"],
    "HON":   ["honeywell"],
    "GE":    ["general electric", "ge aerospace", "ge vernova"],
    "BA":    ["boeing", "737 max", "starliner"],
    "RTX":   ["raytheon", "rtx", "pratt & whitney", "collins aerospace"],
    "LMT":   ["lockheed martin", "f-35"],
    "DE":    ["deere", "john deere"],
    "VZ":    ["verizon"],
    "GWW":   ["w.w. grainger", "ww grainger", "grainger"],
    "FAST":  ["fastenal"],
    "WSO":   ["watsco"],
    "EME":   ["emcor"],
    "FIX":   ["comfort systems"],
    "LECO":  ["lincoln electric"],
    "DHI":   ["d.r. horton", "dr horton"],
    "LEN":   ["lennar"],
    "PHM":   ["pultegroup", "pulte group", "pulte homes"],
    "TOL":   ["toll brothers"],
    # ── Semiconductors ─────────────────────────────────────────────────────────
    "KLAC":  ["kla corporation", "kla"],
    "AMAT":  ["applied materials"],
    "LRCX":  ["lam research"],
    "MRVL":  ["marvell technology", "marvell"],
    "NXPI":  ["nxp semiconductors", "nxp"],
    "MU":    ["micron"],
    "ON":    ["on semiconductor", "onsemi"],
    "SWKS":  ["skyworks"],
    # ── Mid/Small cap + high-growth underfollowed ──────────────────────────────
    "CRWD":  ["crowdstrike", "crowd strike", "falcon"],
    "NET":   ["cloudflare"],
    "DDOG":  ["datadog"],
    "FTNT":  ["fortinet"],
    "ZS":    ["zscaler"],
    "AXON":  ["axon enterprise", "taser", "axon body camera"],
    "MDB":   ["mongodb", "mongo db", "atlas database"],
    "CELH":  ["celsius holdings", "celsius energy drink"],
    "TTD":   ["trade desk", "the trade desk"],
    "SPOT":  ["spotify"],
    "HUBS":  ["hubspot"],
    "SNOW":  ["snowflake"],
    "PLTR":  ["palantir", "gotham", "foundry"],
    "SHOP":  ["shopify", "tobi lutke"],
    "SE":    ["sea limited", "shopee", "garena"],
    # ── Global ADRs ────────────────────────────────────────────────────────────
    "ASML":  ["asml", "euv lithography"],
    "SAP":   ["sap se", "sap software"],
    "NVO":   ["novo nordisk", "ozempic", "wegovy"],
    "AZN":   ["astrazeneca", "astra zeneca"],
    "GSK":   ["gsk", "glaxosmithkline", "glaxo"],
    "SNY":   ["sanofi", "dupixent"],
    "SHEL":  ["shell plc", "royal dutch shell"],
    "BP":    ["bp plc", "british petroleum"],
    "TTE":   ["totalenergies", "total energies"],
    "UL":    ["unilever"],
    "RIO":   ["rio tinto"],
    "TSM":   ["tsmc", "taiwan semiconductor"],
    "SONY":  ["sony", "playstation"],
    "TM":    ["toyota"],
    "BABA":  ["alibaba", "taobao", "tmall"],
    "INFY":  ["infosys"],
    "BHP":   ["bhp group", "bhp billiton"],
    "MELI":  ["mercadolibre", "mercado libre"],
    "NU":    ["nubank", "nu holdings"],
    "VALE":  ["vale s.a.", "vale sa", "vale mining"],
    # ── European value (Lightman holdings, OTC ADRs) ────────────────────────────
    "RHHBY": ["roche", "roche holding", "genentech"],
    "NSRGY": ["nestle", "nestle sa"],
    "DANOY": ["danone"],
    "KKPNY": ["kpn", "koninklijke kpn"],
    "DHLGY": ["dhl group", "deutsche post", "dhl express"],
    # ── EM sleeve ──────────────────────────────────────────────────────────
    "UMC":   ["united microelectronics", "umc"],
    "ASX":   ["ase technology", "advanced semiconductor engineering"],
    "CHT":   ["chunghwa telecom"],
    "PDD":   ["pdd holdings", "pinduoduo", "temu"],
    "TCOM":  ["trip.com", "ctrip", "skyscanner"],
    "YUMC":  ["yum china", "kfc china"],
    "HDB":   ["hdfc bank", "hdfc"],
    "IBN":   ["icici bank", "icici"],
    "KB":    ["kb financial", "kookmin bank"],
    "SHG":   ["shinhan financial", "shinhan bank"],
    "GGB":   ["gerdau"],
    "BAP":   ["credicorp", "banco de credito del peru"],
    "SQM":   ["sociedad quimica", "sqm lithium", "soquimich"],
    "ITUB":  ["itau unibanco", "itau", "itaú"],
    "PBR":   ["petrobras", "petroleo brasileiro"],
    "AMX":   ["america movil", "américa móvil", "telcel"],
    "FMX":   ["femsa", "fomento economico mexicano", "oxxo"],
    "CIB":   ["bancolombia"],
    "GFI":   ["gold fields"],
}

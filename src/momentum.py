"""
src/momentum.py — Module 1: the price engine (fully historical, free).

All functions take a wide price frame (index=Date, columns=tickers) and return
wide frames of the same shape, so signals compose cleanly downstream.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from config import CFG


def tsm(prices: pd.DataFrame, lookback: int | None = None,
        skip: int | None = None) -> pd.DataFrame:
    """
    Trailing N-day (default 12-month) simple return. >0 == 'winner'.
    `skip` drops the most recent days from the window ("12-1" momentum):
    the last month is dominated by short-term reversal, not continuation.
    """
    lookback = lookback or CFG.momentum.tsm_lookback
    skip = CFG.momentum.tsm_skip if skip is None else skip
    recent = prices.shift(skip) if skip > 0 else prices
    return recent / prices.shift(lookback) - 1


def residual_tsm(prices: pd.DataFrame, benchmark: pd.Series,
                 lookback: int | None = None, skip: int | None = None,
                 refit_every: int = 5) -> pd.DataFrame:
    """Blitz, Huij & Martens (2011), "Residual Momentum". Ranking on the
    residual of a factor regression instead of raw returns strips out market
    beta and size exposure, roughly doubling momentum's Sharpe with smaller
    crashes because the factor bets (not the stock-picking) drive the tails.

    Per the paper, the score is the 12-1 window residual return STANDARDISED
    by its own standard deviation over the same window (an information ratio
    of residuals) — the prompt's raw "sum of residuals" is kept as the
    numerator, with the paper's standardisation as the denominator.
    Regressors: market (SPY daily return) and a size proxy (equal-weight
    universe return minus SPY). A value/HML proxy would be a static 0.0
    series on free data (no daily HML factor), which is rank-deficient in
    OLS, so it is intentionally omitted — noted per the prompt.
    Uses numpy lstsq (no statsmodels dependency); refits every `refit_every`
    days for tractability since betas move slowly and the signal is only read
    at monthly rebalances.
    """
    lookback = lookback or CFG.momentum.tsm_lookback
    skip = CFG.momentum.tsm_skip if skip is None else skip

    rets = prices.pct_change()
    mkt = benchmark.reindex(prices.index).pct_change()
    size = rets.mean(axis=1) - mkt              # equal-weight universe minus SPY
    X_all = np.column_stack([np.ones(len(prices)), mkt.values, size.values])

    out = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    for t in prices.columns:
        y_all = rets[t].values
        col = np.full(len(prices), np.nan)
        for i in range(lookback, len(prices), refit_every):
            y = y_all[i - lookback + 1: i + 1]
            X = X_all[i - lookback + 1: i + 1]
            ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
            if ok.sum() < int(lookback * 0.8):
                continue
            coef, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
            resid = y[ok] - X[ok] @ coef
            window = resid[:-skip] if skip > 0 else resid
            sd = window.std()
            if sd > 0:
                col[i] = window.sum() / (sd * np.sqrt(len(window)))
        out[t] = pd.Series(col, index=prices.index).ffill(limit=refit_every)
    return out


def momentum_quality(prices: pd.DataFrame, lookback: int | None = None,
                     skip: int | None = None) -> pd.DataFrame:
    """Gray & Vogel (2016), "Quantitative Momentum" — the path-of-momentum
    quality filter (their "frog in the pan" idea): smooth momentum built from
    many small positive months persists, while the same total return earned in
    one giant month tends to revert. Returns the fraction (0..1) of the ~11
    monthly returns in the 12-1 formation window that were positive, per the
    prompt's monthly formulation.
    """
    lookback = lookback or CFG.momentum.tsm_lookback
    skip = CFG.momentum.tsm_skip if skip is None else skip
    n_months = max(1, (lookback - skip) // 21)
    base = prices.shift(skip) if skip > 0 else prices

    pos_sum = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    valid = pd.DataFrame(0, index=prices.index, columns=prices.columns)
    for k in range(n_months):
        r = base.shift(21 * k) / base.shift(21 * (k + 1)) - 1
        pos_sum += (r > 0).astype(float)
        valid += r.notna().astype(int)
    frac = pos_sum / valid.replace(0, np.nan)
    return frac.where(valid == n_months)   # need the full formation window


def ratio_52w(prices: pd.DataFrame, window: int | None = None) -> pd.DataFrame:
    """price / rolling max  -> proximity to the 52-week high (0..1+)."""
    window = window or CFG.momentum.high_52w_window
    roll_max = prices.rolling(window, min_periods=window // 2).max()
    return prices / roll_max


def rsi(prices: pd.DataFrame, period: int | None = None) -> pd.DataFrame:
    """Wilder's RSI per column."""
    period = period or CFG.momentum.rsi_period
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def moving_average(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    return prices.rolling(window, min_periods=max(2, window // 2)).mean()


def realised_vol(prices: pd.DataFrame, window: int | None = None) -> pd.DataFrame:
    """Rolling std of daily returns — used for inverse-vol position sizing."""
    window = window or CFG.momentum.vol_lookback
    return prices.pct_change().rolling(window, min_periods=window // 2).std()


def macd_hist(prices: pd.DataFrame, fast: int = 12, slow: int = 26,
              signal: int = 9) -> pd.DataFrame:
    """
    MACD histogram (MACD line − signal line), pure pandas — always available,
    no pandas-ta needed. Normalised by price so it's comparable across a
    $20 stock and a $900 stock (a raw MACD is in price units).
    """
    ema_fast = prices.ewm(span=fast, min_periods=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, min_periods=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal, adjust=False).mean()
    return (macd_line - signal_line) / prices


def breadth_regime(
    prices: pd.DataFrame,
    ma_window: int | None = None,
    risk_on: float = 0.65,
    risk_off: float = 0.45,
) -> pd.Series:
    """
    Free, historical market-regime proxy: the fraction of the universe trading
    above its long MA. >risk_on -> 'risk_on', <risk_off -> 'risk_off', else
    'neutral'. Used to scale exposure in the backtest (no sentiment needed).

    Breadth deteriorates slowly (weeks) at the start of a crash, but realised
    volatility spikes immediately, so a cross-sectional vol-spike detector is
    layered on top: if the universe's average 20-day realised vol jumps above
    2.5x its own trailing-year median, force risk_off regardless of breadth.
    This catches events like March 2020 far earlier.
    """
    ma_window = ma_window or CFG.momentum.breadth_ma
    ma = moving_average(prices, ma_window)
    above = (prices > ma)
    frac = above.sum(axis=1) / above.notna().sum(axis=1).replace(0, np.nan)

    rv_20 = prices.pct_change().rolling(20).std().mean(axis=1)
    rv_baseline = rv_20.rolling(252, min_periods=60).median()
    vol_spike = (rv_20 > rv_baseline * 2.5).fillna(False)

    regime = pd.Series("neutral", index=prices.index, name="regime")
    regime[frac >= risk_on] = "risk_on"
    regime[frac <= risk_off] = "risk_off"
    regime[vol_spike] = "risk_off"        # vol spike overrides breadth
    return regime


# ──────────────────────────────────────────────────────────────────────────
# Extended technicals (pandas-ta, optional)
# ──────────────────────────────────────────────────────────────────────────
def build_technicals(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Compute a targeted set of pandas-ta indicators for every ticker:
    MACD, Bollinger %B, ATR, Stochastic %K, OBV, 10-day Momentum.
    Returns a dict of wide DataFrames (index=Date, columns=tickers).

    This intentionally computes ONLY the indicators the scoring layer uses —
    running pandas-ta's "all" strategy (130+ indicators) took minutes per
    100-ticker universe and threw >95% of the output away.

    OHLCV is approximated from close-only data — open/high/low are synthetic
    so volume-dependent indicators like OBV are directionally useful but not
    precise. MACD and momentum indicators (close-based) are accurate.
    """
    import pandas_ta as ta  # optional dependency

    # Collect per-indicator series and concat ONCE at the end — inserting
    # columns one at a time fragments the frame (PerformanceWarning spam and
    # a real slowdown at 100+ tickers).
    cols: dict[str, dict[str, pd.Series]] = {}

    def _put(name: str, ticker: str, series: pd.Series) -> None:
        cols.setdefault(name, {})[ticker] = series

    for ticker in prices.columns:
        close = prices[ticker]
        if close.dropna().shape[0] < 40:
            continue
        high = close.rolling(2).max().fillna(close)
        low = close.rolling(2).min().fillna(close)
        volume = pd.Series(1e6, index=close.index)  # placeholder — direction only
        try:
            macd = ta.macd(close, fast=12, slow=26, signal=9)
            if macd is not None and "MACD_12_26_9" in macd:
                _put("MACD_12_26_9", ticker, macd["MACD_12_26_9"])

            bbands = ta.bbands(close, length=5, std=2.0)
            if bbands is not None:
                bbp = [c for c in bbands.columns if c.startswith("BBP_")]
                if bbp:
                    _put("BBP_5_2.0", ticker, bbands[bbp[0]])

            atr = ta.atr(high, low, close, length=14, percent=True)
            if atr is not None:
                _put("ATRr_14", ticker, atr)

            stoch = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
            if stoch is not None and "STOCHk_14_3_3" in stoch:
                _put("STOCHk_14_3_3", ticker, stoch["STOCHk_14_3_3"])

            obv = ta.obv(close, volume)
            if obv is not None:
                _put("OBV", ticker, obv)

            mom = ta.mom(close, length=10)
            if mom is not None:
                _put("MOM_10", ticker, mom)
        except Exception as e:
            print(f"[momentum] pandas-ta skipped {ticker}: {e}")
            continue
    return {name: pd.concat(d, axis=1).reindex(prices.index)
            for name, d in cols.items()}


def build_panels(prices: pd.DataFrame,
                 benchmark: pd.Series | None = None) -> dict[str, pd.DataFrame]:
    """
    Compute every momentum panel once, return a dict of wide frames.

    Core keys (always present, stable API — do not rename):
      tsm, ratio52, rsi, ma_long, ma_short, vol, above_long_ma, regime,
      macd_hist, momentum_quality, crash_risk, residual_tsm
    `benchmark` (SPY prices) is optional to keep old call sites working:
    without it, crash_risk defaults to "normal" everywhere and residual_tsm
    falls back to the plain tsm panel.
    Optional keys (present only when pandas-ta is installed):
      MACD_12_26_9, BBP_5_2.0, ATRr_14, STOCHk_14_3_3, OBV, MOM_10
    """
    ma_long = moving_average(prices, CFG.momentum.long_ma)

    regime = breadth_regime(prices)
    if getattr(CFG.momentum, "regime_method", "breadth") == "hmm":
        try:
            from src.regime import hmm_regime
            regime = hmm_regime(prices)
        except Exception as e:
            print(f"[momentum] HMM regime unavailable ({e}) — using breadth.")

    tsm_panel = tsm(prices)

    # CHANGE SET 2 (Daniel & Moskowitz): crash-risk flag needs the benchmark.
    if benchmark is not None:
        from src.regime import daniel_moskowitz_crash_risk
        crash_risk = daniel_moskowitz_crash_risk(benchmark)
    else:
        crash_risk = pd.Series("normal", index=prices.index, name="crash_risk")

    # CHANGE SET 3 (Blitz/Huij/Martens): residual momentum. Only computed when
    # opted in (it is the one expensive panel — a rolling lstsq per ticker);
    # otherwise it falls back to plain tsm so the key is always present.
    if benchmark is not None and getattr(CFG.momentum, "use_residual_momentum", False):
        residual = residual_tsm(prices, benchmark)
    else:
        residual = tsm_panel

    panels: dict[str, pd.DataFrame] = {
        "tsm":              tsm_panel,
        "ratio52":          ratio_52w(prices),
        "rsi":              rsi(prices),
        "ma_long":          ma_long,
        "ma_short":         moving_average(prices, CFG.momentum.short_ma),
        "vol":              realised_vol(prices),
        "above_long_ma":    prices > ma_long,
        "regime":           regime,
        "macd_hist":        macd_hist(prices),
        "momentum_quality": momentum_quality(prices),   # CHANGE SET 5
        "crash_risk":       crash_risk,
        "residual_tsm":     residual,
    }
    try:
        panels.update(build_technicals(prices))
    except Exception as e:
        print(f"[momentum] pandas-ta extension skipped — {e}")
    return panels

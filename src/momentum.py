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
    risk_on: float = 0.60,
    risk_off: float = 0.40,
) -> pd.Series:
    """
    Free, historical market-regime proxy: the fraction of the universe trading
    above its long MA. >risk_on -> 'risk_on', <risk_off -> 'risk_off', else
    'neutral'. Used to scale exposure in the backtest (no sentiment needed).
    """
    ma_window = ma_window or CFG.momentum.breadth_ma
    ma = moving_average(prices, ma_window)
    above = (prices > ma)
    frac = above.sum(axis=1) / above.notna().sum(axis=1).replace(0, np.nan)
    regime = pd.Series("neutral", index=prices.index, name="regime")
    regime[frac >= risk_on] = "risk_on"
    regime[frac <= risk_off] = "risk_off"
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


def build_panels(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Compute every momentum panel once, return a dict of wide frames.

    Core keys (always present, stable API — do not rename):
      tsm, ratio52, rsi, ma_long, ma_short, vol, above_long_ma, regime,
      macd_hist (price-normalised MACD histogram, pure pandas)
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

    panels: dict[str, pd.DataFrame] = {
        "tsm":           tsm(prices),
        "ratio52":       ratio_52w(prices),
        "rsi":           rsi(prices),
        "ma_long":       ma_long,
        "ma_short":      moving_average(prices, CFG.momentum.short_ma),
        "vol":           realised_vol(prices),
        "above_long_ma": prices > ma_long,
        "regime":        regime,
        "macd_hist":     macd_hist(prices),
    }
    try:
        panels.update(build_technicals(prices))
    except Exception as e:
        print(f"[momentum] pandas-ta extension skipped — {e}")
    return panels

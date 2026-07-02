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


def build_panels(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute every momentum panel once, return a dict of wide frames."""
    return {
        "tsm":      tsm(prices),
        "ratio52":  ratio_52w(prices),
        "rsi":      rsi(prices),
        "ma_long":  moving_average(prices, CFG.momentum.long_ma),
        "ma_short": moving_average(prices, CFG.momentum.short_ma),
        "vol":      realised_vol(prices),
        "regime":   breadth_regime(prices),
    }

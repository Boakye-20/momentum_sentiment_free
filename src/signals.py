"""
src/signals.py — Module 3: combine momentum + sentiment into target weights.

THE KEY FIX vs the previous engine
----------------------------------
The old LONG rule required a stock to be *near its 52-week high* AND
*RSI <= 30 (oversold)* at the same instant. Those almost never co-occur
(a stock pinned at its highs is not in a steep sell-off), so it traded ~twice
in 11 years. Here the LONG rule expresses "a *pullback within* an uptrend":

  Trend  : 12m return > 0,  within 30% of the 52w high,  price > long MA
  Timing : RSI in a *pullback* band (e.g. 25–55), i.e. a dip, NOT a crash
  News   : sentiment >= 0 (optional; only when sentiment is available)

Those conditions co-occur regularly, so the strategy actually trades.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from config import CFG


def _at(frame: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    """Row at `date` (forward-filled to the last available trading day)."""
    idx = frame.index.get_indexer([date], method="ffill")[0]
    return frame.iloc[idx] if idx >= 0 else pd.Series(dtype=float)


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0


def _long_weights(longs: list[str], panels: dict, date: pd.Timestamp,
                  gross: float) -> pd.Series:
    """Inverse-realised-vol sizing across the selected longs (equal-weight
    fallback when vol is unavailable). Sum of weights == gross either way."""
    if CFG.portfolio.use_inverse_vol_weights and "vol" in panels:
        vol = _at(panels["vol"], date).reindex(longs)
        inv = 1.0 / vol.replace(0.0, np.nan)
        if inv.notna().all() and np.isfinite(inv).all():
            return gross * inv / inv.sum()
    return pd.Series(gross / len(longs), index=longs)


def weights_for_date(
    date: pd.Timestamp,
    prices: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
    sentiment: pd.Series | None = None,
    use_sentiment: bool = False,
) -> pd.Series:
    """
    Return a Series of target weights (index=tickers) for one rebalance date.
    Longs are positive, shorts negative. Gross long <= 1.0, gross short
    <= max_gross_short. Regime scales exposure when enabled.
    """
    sc, pc = CFG.signal, CFG.portfolio
    px      = _at(prices, date)
    tsm     = _at(panels["tsm"], date)
    ratio   = _at(panels["ratio52"], date)
    rsi     = _at(panels["rsi"], date)
    ma_long = _at(panels["ma_long"], date)
    tickers = prices.columns
    sent = (sentiment if sentiment is not None
            else pd.Series(0.0, index=tickers))

    # ── LONG gate ────────────────────────────────────────────────────────
    long_mask = (
        (tsm > sc.trend_tsm_min)
        & (ratio >= sc.near_floor_52w)
        & (rsi >= sc.rsi_pullback_min)
        & (rsi <= sc.rsi_pullback_max)
    )
    if sc.require_above_long_ma:
        long_mask &= (px > ma_long)
    if use_sentiment:
        long_mask &= (sent >= sc.long_sentiment_min)
    long_mask = long_mask.reindex(tickers).fillna(False)

    # ── SHORT gate (optional) ────────────────────────────────────────────
    short_mask = pd.Series(False, index=tickers)
    if sc.enable_shorts:
        short_mask = (
            (tsm < sc.loser_tsm_max)
            & (ratio <= sc.short_ratio_52w_max)
            & (px < ma_long)
            & (rsi >= sc.rsi_bounce_min)
        )
        if use_sentiment:
            short_mask &= (sent <= sc.short_sentiment_max)
        short_mask = short_mask.reindex(tickers).fillna(False)

    # ── Regime scaling (free, price-based breadth) ───────────────────────
    regime = _at(panels["regime"], date)
    regime = regime if isinstance(regime, str) else "neutral"
    long_gross, max_n = 1.0, pc.max_positions
    allow_shorts = sc.enable_shorts
    if pc.use_breadth_regime:
        if regime == "risk_off":
            long_gross, max_n, allow_shorts = 0.5, max(3, pc.max_positions // 2), allow_shorts
        elif regime == "neutral":
            allow_shorts = False

    # ── Rank & select longs ──────────────────────────────────────────────
    # z-score both terms so the blend weight means what it says (raw sentiment
    # lives in [-1, 1] while z-scores span ~[-2, 2], which silently halved the
    # effective sentiment weight).
    tilt = _zscore(sent[long_mask] if use_sentiment else ratio[long_mask])
    rank = (1 - sc.rank_sentiment_weight) * _zscore(tsm[long_mask]) \
         + sc.rank_sentiment_weight * tilt
    longs = rank.sort_values(ascending=False).head(max_n).index.tolist()

    weights = pd.Series(0.0, index=tickers)
    if longs:
        weights[longs] = _long_weights(longs, panels, date, long_gross)

    # ── Select shorts (capped) ───────────────────────────────────────────
    if allow_shorts and short_mask.any():
        shorts = (tsm[short_mask].sort_values()
                  .head(max(1, int(max_n * pc.max_gross_short))).index.tolist())
        if shorts:
            weights[shorts] = -min(pc.max_gross_short, long_gross) / len(shorts)

    return weights

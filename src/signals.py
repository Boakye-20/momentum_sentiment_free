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
    """Inverse-realised-vol sizing across the selected longs.

    Two fixes vs the old version: (1) a *partial* fallback — a ticker with
    missing/infinite vol is filled with the median inverse-vol, instead of the
    whole book silently collapsing to equal weight when a single name is bad;
    (2) a cap at 2x the equal weight, so a very low-vol name (a KO or MA) can't
    balloon to 20%+ of the book and turn one bad month into a large drawdown.
    Sum of weights == gross either way."""
    if not (CFG.portfolio.use_inverse_vol_weights and "vol" in panels):
        return pd.Series(gross / len(longs), index=longs)

    vol = _at(panels["vol"], date).reindex(longs)
    inv = (1.0 / vol.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
    median_inv = inv.median()
    inv = inv.fillna(median_inv if np.isfinite(median_inv) else 1.0)

    raw = gross * inv / inv.sum()
    cap = gross / len(longs) * 2.0
    capped = raw.clip(upper=cap)
    return gross * capped / capped.sum()


def weights_for_date(
    date: pd.Timestamp,
    prices: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
    sentiment: pd.Series | None = None,
    use_sentiment: bool = False,
    prev_top: list[str] | None = None,
) -> pd.Series:
    """
    Return a Series of target weights (index=tickers) for one rebalance date.
    Longs are positive, shorts negative. Gross long <= 1.0, gross short
    <= max_gross_short. Regime scales exposure when enabled.
    `prev_top` is last rebalance's selected longs, used by the optional
    consistent-momentum filter (Chen/Chou/Hsieh).
    """
    sc, pc = CFG.signal, CFG.portfolio
    px      = _at(prices, date)
    tsm     = _at(panels["tsm"], date)
    # CHANGE SET 3 (Blitz/Huij/Martens, Residual Momentum): opt in to ranking
    # and gating on factor-residual momentum instead of raw returns.
    if (getattr(CFG.momentum, "use_residual_momentum", False)
            and "residual_tsm" in panels):
        tsm = _at(panels["residual_tsm"], date)
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

    # CHANGE SET 5 (Gray & Vogel, Quantitative Momentum): path-of-momentum
    # quality gate — require a minimum fraction of positive monthly returns
    # in the formation window. Inactive at the default threshold of 0.0
    # (a NaN-safe explicit guard, so default results are unchanged).
    if (getattr(sc, "momentum_quality_min", 0.0) > 0
            and "momentum_quality" in panels):
        quality = _at(panels["momentum_quality"], date)
        long_mask &= (quality >= sc.momentum_quality_min) \
            .reindex(tickers).fillna(False)

    # CHANGE SET 6 (Chen/Chou/Hsieh, Consistent Momentum): a long candidate
    # must be a consistent winner (also selected last rebalance) OR a fresh
    # entrant with top-decile-strength momentum (top X% of universe by TSM),
    # filtering out one-big-month wonders that tend to revert.
    if (prev_top is not None
            and getattr(sc, "require_consistent_momentum", False)):
        thresh = tsm.quantile(1.0 - sc.consistent_momentum_top_pct)
        fresh_strong = (tsm >= thresh).reindex(tickers).fillna(False)
        held_before = pd.Series(
            [t in set(prev_top) for t in tickers], index=tickers)
        long_mask &= (held_before | fresh_strong)

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

    # CHANGE SET 2 (Daniel & Moskowitz, Momentum Crashes): when the market is
    # rebounding out of a bear (the classic momentum-crash setup), cap long
    # gross at 0.3 regardless of what the breadth regime says.
    if getattr(pc, "use_crash_risk_filter", False) and "crash_risk" in panels:
        crash = _at(panels["crash_risk"], date)
        if isinstance(crash, str) and crash == "elevated":
            long_gross = min(long_gross, 0.3)

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

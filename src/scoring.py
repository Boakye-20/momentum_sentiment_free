"""
src/scoring.py — Composite AI Score and plain-English action labels.

Takes a signals DataFrame (momentum + sentiment + fundamentals, one row per
ticker) and produces a 1–10 AI Score plus a BUY / HOLD / AVOID label.

Three layers blended with fixed weights:
  Technical    45% — trend strength, RSI pullback zone, 52w proximity,
                     long-MA confirmation, realised vol, MACD histogram
  Sentiment    25% — news score (VADER or Alpha Vantage) mapped to [0, 1]
  Fundamentals 30% — ROE, forward P/E, debt-equity, margins, growth

The blend is renormalised by the weights that actually had data: if the
fundamentals layer is entirely missing, the score is tech+sentiment over
their combined weight — NOT deflated toward zero. (The old behaviour made
the 6.5 BUY threshold unreachable whenever a layer was absent.)

Outputs per ticker:
  ai_score        1–10 composite
  action          BUY (>= 6.5) / HOLD / AVOID (< 3.5)
  tech_score      technical sub-score, 0–10 (NaN if no inputs)
  sent_score      sentiment sub-score, 0–10 (NaN if no inputs)
  fund_score      fundamentals sub-score, 0–10 (NaN if no inputs)
  value_score     valuation-only lens, 0–10 (NaN if no inputs) — NOT part
                  of the ai_score blend (fundamentals already include P/E);
                  a sort/filter axis for "quality that's also cheap"
  under_radar     True when fundamentals are strong, valuation is cheap,
                  news sentiment is quiet/negative AND the company is not a
                  mega-cap — the classic "good company, nobody excited"
                  rerating setup. The size cap matters: neutral sentiment
                  tone on a $1T name means positives/negatives netting out
                  under heavy coverage, not low attention (META once
                  qualified on tone alone, which is nonsense for a
                  mega-cap)
  rank_pct        percentile rank of ai_score across the universe (0–100)
  confidence_pct  share of the total blend weight backed by real data
"""

from __future__ import annotations
import numpy as np
import pandas as pd

W_TECH, W_SENT, W_FUND = 0.45, 0.25, 0.30
BUY_MIN, HOLD_MIN = 6.5, 3.5
UNDER_RADAR_MAX_MCAP = 2.0e11   # $200B — above this, "under the radar" is a misnomer


def _norm(series: pd.Series) -> pd.Series:
    """Min-max normalise to [0, 1]; 0.5 everywhere when empty/constant."""
    s = pd.to_numeric(series, errors="coerce")
    valid = s.dropna()
    if valid.empty or valid.nunique() <= 1:
        return pd.Series(0.5, index=series.index)
    mn, mx = valid.min(), valid.max()
    return ((s - mn) / (mx - mn)).clip(0, 1).fillna(0.5)


def _inv_norm(series: pd.Series) -> pd.Series:
    """Min-max normalise where LOWER is better (e.g. debt-equity, P/E)."""
    return 1.0 - _norm(series)


def _winsor_norm(series: pd.Series, lo: float = 0.05, hi: float = 0.95) -> pd.Series:
    """Min-max normalise after clipping to the [5th, 95th] percentile band —
    one outlier (a 900% mover, a P/E of 2000) no longer flattens everyone
    else's score into a narrow band."""
    s = pd.to_numeric(series, errors="coerce")
    valid = s.dropna()
    if valid.empty or valid.nunique() <= 1:
        return pd.Series(0.5, index=series.index)
    ql, qh = valid.quantile(lo), valid.quantile(hi)
    if ql == qh:
        return _norm(series)
    return ((s.clip(ql, qh) - ql) / (qh - ql)).clip(0, 1).fillna(0.5)


def _inv_winsor_norm(series: pd.Series) -> pd.Series:
    return 1.0 - _winsor_norm(series)


def _technical_layer(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """Weighted technical sub-score in [0,1] and the weight actually used.
    Sub-weights renormalise over the inputs present, so a missing MACD
    column doesn't cap the layer below 1.0."""
    score = pd.Series(0.0, index=df.index)
    used = 0.0
    if "mom_12m" in df.columns:
        score += _winsor_norm(df["mom_12m"]) * 0.30
        used += 0.30
    if "ratio_52w" in df.columns:
        score += _norm(df["ratio_52w"]) * 0.20
        used += 0.20
    if "rsi" in df.columns:
        # Peak reward in the 25–55 pullback band, fading to 0 at the extremes
        # — mirrors the LONG entry's "dip, not crash" timing. Absolute RSI
        # scale (not cross-sectional norm): 40 is the sweet spot.
        r = pd.to_numeric(df["rsi"], errors="coerce").fillna(50.0)
        score += (1.0 - ((r - 40.0).abs() / 40.0)).clip(0, 1) * 0.15
        used += 0.15
    if "above_long_ma" in df.columns:
        score += df["above_long_ma"].fillna(0).astype(float).clip(0, 1) * 0.15
        used += 0.15
    if "volatility" in df.columns:
        score += _inv_winsor_norm(df["volatility"]) * 0.10
        used += 0.10
    if "macd_hist" in df.columns:
        score += _winsor_norm(df["macd_hist"]) * 0.10
        used += 0.10
    elif "macd_signal" in df.columns:      # legacy column name
        score += _winsor_norm(df["macd_signal"]) * 0.10
        used += 0.10
    if used > 0:
        score = score / used
    return score.clip(0, 1), min(used / 1.0, 1.0)


def _sentiment_layer(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """News score in [-1, 1] mapped to [0, 1]. Layer inactive when absent
    or when every ticker is exactly 0 (i.e. no sentiment was ever logged)."""
    for col in ("sentiment_score", "sentiment"):
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().any() and not (s.fillna(0.0) == 0.0).all():
                return ((s.fillna(0.0) + 1.0) / 2.0).clip(0, 1), 1.0
    return pd.Series(np.nan, index=df.index), 0.0


def _fundamental_layer(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """Weighted fundamental sub-score in [0,1] and the weight actually used.
    Sub-weights renormalise over the columns present."""
    score = pd.Series(0.0, index=df.index)
    used = 0.0
    parts = [
        ("roe",              _winsor_norm,     0.25),
        ("pe_forward",       _inv_winsor_norm, 0.20),
        ("debt_equity",      _inv_winsor_norm, 0.15),
        ("gross_margin",     _norm,            0.15),
        ("revenue_growth",   _winsor_norm,     0.15),
        ("operating_margin", _norm,            0.10),
    ]
    for col, fn, w in parts:
        if col in df.columns and df[col].notna().any():
            score += fn(df[col]) * w
            used += w
    if used > 0:
        score = score / used
    return score.clip(0, 1), min(used / 1.0, 1.0)


def _value_layer(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """Pure-valuation sub-score in [0,1]: cheaper = higher, winsorised so a
    single distressed name doesn't compress everyone else. Sub-weights
    renormalise over the columns present."""
    score = pd.Series(0.0, index=df.index)
    used = 0.0
    parts = [
        ("pe_forward",    _inv_winsor_norm, 0.30),
        ("ev_ebitda",     _inv_winsor_norm, 0.25),
        ("price_to_book", _inv_winsor_norm, 0.20),
        ("ps_ratio",      _inv_winsor_norm, 0.15),
        ("peg_ratio",     _inv_winsor_norm, 0.10),
    ]
    for col, fn, w in parts:
        if col in df.columns and df[col].notna().any():
            score += fn(df[col]) * w
            used += w
    if used > 0:
        score = score / used
    return score.clip(0, 1), min(used / 1.0, 1.0)


def compute_ai_score(signals_df: pd.DataFrame,
                     technical_fn=None) -> pd.DataFrame:
    """
    Add ai_score (1–10), action, per-layer sub-scores, rank_pct and
    confidence_pct to a per-ticker signals DataFrame. Never raises on
    missing columns — the blend renormalises over whatever data exists.

    `technical_fn` swaps the technical layer for a candidate implementation
    with the same (score in [0,1], weight used) contract. Defaults to the
    shipping `_technical_layer`; it exists so research scripts
    (scripts/ai_score_layer_ab.py) can A/B a layer against forward returns
    without editing production scoring. Do not pass it from app code.
    """
    df = signals_df.copy()

    tech, tech_used = (technical_fn or _technical_layer)(df)
    sent, sent_used = _sentiment_layer(df)
    fund, fund_used = _fundamental_layer(df)

    # Effective weight of each layer = design weight × fraction of the layer
    # that had data. Blend over live weight only, so absent layers redistribute
    # instead of dragging everyone toward AVOID.
    w_t, w_s, w_f = W_TECH * tech_used, W_SENT * sent_used, W_FUND * fund_used
    live = w_t + w_s + w_f
    if live <= 0:
        raw = pd.Series(0.5, index=df.index)
    else:
        raw = (tech.fillna(0) * w_t + sent.fillna(0) * w_s
               + fund.fillna(0) * w_f) / live

    df["ai_score"] = (raw * 10).clip(1, 10).round(1)
    df["tech_score"] = (tech * 10).round(1) if tech_used > 0 else np.nan
    df["sent_score"] = (sent * 10).round(1) if sent_used > 0 else np.nan
    df["fund_score"] = (fund * 10).round(1) if fund_used > 0 else np.nan

    # Valuation lens + under-the-radar flag (quality + cheap + quiet news).
    # Missing sentiment counts as "quiet" via the neutral 5.0 fill, but the
    # flag needs BOTH real fundamentals and real valuation data to fire.
    val, val_used = _value_layer(df)
    df["value_score"] = (val * 10).round(1) if val_used > 0 else np.nan
    if fund_used > 0 and val_used > 0:
        df["under_radar"] = (
            (df["fund_score"] >= 6.5)
            & (df["value_score"] >= 6.0)
            & (df["sent_score"].fillna(5.0) <= 5.5)
        )
        # Mega-caps are never "under the radar": their neutral sentiment is
        # heavy coverage netting out, not absence of attention. Missing
        # market cap passes (unknown size is usually small, not huge).
        if "market_cap" in df.columns:
            df["under_radar"] &= (
                pd.to_numeric(df["market_cap"], errors="coerce").fillna(0)
                < UNDER_RADAR_MAX_MCAP
            )
    else:
        df["under_radar"] = False

    df["action"] = pd.cut(
        df["ai_score"],
        bins=[0, HOLD_MIN, BUY_MIN, 10],
        labels=["AVOID", "HOLD", "BUY"],
    )
    df["rank_pct"] = (df["ai_score"].rank(pct=True) * 100).round(0)

    # Confidence: share of the total design weight backed by real data.
    df["confidence_pct"] = round(live / (W_TECH + W_SENT + W_FUND) * 100)

    return df

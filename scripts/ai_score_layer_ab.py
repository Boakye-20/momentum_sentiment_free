"""
scripts/ai_score_layer_ab.py — A/B candidate technical layers for the AI Score.

scripts/ai_score_decile_study.py established that the shipping AI Score has no
measurable ranking power (21d D10-D1 -0.49pp, rank IC -0.0092, t=-0.49) and
that its AVOID bucket beats its BUY bucket. This script tests the leading
structural explanation.

The hypothesis
--------------
scoring._technical_layer rewards momentum and 52-week proximity MONOTONICALLY
-- more is always better. The Signal Book (src/signals.py, the system the
backtest actually validates) instead gates on a BAND: 12m return above
trend_tsm_min, price within near_floor_52w of the high, and RSI inside
[rsi_pullback_min, rsi_pullback_max]. It is a "pullback within an uptrend"
thesis, not a "most extended name wins" thesis.

If that difference is the cause, re-shaping the layer to match the Signal
Book's own gates should move the IC. If the IC stays at zero, the problem is
not the shape and the layer needs different inputs, not a different curve.

Discipline
----------
Every threshold below is READ FROM CFG.signals, never fitted -- these are the
same numbers the validated Signal Book already uses, so the variants encode a
prior rather than a search over the outcome.

This still tests 4 variants against one sample. With a baseline t-stat near
zero, a single variant crossing |t|>2 out of 4 tries is weak evidence, not a
result -- roughly a 1-in-5 shot at the 5% level before correction. The bar
for believing any winner here is that it beats the baseline on BOTH horizons
AND in BOTH sentiment eras, which is reported per variant below.

Run:
    python scripts/ai_score_layer_ab.py
    python scripts/ai_score_layer_ab.py --horizons 21 63 --start 2015-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CFG                                    # noqa: E402
from src.scoring import _norm, _winsor_norm, _inv_winsor_norm  # noqa: E402
from ai_score_decile_study import (                       # noqa: E402
    SENTIMENT_ERA_START, build_observations, decile_table,
    information_coefficient, action_table, load_price_panel,
)

SC = CFG.signal


# ──────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────
def _rsi_band(df: pd.DataFrame) -> pd.Series:
    """RSI credit peaking at the centre of the Signal Book's pullback band and
    falling to zero at its edges — a strict reading of the same rule.

    The shipping layer instead fades linearly to zero at RSI 0 and 80, so it
    still pays partial credit to names the Signal Book would reject outright.
    """
    lo, hi = SC.rsi_pullback_min, SC.rsi_pullback_max
    mid, half = (lo + hi) / 2.0, (hi - lo) / 2.0
    r = pd.to_numeric(df["rsi"], errors="coerce").fillna(mid)
    return (1.0 - (r - mid).abs() / half).clip(0, 1)


def _mom_gated(df: pd.DataFrame) -> pd.Series:
    """Momentum credit, zero below trend_tsm_min, winsor-ranked above it.

    Keeps 'more momentum is better' but only among names that clear the gate,
    so a falling name can no longer earn partial technical credit for being
    less bad than the worst in the cross-section.
    """
    m = pd.to_numeric(df["mom_12m"], errors="coerce")
    passing = m >= SC.trend_tsm_min
    out = pd.Series(0.0, index=df.index)
    if passing.any():
        out.loc[passing] = _winsor_norm(m[passing])
    return out.clip(0, 1)


def _ratio_gated(df: pd.DataFrame) -> pd.Series:
    """52w-proximity credit, zero below near_floor_52w, rising to 1.0 at the high."""
    r = pd.to_numeric(df["ratio_52w"], errors="coerce")
    floor = SC.near_floor_52w
    return ((r - floor) / (1.0 - floor)).clip(0, 1).fillna(0.0)


def _ratio_pullback(df: pd.DataFrame) -> pd.Series:
    """52w-proximity credit that PEAKS BELOW the high, then tapers.

    This is the one genuinely new shape. The Signal Book's thesis is a dip
    inside an uptrend, so a name pinned at its 52-week high is extended, not
    ideal. Credit rises from near_floor_52w, plateaus over the upper-middle of
    the band, then falls back to 0.6 at the high itself — a taper, not a
    rejection, since a breakout is still a legitimate setup.
    """
    r = pd.to_numeric(df["ratio_52w"], errors="coerce")
    floor = SC.near_floor_52w
    peak_lo = floor + 0.55 * (1.0 - floor)   # ~0.8875 when floor is 0.75
    peak_hi = floor + 0.85 * (1.0 - floor)   # ~0.9625

    rise = ((r - floor) / (peak_lo - floor)).clip(0, 1)
    fall = 1.0 - 0.4 * ((r - peak_hi) / (1.0 - peak_hi)).clip(0, 1)
    return (rise * fall).clip(0, 1).fillna(0.0)


def _assemble(df: pd.DataFrame, parts: list[tuple[pd.Series, float]]
              ) -> tuple[pd.Series, float]:
    """Weighted sum renormalised over the weight actually used — the same
    contract _technical_layer honours, so compute_ai_score blends identically."""
    score = pd.Series(0.0, index=df.index)
    used = 0.0
    for series, w in parts:
        score += series.fillna(0.0) * w
        used += w
    if used > 0:
        score = score / used
    return score.clip(0, 1), min(used, 1.0)


# ──────────────────────────────────────────────────────────────────────────
# Variants
# ──────────────────────────────────────────────────────────────────────────
def layer_gated(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """B — Signal Book gates applied, weights otherwise unchanged."""
    return _assemble(df, [
        (_mom_gated(df),                                    0.30),
        (_ratio_gated(df),                                  0.20),
        (_rsi_band(df),                                     0.15),
        (df.get("above_long_ma", pd.Series(0.0, index=df.index))
           .fillna(0).astype(float).clip(0, 1),             0.15),
        (_inv_winsor_norm(df["volatility"]),                0.10),
        (_winsor_norm(df["macd_hist"]),                     0.10),
    ])


def layer_pullback(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """C — as B, but 52w proximity peaks below the high instead of at it."""
    return _assemble(df, [
        (_mom_gated(df),                                    0.30),
        (_ratio_pullback(df),                               0.20),
        (_rsi_band(df),                                     0.15),
        (df.get("above_long_ma", pd.Series(0.0, index=df.index))
           .fillna(0).astype(float).clip(0, 1),             0.15),
        (_inv_winsor_norm(df["volatility"]),                0.10),
        (_winsor_norm(df["macd_hist"]),                     0.10),
    ])


def layer_pullback_novol(df: pd.DataFrame) -> tuple[pd.Series, float]:
    """D — as C, with the low-volatility reward removed.

    Rewarding low realised vol is a risk preference, not a return forecast,
    and in a long bull sample it systematically down-ranks exactly the
    high-beta names that produced the biggest winners — the same mechanism
    that made vol-adjusted momentum lose its own A/B (see CLAUDE.md). Its
    0.10 redistributes across the survivors via _assemble's renormalisation.
    """
    return _assemble(df, [
        (_mom_gated(df),                                    0.30),
        (_ratio_pullback(df),                               0.20),
        (_rsi_band(df),                                     0.15),
        (df.get("above_long_ma", pd.Series(0.0, index=df.index))
           .fillna(0).astype(float).clip(0, 1),             0.15),
        (_winsor_norm(df["macd_hist"]),                     0.10),
    ])


VARIANTS = {
    "A baseline (shipping)":      None,             # None -> _technical_layer
    "B gated":                    layer_gated,
    "C gated + pullback 52w":     layer_pullback,
    "D C without low-vol reward": layer_pullback_novol,
}


# ──────────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────────
def summarise(obs: pd.DataFrame, horizons: list[int]) -> dict:
    """IC, t-stat, decile spread and BUY-minus-AVOID gap per horizon."""
    out = {}
    for h in horizons:
        ic, t, n = information_coefficient(obs, h)
        tbl = decile_table(obs, h)
        spread = (tbl.loc[10, "mean_%"] - tbl.loc[1, "mean_%"]
                  if not tbl.empty else np.nan)
        acts = action_table(obs, h)
        gap = (acts.loc["BUY", "mean_%"] - acts.loc["AVOID", "mean_%"]
               if {"BUY", "AVOID"}.issubset(acts.index) else np.nan)
        out[h] = {"ic": ic, "t": t, "n": n, "spread": spread, "buy_minus_avoid": gap}
    return out


def print_block(title: str, results: dict, horizons: list[int]) -> None:
    print(f"\n{title}")
    print("-" * 96)
    print(f"{'variant':<28}" + "".join(
        f"{'IC@' + str(h):>10}{'t':>8}{'D10-D1':>10}{'BUY-AVOID':>12}"
        for h in horizons))
    for name, res in results.items():
        row = f"{name:<28}"
        for h in horizons:
            r = res[h]
            row += (f"{r['ic']:>+10.4f}{r['t']:>+8.2f}"
                    f"{r['spread']:>+9.2f}pp{r['buy_minus_avoid']:>+11.2f}pp")
        print(row)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--horizons", type=int, nargs="+", default=[21, 63])
    ap.add_argument("--start", default="2015-01-01")
    args = ap.parse_args()

    px = load_price_panel(args.start)
    print(f"Prices: {px.shape[1]} tickers, "
          f"{px.index[0].date()} -> {px.index[-1].date()}")
    print(f"Gates from config: tsm_min={SC.trend_tsm_min}, "
          f"52w_floor={SC.near_floor_52w}, "
          f"rsi=[{SC.rsi_pullback_min:.0f},{SC.rsi_pullback_max:.0f}]")

    full, pre, post = {}, {}, {}
    for name, fn in VARIANTS.items():
        print(f"  scoring {name} ...", flush=True)
        obs = build_observations(px, args.horizons, technical_fn=fn)
        full[name] = summarise(obs, args.horizons)
        pre[name] = summarise(obs[obs["date"] < SENTIMENT_ERA_START], args.horizons)
        post[name] = summarise(obs[obs["date"] >= SENTIMENT_ERA_START], args.horizons)

    print_block("FULL SAMPLE", full, args.horizons)
    print_block("PRE-2022-03 (technical only)", pre, args.horizons)
    print_block("2022-03 ONWARD (technical + sentiment)", post, args.horizons)

    print("\n" + "=" * 96)
    print("A variant is only interesting if IC is positive with |t| > 2 in the "
          "FULL sample AND\nholds its sign in both eras and both horizons. "
          "BUY-AVOID should be positive — negative\nmeans the labels are still "
          "inverted. Four variants on one sample: treat a lone winner\nas a "
          "lead to test out-of-sample, never as a result to ship.")
    print("=" * 96)


if __name__ == "__main__":
    main()

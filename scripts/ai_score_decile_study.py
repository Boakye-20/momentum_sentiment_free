"""
scripts/ai_score_decile_study.py — does the AI Score predict forward returns?

The backtest validates the SIGNAL BOOK (src/signals.py's entry filter). It says
nothing about the AI SCORE, which is a different system: a 1-10 composite that
is the headline number in the screener UI and carries BUY/HOLD/AVOID labels a
user could trade on. That composite has never been tested against forward
returns. This script is that test.

Method
------
At each month-end, rebuild the exact per-ticker frame the screener builds,
score it with the REAL src/scoring.compute_ai_score, then measure what each
score decile actually returned over the following 21 / 63 trading days.

Two properties make this honest rather than circular:
  * scoring.py's _norm/_winsor_norm are CROSS-SECTIONAL (min-max across the
    tickers present on that date), so rebuilding them per-date uses only that
    date's information. No look-ahead.
  * forward returns are measured strictly after the scoring date.

The fundamentals blind spot
---------------------------
scoring.py weights fundamentals at 30%. yfinance's .info returns TODAY's
ratios with no as-of date (see src/fundamentals.py — the frame is indexed by
ticker, with no date axis), so a historical fundamentals panel cannot be
reconstructed on free data. Feeding today's ROE into a 2016 score would be
textbook look-ahead, so this study omits the layer entirely.

compute_ai_score handles that natively: _fundamental_layer returns used=0.0,
and the blend renormalises over live weight only. The scores here are
therefore technical 45/(45+25) = 64.3% + sentiment 25/70 = 35.7%. That is 70%
of the shipping score by design weight. The remaining 30% stays UNVALIDATED
and this script cannot fix that — only a paid point-in-time fundamentals
source could.

Sentiment coverage splits the sample
------------------------------------
data/sentiment_history.csv starts 2022-03. Before that the panel is all
zeros, and _sentiment_layer deactivates itself when every value is 0 — so
pre-2022 rows score on technicals alone. Results are reported per era for
that reason; pooling them would blend two different scoring systems.

Run:
    python scripts/ai_score_decile_study.py
    python scripts/ai_score_decile_study.py --horizons 21 63 126 --start 2016-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CFG                          # noqa: E402
from src import momentum                        # noqa: E402
from src.scoring import compute_ai_score, BUY_MIN, HOLD_MIN  # noqa: E402
from src.sentiment import load_sentiment_panel  # noqa: E402

SENTIMENT_ERA_START = pd.Timestamp("2022-03-01")


# ──────────────────────────────────────────────────────────────────────────
# Panel construction
# ──────────────────────────────────────────────────────────────────────────
def load_price_panel(start: str | None) -> pd.DataFrame:
    """Cached prices, restricted to the tradeable universe (no benchmark ETFs).

    Mirrors api/server.py's _tradeable_cols: the cache legitimately holds
    EEM/EMXC/FRDM as comparison benchmarks, and scoring them as if they were
    stocks would put ETFs in the deciles.
    """
    path = Path(CFG.paths.price_cache)
    if not path.exists():
        raise SystemExit(
            f"No price cache at {path}. Run a fetch first "
            "(python scripts/daily_fetch.py) — this study never uses "
            "synthetic prices."
        )
    px = pd.read_parquet(path).ffill().dropna(how="all")
    keep = [t for t in CFG.universe.tickers if t in px.columns]
    px = px[keep]
    if start:
        px = px.loc[str(start):]
    return px


def scoring_frame(date: pd.Timestamp, px: pd.DataFrame, panels: dict,
                  sent_panel: pd.DataFrame) -> pd.DataFrame:
    """The per-ticker frame the screener builds, as of `date`.

    Column names and derivations are copied from api/server.py's
    _build_screener so compute_ai_score sees exactly the inputs it sees in
    production. Deliberately omits every fundamentals column.
    """
    def row(panel_key: str) -> pd.Series:
        panel = panels.get(panel_key)
        if panel is None or date not in panel.index:
            return pd.Series(np.nan, index=px.columns)
        return panel.loc[date].reindex(px.columns)

    last_px = px.loc[date]
    ma_long = row("ma_long")

    df = pd.DataFrame({
        "mom_12m":       row("tsm"),
        "ratio_52w":     row("ratio52"),
        "rsi":           row("rsi"),
        "volatility":    row("vol"),
        "macd_hist":     row("macd_hist"),
        "above_long_ma": (last_px > ma_long).astype(float).where(ma_long.notna()),
    }, index=px.columns)

    if date in sent_panel.index:
        df["sentiment_score"] = sent_panel.loc[date].reindex(px.columns)

    # A ticker with no price that day (pre-IPO, delisted, failed fetch) cannot
    # be scored or traded. Dropping it here keeps it out of the cross-sectional
    # min-max too, so a half-listed name can't skew everyone else's normalisation.
    return df[last_px.notna() & df["mom_12m"].notna()]


def forward_return(px: pd.DataFrame, date: pd.Timestamp,
                   horizon: int) -> pd.Series:
    """Simple return from `date` to `date + horizon` trading days.

    Returns NaN where the window runs past the end of the data, so a truncated
    final window is excluded rather than silently scored as flat.
    """
    idx = px.index
    i = idx.get_indexer([date])[0]
    j = i + horizon
    if i < 0 or j >= len(idx):
        return pd.Series(np.nan, index=px.columns)
    return px.iloc[j] / px.iloc[i] - 1.0


# ──────────────────────────────────────────────────────────────────────────
# Study
# ──────────────────────────────────────────────────────────────────────────
def build_observations(px: pd.DataFrame, horizons: list[int],
                       technical_fn=None) -> pd.DataFrame:
    """One row per (date, ticker): its AI Score, action label and forward returns.

    `technical_fn` is passed through to compute_ai_score so a candidate
    technical layer can be measured on the same cross-sections — see
    scripts/ai_score_layer_ab.py.
    """
    panels = momentum.build_panels(px)
    sent_panel = load_sentiment_panel(px.index, list(px.columns))

    # Month-end scoring dates, matching the strategy's rebalance cadence.
    # Overlapping windows would otherwise inflate the apparent sample size.
    month_ends = px.index.to_series().groupby(px.index.to_period("M")).last()
    # Need a full year of history for the 12-month momentum panel to be real.
    month_ends = month_ends[month_ends >= px.index[0] + pd.Timedelta(days=400)]

    records = []
    for date in month_ends:
        frame = scoring_frame(date, px, panels, sent_panel)
        if len(frame) < 20:          # too thin for a 10-bucket cross-section
            continue
        scored = compute_ai_score(frame, technical_fn=technical_fn)
        fwd = {h: forward_return(px, date, h) for h in horizons}

        for ticker, r in scored.iterrows():
            rec = {
                "date": date,
                "ticker": ticker,
                "ai_score": r["ai_score"],
                "tech_score": r.get("tech_score", np.nan),
                "sent_score": r.get("sent_score", np.nan),
                "action": str(r["action"]),
                "confidence_pct": r.get("confidence_pct", np.nan),
            }
            for h in horizons:
                rec[f"fwd_{h}d"] = fwd[h].get(ticker, np.nan)
            records.append(rec)

    return pd.DataFrame(records)


def decile_table(obs: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Mean/median forward return by score decile.

    Deciles are cut WITHIN each date, not pooled: pooling would let a
    high-scoring month outrank a low-scoring one on level rather than on
    relative rank, which is not how the screener is read.
    """
    col = f"fwd_{horizon}d"
    d = obs.dropna(subset=[col, "ai_score"]).copy()
    if d.empty:
        return pd.DataFrame()

    d["decile"] = (
        d.groupby("date")["ai_score"]
         .transform(lambda s: pd.qcut(s.rank(method="first"), 10,
                                      labels=range(1, 11)))
    )
    g = d.groupby("decile", observed=True)[col]
    out = pd.DataFrame({
        "n":          g.size(),
        "mean_%":     g.mean() * 100,
        "median_%":   g.median() * 100,
        "hit_rate_%": g.apply(lambda s: (s > 0).mean() * 100),
    })
    return out.round(2)


def information_coefficient(obs: pd.DataFrame, horizon: int) -> tuple[float, float, int]:
    """Mean per-date Spearman rank IC, its t-stat, and the number of dates.

    IC is computed per date and then averaged — the standard construction.
    A pooled correlation across all dates would mix cross-sectional signal
    with time-series drift and overstate significance.
    """
    col = f"fwd_{horizon}d"
    ics = []
    for _, grp in obs.dropna(subset=[col, "ai_score"]).groupby("date"):
        if len(grp) >= 20 and grp["ai_score"].nunique() > 1:
            ics.append(grp["ai_score"].corr(grp[col], method="spearman"))
    if len(ics) < 2:
        return np.nan, np.nan, len(ics)
    arr = np.array(ics, dtype=float)
    t = arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr))) if arr.std(ddof=1) else np.nan
    return arr.mean(), t, len(arr)


def action_table(obs: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Forward returns by the BUY/HOLD/AVOID label the UI actually shows."""
    col = f"fwd_{horizon}d"
    d = obs.dropna(subset=[col])
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("action", observed=True)[col]
    out = pd.DataFrame({
        "n":          g.size(),
        "mean_%":     g.mean() * 100,
        "median_%":   g.median() * 100,
        "hit_rate_%": g.apply(lambda s: (s > 0).mean() * 100),
    })
    order = [a for a in ["BUY", "HOLD", "AVOID"] if a in out.index]
    return out.reindex(order).round(2)


def report_era(obs: pd.DataFrame, horizons: list[int], label: str) -> None:
    if obs.empty:
        print(f"\n{label}: no observations.\n")
        return

    dates = obs["date"].nunique()
    print(f"\n{'=' * 74}")
    print(f"{label}")
    print(f"{'=' * 74}")
    print(f"{dates} scoring dates · {len(obs):,} ticker-observations · "
          f"{obs['ticker'].nunique()} tickers")
    conf = obs["confidence_pct"].dropna()
    if not conf.empty:
        print(f"Blend confidence: {conf.mean():.0f}% of design weight "
              f"(fundamentals layer absent by construction)")

    for h in horizons:
        col = f"fwd_{h}d"
        if col not in obs.columns or obs[col].notna().sum() == 0:
            continue

        print(f"\n--- {h}-day forward return ---")
        tbl = decile_table(obs, h)
        if tbl.empty:
            print("  (insufficient data)")
            continue
        print(tbl.to_string())

        top, bot = tbl.loc[10, "mean_%"], tbl.loc[1, "mean_%"]
        print(f"\n  D10 - D1 spread : {top - bot:+.2f}pp "
              f"(D10 {top:+.2f}% vs D1 {bot:+.2f}%)")

        ic, t, n = information_coefficient(obs, h)
        if np.isfinite(ic):
            verdict = ("no predictive power" if abs(t) < 2
                       else "statistically significant")
            print(f"  Rank IC         : {ic:+.4f}  (t={t:+.2f}, {n} dates) "
                  f"-> {verdict} at |t|>2")

        acts = action_table(obs, h)
        if not acts.empty:
            print(f"\n  By displayed label:")
            print("  " + acts.to_string().replace("\n", "\n  "))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--horizons", type=int, nargs="+", default=[21, 63],
                    help="forward return horizons in trading days (default: 21 63)")
    ap.add_argument("--start", default=None,
                    help="earliest price date to load, e.g. 2016-01-01")
    ap.add_argument("--csv", default=None,
                    help="write the raw per-observation frame to this path")
    args = ap.parse_args()

    px = load_price_panel(args.start)
    print(f"Prices: {px.shape[1]} tickers, "
          f"{px.index[0].date()} -> {px.index[-1].date()}")

    obs = build_observations(px, args.horizons)
    if obs.empty:
        raise SystemExit("No observations produced — price history too short.")

    if args.csv:
        obs.to_csv(args.csv, index=False)
        print(f"Wrote {len(obs):,} observations to {args.csv}")

    report_era(obs, args.horizons, "FULL SAMPLE")

    pre = obs[obs["date"] < SENTIMENT_ERA_START]
    post = obs[obs["date"] >= SENTIMENT_ERA_START]
    if not pre.empty and not post.empty:
        report_era(pre, args.horizons,
                   "PRE-2022-03 — technical layer only (no sentiment logged)")
        report_era(post, args.horizons,
                   "2022-03 ONWARD — technical + sentiment, as shipped")

    print(f"\n{'=' * 74}")
    print("Reading this: a monotonic rise in mean return from D1 to D10 means "
          "the score\nranks. A positive IC with |t| > 2 means it ranks "
          "reliably rather than by luck.\nThe 30% fundamentals layer is NOT "
          "tested here and remains unvalidated.")
    print(f"{'=' * 74}")


if __name__ == "__main__":
    main()

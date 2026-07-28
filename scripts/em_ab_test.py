"""
scripts/em_ab_test.py — A/B the emerging-markets sleeve and its two risk gates.

Answers three separate questions that are easy to conflate:

  1. Does ADDING the EM sleeve to the universe help?      (arm 2 vs arm 1)
  2. Does the country cap help, given EM is in?           (arm 3 vs arm 2)
  3. Does vol-adjusted momentum ranking help, given EM?   (arm 4 vs arm 2)

Arms 3 and 4 are scored against arm 2, NOT arm 1, so a gate's effect is never
credited to (or blamed on) the universe change that preceded it.

READ `em_selection_rate_pct` BEFORE READING SHARPE. The LONG gate is calibrated
on US large caps: `near_floor_52w` wants price within 25% of the 52-week high,
and inverse-vol sizing scales ~ 1/vol. Both mechanically penalise high-vol EM
names. If EM barely gets selected, a flat Sharpe says nothing about EM alpha —
it says the gate never let EM in, which is a finding about the gate.

Usage:
    python scripts/em_ab_test.py
    python scripts/em_ab_test.py --start 2016-01-01
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg_mod  # noqa: E402
from config import CFG  # noqa: E402
from src import backtest, data  # noqa: E402

# Metrics worth printing, in the order the guidance document's §8 evaluation
# checklist asks for them.
CHECKLIST = [
    ("cagr_pct", "CAGR %"),
    ("sharpe", "Sharpe"),
    ("sortino", "Sortino"),
    ("max_drawdown_pct", "MaxDD %"),
    ("calmar", "Calmar"),
    ("win_rate_pct", "Win %"),
    ("avg_trade_pct", "AvgTrade %"),
    ("avg_hold_days", "AvgHold d"),
    ("n_trades", "Trades"),
    ("information_ratio", "InfoRatio"),
    ("beta", "Beta"),
    ("alpha_ann_pct", "Alpha %"),
    ("ann_vol_pct", "Vol %"),
]

EM_INSTRUMENTS = [
    ("em_weight_share_pct", "EM wt %"),
    ("em_selection_rate_pct", "EM sel %"),
    ("em_names_ever_held", "EM names"),
]


@contextmanager
def overrides(**kw):
    """Temporarily set CFG attributes, e.g. portfolio__use_country_cap=True.

    Restores the previous values on exit so one arm can never leak settings
    into the next — the whole test is worthless if it does.
    """
    saved = []
    try:
        for key, value in kw.items():
            section, attr = key.split("__", 1)
            obj = getattr(CFG, section)
            saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, value)
        yield
    finally:
        for obj, attr, old in reversed(saved):
            setattr(obj, attr, old)


def _run(prices: pd.DataFrame, benchmark: pd.Series, tickers: list[str],
         **flag_overrides) -> dict:
    px = prices[[t for t in tickers if t in prices.columns]]
    with overrides(**flag_overrides):
        res = backtest.run_backtest(px, benchmark, use_sentiment=False)
    return res.metrics


def _delta_table(arms: dict[str, dict], baselines: dict[str, str]) -> str:
    """Rows = metrics, columns = arms, with each arm's delta vs its own
    designated baseline arm."""
    names = list(arms)
    width = max(len(n) for n in names) + 2
    head = "metric".ljust(22) + "".join(n.ljust(width + 12) for n in names)
    lines = [head, "-" * len(head)]
    for key, label in CHECKLIST + EM_INSTRUMENTS:
        row = label.ljust(22)
        for n in names:
            val = arms[n].get(key, 0)
            base_name = baselines.get(n)
            if base_name and base_name != n:
                d = val - arms[base_name].get(key, 0)
                cell = f"{val:>9.3f} ({d:+.3f})"
            else:
                cell = f"{val:>9.3f}" + " " * 11
            row += cell.ljust(width + 12)
        lines.append(row)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=CFG.universe.start_date)
    ap.add_argument("--end", default=CFG.universe.end_date)
    args = ap.parse_args()

    pre_em = (cfg_mod.SLEEVE_CORE + cfg_mod.SLEEVE_QUALITY_VALUE
              + cfg_mod.SLEEVE_NICHE_GROWTH + cfg_mod.SLEEVE_GLOBAL)
    with_em = pre_em + cfg_mod.SLEEVE_EM
    em_benches = CFG.universe.em_benchmark_tickers

    need = sorted(set(with_em + [CFG.universe.benchmark_ticker] + em_benches))
    prices = data.load_prices(need, start=args.start, end=args.end)
    benchmark = prices[CFG.universe.benchmark_ticker]

    print(f"\nWindow {prices.index[0].date()} -> {prices.index[-1].date()}   "
          f"pre-EM={len(pre_em)}  with-EM={len(with_em)}\n")

    # EVERY flag is set explicitly on EVERY arm, never left to the config
    # default. This is not verbosity for its own sake: `use_country_cap` was
    # later flipped to default True, which silently turned "arm 2 = flags off"
    # into "arm 2 = cap on" and made arms 2 and 3 the same configuration. The
    # table still rendered, showing a perfect zero delta that looked like a
    # finding about the cap rather than a bug in the harness.
    OFF = dict(portfolio__use_country_cap=False,
               momentum__use_vol_adjusted_momentum=False)
    arms = {
        "1_baseline":   _run(prices, benchmark, pre_em, **OFF),
        "2_em":         _run(prices, benchmark, with_em, **OFF),
        "3_em_ctrycap": _run(prices, benchmark, with_em,
                             **{**OFF, "portfolio__use_country_cap": True}),
        "4_em_cap_vol": _run(prices, benchmark, with_em,
                             portfolio__use_country_cap=True,
                             momentum__use_vol_adjusted_momentum=True),
    }
    baselines = {"2_em": "1_baseline",
                 "3_em_ctrycap": "2_em",
                 "4_em_cap_vol": "2_em"}

    print("\n" + "=" * 100)
    print("EM A/B — deltas are vs arm 1 for arm 2, and vs arm 2 for arms 3/4")
    print("=" * 100)
    print(_delta_table(arms, baselines))

    # Benchmark context. EMXC/FRDM launched mid-sample, so their CAGR here is
    # over a shorter window than SPY's and is NOT directly comparable — the
    # start date is printed so that is visible rather than assumed.
    print("\nBenchmarks over this window:")
    for t in [CFG.universe.benchmark_ticker] + em_benches:
        if t not in prices.columns:
            continue
        s = prices[t].dropna()
        if len(s) < 2:
            continue
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        cagr = ((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs else 0.0
        print(f"  {t:6s} from {s.index[0].date()}  CAGR {cagr:6.2f}%")

    sel = arms["2_em"].get("em_selection_rate_pct", 0.0)
    print("\nInterpretation guard:")
    if sel < 5.0:
        print(f"  EM won only {sel:.2f}% of book seats — the Sharpe comparison "
              "above is NOT a verdict on EM alpha. The US-calibrated LONG gate "
              "is excluding EM mechanically; revisit near_floor_52w / RSI band "
              "or sleeve-relative parameters before concluding anything.")
    else:
        print(f"  EM won {sel:.2f}% of book seats — enough participation for "
              "the performance comparison to be meaningful.")
    print("\nRemember: these EM ADRs all survived to today. Survivorship bias "
          "inflates EM more than the US sleeve (terminated ADR programmes, the "
          "2022 China delisting scare). Discount any EM win accordingly.\n")


if __name__ == "__main__":
    main()

"""
scripts/coverage_check.py — is the sentiment history ready for the A/B test?

Per sleeve, reports how many tickers have complete Alpha Vantage history for
the backtest window, how many are mid-fetch, and how many haven't started.
Prints READY once >=80% of the non-core sleeves (quality_value, niche_growth,
global) are complete — that's the point where rerunning the sentiment-overlay
A/B actually tests the sleeves the overlay was built for.

Run:  python scripts/coverage_check.py
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import pandas as pd  # noqa: E402

from config import CFG, SLEEVES  # noqa: E402
from src.av_sentiment import _resume_from  # noqa: E402

HISTORY_START = "2022-03-01"
READY_PCT = 80.0


def main() -> int:
    end = CFG.universe.end_date
    resume = _resume_from(set(CFG.universe.tickers), HISTORY_START, end)

    print(f"\nAV sentiment coverage vs window {HISTORY_START} -> {end}\n")
    non_core_done = non_core_total = 0
    for name, tickers in SLEEVES.items():
        done = [t for t in tickers if resume.get(t) is None]
        started = [t for t in tickers
                   if resume.get(t) is not None
                   and resume[t] > pd.Timestamp(HISTORY_START)]
        fresh = [t for t in tickers
                 if resume.get(t) is not None and t not in started]
        pct = 100.0 * len(done) / len(tickers)
        print(f"  {name:<14} {len(done):>3}/{len(tickers)} complete "
              f"({pct:5.1f}%) | {len(started)} mid-fetch | "
              f"{len(fresh)} not started")
        if name != "core":
            non_core_done += len(done)
            non_core_total += len(tickers)

    pct = 100.0 * non_core_done / non_core_total
    print(f"\nNon-core sleeves complete: {non_core_done}/{non_core_total} "
          f"({pct:.1f}%) — threshold {READY_PCT:.0f}%")
    if pct >= READY_PCT:
        print("\nREADY -- rerun the A/B test:")
        print("    python main.py backtest")
        print("    python main.py backtest --use-sentiment")
        print("Compare Sharpe (not just CAGR). If the overlay still lags,")
        print("keep it off; if it now wins, flip use_sentiment_in_backtest.")
        return 0
    print("\nNOT READY -- the daily fetch is still filling the new sleeves "
          "(~25 requests/day). Check again in a few days.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

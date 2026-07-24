"""
scripts/daily_fetch.py — headless daily sentiment accumulation.

Run automatically by Windows Task Scheduler via scripts/daily_fetch.cmd
(task name: "MomentumSentiment Daily Fetch"). Three steps, each best-effort:

  1. Free snapshot: RSS + yfinance headlines scored with VADER, logged to
     data/sentiment_history.csv. This is the irreplaceable part — free news
     is recent-only, so a day not logged is a day lost forever.
  2. Alpha Vantage incremental history fetch — no-op once all tickers are
     cached, otherwise spends the daily budget filling gaps.
  3. Commits data/sentiment_history.csv if it changed, so the accumulated
     history is protected by git.

Manual run:  python scripts/daily_fetch.py
"""

from __future__ import annotations
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from config import CFG, av_fetch_order  # noqa: E402


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT,
                          capture_output=True, text=True)


def main() -> int:
    print(f"\n=== daily fetch {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
    ok = True

    # Keep the price cache current so the dashboard/API never serve stale
    # prices. yfinance first, Twelve Data fallback (slow but free) if set.
    # max_age_days=0 forces a top-up attempt every run: this job runs once
    # daily, so the default 3-day tolerance (meant for other callers, e.g.
    # the API checking freshness on every web request) let 1-2 day-old
    # data silently pass as "fresh enough" and never actually refresh.
    try:
        from src.data import refresh_price_cache
        refresh_price_cache(max_age_days=0)
    except Exception as e:
        print(f"[daily] price cache refresh failed: {e}")

    try:
        from src import sentiment as sent_mod
        snap = sent_mod.fetch_all_sentiment(CFG.universe.tickers)
        sent_mod.log_sentiment(snap, source="free")
    except Exception as e:
        ok = False
        print(f"[daily] free sentiment fetch failed: {e}")

    try:
        from src import av_sentiment as av
        # Sleeve-priority order: quality-value + niche first — sentiment
        # history matters most where analyst/news coverage is thinnest.
        av.fetch_history(av_fetch_order(), "2022-03-01",
                         CFG.universe.end_date)
    except Exception as e:
        # A missing key or exhausted budget shouldn't kill the free-side run.
        print(f"[daily] alpha vantage fetch failed: {e}")

    try:
        from scripts import portfolio_alerts
        portfolio_alerts.main()
    except Exception as e:
        print(f"[daily] portfolio alert check failed: {e}")

    log = CFG.paths.sentiment_log
    if _git("diff", "--quiet", "--", log).returncode != 0:
        _git("add", "--", log)
        r = _git("commit", "-m",
                 f"Daily sentiment fetch {datetime.now():%Y-%m-%d}\n\n"
                 "Automated by scripts/daily_fetch.py (Task Scheduler).")
        print(r.stdout.strip() or r.stderr.strip())
    else:
        print("[daily] no new sentiment rows to commit.")

    print(f"=== done ({'ok' if ok else 'with errors'}) ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

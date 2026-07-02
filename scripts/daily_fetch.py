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

from config import CFG  # noqa: E402


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT,
                          capture_output=True, text=True)


def main() -> int:
    print(f"\n=== daily fetch {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
    ok = True

    try:
        from src import sentiment as sent_mod
        snap = sent_mod.fetch_all_sentiment(CFG.universe.tickers)
        sent_mod.log_sentiment(snap, source="free")
    except Exception as e:
        ok = False
        print(f"[daily] free sentiment fetch failed: {e}")

    try:
        from src import av_sentiment as av
        av.fetch_history(CFG.universe.tickers, "2022-03-01",
                         CFG.universe.end_date)
    except Exception as e:
        # A missing key or exhausted budget shouldn't kill the free-side run.
        print(f"[daily] alpha vantage fetch failed: {e}")

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

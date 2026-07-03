"""
tests/test_smoke.py — runs the whole pipeline offline (synthetic prices),
so you can verify the engine end-to-end with no network and no API keys:

    python -m pytest -q        (or)        python tests/test_smoke.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import CFG
from src import data as data_mod
from src import backtest as bt_mod
from src import momentum
from src import sentiment as sent_mod
from src import signals


def test_backtest_runs_and_trades():
    prices_all = data_mod.load_prices(source="synthetic", use_cache=False)
    prices, bench = data_mod.split_universe_benchmark(prices_all)
    if bench is None:
        bench = prices.mean(axis=1)
    res = bt_mod.run_backtest(prices, bench, use_sentiment=False)

    # The previous engine managed ~2 trades in 11 years; the fixed filter
    # should trade meaningfully more than that.
    assert res.metrics["n_trades"] > 20, res.metrics
    # Sharpe must be finite and sane (the old bug produced ~3.3 on monthly data).
    assert -5 < res.metrics["sharpe"] < 5, res.metrics
    assert len(res.equity) > 200
    assert res.equity.iloc[-1] > 0


def test_tsm_skips_recent_month():
    # 12-1 momentum: a crash inside the skip window must be invisible to TSM,
    # while plain 12m TSM sees it.
    idx = pd.bdate_range("2020-01-01", periods=300)
    vals = np.full(300, 100.0)
    vals[-21:] = 50.0
    px = pd.DataFrame({"X": vals}, index=idx)
    assert momentum.tsm(px, lookback=252, skip=21)["X"].iloc[-1] == 0.0
    assert momentum.tsm(px, lookback=252, skip=0)["X"].iloc[-1] < 0


def test_inverse_vol_weights():
    prices_all = data_mod.load_prices(source="synthetic", use_cache=False)
    prices, _ = data_mod.split_universe_benchmark(prices_all)
    panels = momentum.build_panels(prices)
    w = signals.weights_for_date(prices.index[-1], prices, panels)
    longs = w[w > 0]
    assert longs.sum() <= 1.0 + 1e-9          # gross long never exceeds 1
    if len(longs) > 1 and CFG.portfolio.use_inverse_vol_weights:
        vol = panels["vol"].iloc[-1].reindex(longs.index)
        expected = (1 / vol) / (1 / vol).sum() * longs.sum()
        assert np.allclose(longs.values, expected.values, rtol=1e-6), \
            "long weights must be proportional to 1/realised vol"


def test_av_resume_points(tmp_path=None):
    from src.av_sentiment import _resume_from

    out_dir = Path(tmp_path) if tmp_path else Path("outputs")
    out_dir.mkdir(exist_ok=True)
    csv = out_dir / "_test_av_resume.csv"

    rows = []
    # A: history truncated mid-2023, PLUS a recent snapshot row that must not
    #    mask the gap -> resume the day after the contiguous block ends.
    for d in pd.date_range("2022-03-01", "2023-06-05", freq="7D"):
        rows.append({"date": d, "ticker": "A", "score": 0.1, "source": "alphavantage"})
    rows.append({"date": pd.Timestamp("2026-06-30"), "ticker": "A",
                 "score": 0.2, "source": "alphavantage"})
    # B: history reaches within the tail tolerance of the window end -> done.
    for d in pd.date_range("2022-03-01", "2025-12-20", freq="30D"):
        rows.append({"date": d, "ticker": "B", "score": 0.1, "source": "alphavantage"})
    # C: only a snapshot row -> fetch from the window start.
    rows.append({"date": pd.Timestamp("2026-06-30"), "ticker": "C",
                 "score": 0.3, "source": "alphavantage"})
    pd.DataFrame(rows).to_csv(csv, index=False)

    r = _resume_from({"A", "B", "C", "D"}, "2022-03-01", "2025-12-31", path=str(csv))
    csv.unlink()

    block_end_a = pd.date_range("2022-03-01", "2023-06-05", freq="7D")[-1]
    assert r["A"] == block_end_a + pd.Timedelta(days=1)
    assert r["B"] is None
    assert r["C"] == pd.Timestamp("2022-03-01")
    assert r["D"] == pd.Timestamp("2022-03-01")   # never fetched


def test_vader_scoring_offline():
    pos = sent_mod.score_text("Shares soar after blowout earnings beat")
    neg = sent_mod.score_text("Stock plunges amid fraud probe and lawsuits")
    assert pos > 0 > neg


if __name__ == "__main__":
    test_backtest_runs_and_trades()
    test_tsm_skips_recent_month()
    test_inverse_vol_weights()
    test_av_resume_points()
    test_vader_scoring_offline()
    print("\nAll smoke tests passed.")

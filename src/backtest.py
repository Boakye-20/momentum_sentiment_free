"""
src/backtest.py — Module 4: a correct vector backtest.

Fixes vs the previous engine:
  * Marks the book to market DAILY, so Sharpe/vol/drawdown annualise correctly
    (x252 / xsqrt(252) on *daily* returns). The old code annualised a *monthly*
    equity series as if it were daily and inflated Sharpe ~4.6x.
  * Positions actually rotate (monthly target weights, ffilled, T+1 lagged).
  * Costs charged on real turnover on the execution day.
"""

from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import CFG
from src import momentum, signals, sentiment as sent_mod


@dataclass
class BacktestResult:
    equity: pd.Series
    benchmark: pd.Series
    daily_returns: pd.Series
    weights: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict
    walk_forward: list = field(default_factory=list)


def _rebalance_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last available trading day of each month."""
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period(CFG.portfolio.rebalance)).last().values)


def _build_target_weights(prices, panels, sent_panel, use_sentiment) -> pd.DataFrame:
    rebals = _rebalance_dates(prices.index)
    rows = {}
    min_hist = CFG.backtest.min_history_days
    for d in rebals:
        if prices.index.get_loc(d) < min_hist:
            continue
        sent_row = sent_panel.loc[d] if (use_sentiment and d in sent_panel.index) else None
        rows[d] = signals.weights_for_date(d, prices, panels, sent_row, use_sentiment)
    if not rows:
        return pd.DataFrame(columns=prices.columns)
    return pd.DataFrame(rows).T.reindex(columns=prices.columns).fillna(0.0)


def _trades_from_weights(eff: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct discrete holding spells (entry->exit) for honest trade stats."""
    recs = []
    for t in eff.columns:
        w = eff[t]
        held = w != 0
        if not held.any():
            continue
        starts = held & ~held.shift(1, fill_value=False)
        ends = ~held & held.shift(1, fill_value=False)
        entry_dates = w.index[starts]
        exit_dates = list(w.index[ends])
        for i, ed in enumerate(entry_dates):
            xd = exit_dates[i] if i < len(exit_dates) else w.index[-1]
            direction = "LONG" if w.loc[ed] > 0 else "SHORT"
            ep, xp = prices.loc[ed, t], prices.loc[xd, t]
            ret = (xp / ep - 1) * (1 if direction == "LONG" else -1)
            recs.append({"ticker": t, "direction": direction,
                         "entry_date": ed.date(), "exit_date": xd.date(),
                         "entry_price": round(float(ep), 2), "exit_price": round(float(xp), 2),
                         "return_pct": round(float(ret) * 100, 2),
                         "hold_days": int((xd - ed).days)})
    cols = ["ticker", "direction", "entry_date", "exit_date",
            "entry_price", "exit_price", "return_pct", "hold_days"]
    return pd.DataFrame(recs, columns=cols).sort_values("entry_date").reset_index(drop=True)


def _metrics(equity, benchmark, daily, trades) -> dict:
    n_years = (equity.index[-1] - equity.index[0]).days / 365.25
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    vol = daily.std() * np.sqrt(252)
    sharpe = (daily.mean() * 252) / vol if vol > 0 else 0.0
    downside = daily[daily < 0].std() * np.sqrt(252)
    sortino = (daily.mean() * 252) / downside if downside > 0 else 0.0
    dd = (equity / equity.cummax() - 1)
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    b = benchmark.reindex(equity.index).ffill()
    b_total = b.iloc[-1] / b.iloc[0] - 1
    b_cagr = (1 + b_total) ** (1 / n_years) - 1 if n_years > 0 else 0.0

    win = (trades["return_pct"] > 0).mean() if len(trades) else 0.0
    return {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "benchmark_cagr_pct": round(b_cagr * 100, 2),
        "active_return_pct": round((cagr - b_cagr) * 100, 2),
        "ann_vol_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "calmar": round(calmar, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "n_trades": int(len(trades)),
        "win_rate_pct": round(win * 100, 2),
        "avg_trade_pct": round(trades["return_pct"].mean(), 2) if len(trades) else 0.0,
        "avg_hold_days": int(trades["hold_days"].mean()) if len(trades) else 0,
    }


def _walk_forward(equity, benchmark) -> list:
    in_y, out_y = CFG.backtest.in_sample_years, CFG.backtest.out_sample_years
    folds, start, end_all = [], equity.index[0], equity.index[-1]

    def _cagr(s):
        if len(s) < 2:
            return 0.0
        r = s.iloc[-1] / s.iloc[0] - 1
        n = (s.index[-1] - s.index[0]).days / 365.25
        return round(((1 + r) ** (1 / n) - 1) * 100, 2) if n > 0 else 0.0

    while True:
        in_end = start + pd.DateOffset(years=in_y)
        out_end = in_end + pd.DateOffset(years=out_y)
        if out_end > end_all:
            break
        ie = equity[(equity.index >= start) & (equity.index < in_end)]
        oe = equity[(equity.index >= in_end) & (equity.index < out_end)]
        folds.append({
            "window": f"{start.date()} -> {out_end.date()}",
            "in_cagr": _cagr(ie), "out_cagr": _cagr(oe),
            "out_bench": _cagr(benchmark.reindex(oe.index).ffill()),
        })
        start += pd.DateOffset(years=out_y)
    return folds


def run_backtest(prices: pd.DataFrame, benchmark: pd.Series,
                 use_sentiment: bool | None = None) -> BacktestResult:
    use_sentiment = (CFG.backtest.use_sentiment_in_backtest
                     if use_sentiment is None else use_sentiment)
    print(f"[backtest] universe={prices.shape[1]} tickers, "
          f"{prices.index[0].date()} -> {prices.index[-1].date()}, "
          f"sentiment_overlay={use_sentiment}")

    panels = momentum.build_panels(prices)
    sent_panel = (sent_mod.load_sentiment_panel(prices.index, list(prices.columns))
                  if use_sentiment else None)

    target = _build_target_weights(prices, panels, sent_panel, use_sentiment)
    if target.empty:
        raise RuntimeError("No rebalance dates produced signals — check history length.")

    # daily step-function weights, T+1 lagged (no look-ahead)
    daily_w = target.reindex(prices.index).ffill().fillna(0.0)
    eff = daily_w.shift(CFG.portfolio.execution_delay_days).fillna(0.0)

    asset_ret = prices.pct_change().fillna(0.0)
    gross = (eff * asset_ret).sum(axis=1)
    turnover = eff.diff().abs().sum(axis=1)
    turnover.iloc[0] = eff.iloc[0].abs().sum()
    cost = turnover * CFG.portfolio.transaction_cost_bps / 10_000.0
    net = (gross - cost)

    # restrict to the live period (after first real position)
    first = eff.abs().sum(axis=1)
    live = first[first > 0].index.min()
    net = net.loc[live:]
    equity = (1 + net).cumprod() * CFG.portfolio.initial_capital
    equity.name = "strategy"

    bench = benchmark.reindex(equity.index).ffill()
    bench = bench / bench.iloc[0] * CFG.portfolio.initial_capital
    bench.name = "benchmark"

    trades = _trades_from_weights(eff.loc[live:], prices.loc[live:])
    metrics = _metrics(equity, bench, net, trades)
    wf = _walk_forward(equity, bench)

    print(f"[backtest] done. final equity £{equity.iloc[-1]:,.0f} "
          f"| CAGR {metrics['cagr_pct']}% vs bench {metrics['benchmark_cagr_pct']}% "
          f"| Sharpe {metrics['sharpe']} | {metrics['n_trades']} trades")
    return BacktestResult(equity, bench, net, eff.loc[live:], trades, metrics, wf)

"""
src/report.py — Module 5: charts + markdown performance report.
"""

from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import CFG

plt.rcParams.update({"figure.dpi": 110, "axes.grid": True,
                     "grid.alpha": 0.25, "font.size": 10})


def _save(fig, name) -> str:
    os.makedirs(CFG.paths.outputs_dir, exist_ok=True)
    path = str(Path(CFG.paths.outputs_dir) / name)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def make_charts(res) -> list[str]:
    paths = []

    # 1. Equity vs benchmark
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(res.equity.index, res.equity, label="Strategy", lw=1.6)
    ax.plot(res.benchmark.index, res.benchmark, label="Benchmark (buy & hold)",
            lw=1.3, alpha=0.8)
    ax.set_title("Equity curve vs benchmark")
    ax.set_ylabel("Portfolio value (£)")
    ax.legend()
    paths.append(_save(fig, "01_equity_curve.png"))

    # 2. Drawdown
    dd = (res.equity / res.equity.cummax() - 1) * 100
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.fill_between(dd.index, dd, 0, color="#E74C3C", alpha=0.4)
    ax.set_title("Drawdown")
    ax.set_ylabel("%")
    paths.append(_save(fig, "02_drawdown.png"))

    # 3. Monthly returns heatmap
    monthly = res.daily_returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
    if len(monthly):
        piv = monthly.to_frame("r")
        piv["Year"] = piv.index.year
        piv["Month"] = piv.index.month
        grid = piv.pivot_table(index="Year", columns="Month", values="r")
        fig, ax = plt.subplots(figsize=(10, max(2.5, 0.5 * len(grid))))
        im = ax.imshow(grid.values, cmap="RdYlGn", aspect="auto",
                       vmin=-np.nanmax(np.abs(grid.values)),
                       vmax=np.nanmax(np.abs(grid.values)))
        ax.set_xticks(range(len(grid.columns)))
        ax.set_xticklabels(grid.columns)
        ax.set_yticks(range(len(grid.index)))
        ax.set_yticklabels(grid.index)
        ax.set_title("Monthly returns (%)")
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                v = grid.values[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7)
        fig.colorbar(im, ax=ax, fraction=0.025)
        paths.append(_save(fig, "03_monthly_returns.png"))

    # 4. Trade return distribution
    if len(res.trades):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(res.trades["return_pct"], bins=30, color="#3498DB", alpha=0.8)
        ax.axvline(0, color="k", lw=1)
        ax.set_title(f"Per-trade return distribution (n={len(res.trades)})")
        ax.set_xlabel("Return %")
        paths.append(_save(fig, "04_trade_distribution.png"))

    return paths


def write_report(res, chart_paths) -> str:
    m = res.metrics
    os.makedirs(CFG.paths.outputs_dir, exist_ok=True)
    path = str(Path(CFG.paths.outputs_dir) / "performance_report.md")
    lines = [
        "# Momentum + Sentiment Strategy — Performance Report",
        f"*Generated {datetime.now():%Y-%m-%d %H:%M}*",
        "",
        f"Window: **{res.equity.index[0].date()} → {res.equity.index[-1].date()}** | "
        f"Universe: **{len(CFG.universe.tickers)}** tickers | "
        f"Benchmark: **{CFG.universe.benchmark_ticker}**",
        "",
        "## Headline metrics",
        "",
        "| Metric | Strategy | Benchmark |",
        "|---|---|---|",
        f"| CAGR | **{m['cagr_pct']}%** | {m['benchmark_cagr_pct']}% |",
        f"| Active return (vs benchmark) | **{m['active_return_pct']}%** | — |",
        f"| Annualised volatility | {m['ann_vol_pct']}% | — |",
        f"| Sharpe | **{m['sharpe']}** | — |",
        f"| Sortino | {m['sortino']} | — |",
        f"| Calmar | {m['calmar']} | — |",
        f"| Max drawdown | {m['max_drawdown_pct']}% | — |",
        f"| Total trades | {m['n_trades']} | — |",
        f"| Win rate | {m['win_rate_pct']}% | — |",
        f"| Avg trade | {m['avg_trade_pct']}% | — |",
        f"| Avg hold (days) | {m['avg_hold_days']} | — |",
        "",
        "## Walk-forward (out-of-sample) validation",
        "",
        "| Window | In-sample CAGR | Out-sample CAGR | Out-sample benchmark |",
        "|---|---|---|---|",
    ]
    for f in res.walk_forward:
        lines.append(f"| {f['window']} | {f['in_cagr']}% | {f['out_cagr']}% | {f['out_bench']}% |")

    lines += ["", "## Charts", ""]
    for p in chart_paths:
        lines.append(f"![{Path(p).stem}]({Path(p).name})")

    lines += [
        "", "## Notes", "",
        "- Backtest signals are **price/momentum based** (fully historical, free).",
        "  News sentiment is a *live* overlay — see the README for why free news",
        "  can't be backtested over many years, and how to grow your own history.",
        "- Past simulated performance is not indicative of future results. This is a",
        "  research tool, not investment advice.",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] written -> {path}")
    return path

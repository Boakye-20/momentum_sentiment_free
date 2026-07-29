"""
main.py — command-line entry point.

  python main.py backtest                 # historical momentum backtest + report
  python main.py backtest --synthetic     # offline test (fake prices, no network)
  python main.py signals                  # TODAY's live signals (price + free news)
  python main.py fetch-sentiment          # log today's free news sentiment only
  python main.py report                   # rebuild report from a cached backtest

Run from the project root so `config` and `src` import correctly.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from config import CFG
from src import data as data_mod
from src import momentum, signals
from src import sentiment as sent_mod
from src import backtest as bt_mod
from src import report as report_mod


def cmd_backtest(args):
    source = "synthetic" if args.synthetic else "yfinance"
    prices_all = data_mod.load_prices(source=source, use_cache=not args.no_cache)
    prices, benchmark = data_mod.split_universe_benchmark(prices_all)
    if benchmark is None:                       # synthetic benchmark fallback
        benchmark = prices.mean(axis=1)
    res = bt_mod.run_backtest(prices, benchmark,
                              use_sentiment=args.use_sentiment)
    charts = report_mod.make_charts(res)
    report_mod.write_report(res, charts)
    res.trades.to_csv(Path(CFG.paths.outputs_dir) / "trade_log.csv", index=False)
    print(f"[main] trade log -> {Path(CFG.paths.outputs_dir) / 'trade_log.csv'}")


def cmd_signals(args):
    """Today's actionable signals: current momentum state + live free sentiment."""
    prices_all = data_mod.load_prices(use_cache=not args.no_cache)
    prices, _ = data_mod.split_universe_benchmark(prices_all)
    panels = momentum.build_panels(prices)
    today = prices.index[-1]

    source = args.source or CFG.sentiment.source
    print(f"\n[signals] fetching sentiment (source: {source}) ...")
    if source == "alphavantage":
        from src import av_sentiment as av
        snap = av.fetch_today(list(prices.columns))
        if not snap.empty:
            av.append_sentiment_rows(snap, source="alphavantage")
            sent_row = snap.set_index("ticker")["score"]
        else:
            sent_row = pd.Series(0.0, index=prices.columns)
    else:
        snap = sent_mod.fetch_all_sentiment(list(prices.columns))
        sent_mod.log_sentiment(snap, source="free")
        sent_row = snap["score"]

    weights = signals.weights_for_date(today, prices, panels,
                                       sentiment=sent_row, use_sentiment=True)
    active = weights[weights != 0].sort_values(ascending=False)
    print(f"\n=== SIGNALS for {today.date()} "
          f"(regime: {momentum.breadth_regime(prices).iloc[-1]}) ===")
    if active.empty:
        print("  No positions pass the filter today.")
        return
    out = []
    for t, w in active.items():
        out.append({
            "ticker": t,
            "side": "LONG" if w > 0 else "SHORT",
            "weight_%": round(w * 100, 1),
            "tsm_12m_%": round(panels["tsm"][t].iloc[-1] * 100, 1),
            "52w_ratio": round(panels["ratio52"][t].iloc[-1], 2),
            "rsi": round(panels["rsi"][t].iloc[-1], 1),
            "sentiment": round(float(sent_row.get(t, 0.0)), 3),
        })
    print(pd.DataFrame(out).to_string(index=False))


def cmd_fetch_sentiment(args):
    snap = sent_mod.fetch_all_sentiment()
    sent_mod.log_sentiment(snap, source="free")
    print("\n" + snap[["score", "n_headlines", "label"]].to_string())


def cmd_fetch_av(args):
    """Fetch & cache historical sentiment from Alpha Vantage (free key)."""
    from src import av_sentiment as av
    try:
        av.fetch_history(CFG.universe.tickers, args.start, args.end,
                         max_requests=args.max_requests)
    except RuntimeError as e:
        print(f"\n[error] {e}")
        print("Get a free key at https://www.alphavantage.co/support/#api-key, "
              "then `cp .env.example .env` and paste it in.")


def cmd_execute_trades(args):
    """Execute target trades in Trading212."""
    from src.executor import execute_trades
    execute_trades(live=args.live, override_capital=args.capital,
                   force=getattr(args, "force", False))


def build_parser():
    p = argparse.ArgumentParser(description="Free momentum + sentiment trading model")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="historical backtest + report")
    b.add_argument("--synthetic", action="store_true",
                   help="use offline synthetic prices (no network)")
    b.add_argument("--use-sentiment", action="store_true",
                   help="overlay logged sentiment history (see README)")
    b.add_argument("--no-cache", action="store_true")
    b.set_defaults(func=cmd_backtest)

    s = sub.add_parser("signals", help="today's live signals")
    s.add_argument("--source", choices=["free", "alphavantage"], default=None,
                   help="sentiment source (default: config)")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_signals)

    f = sub.add_parser("fetch-sentiment", help="log today's free news sentiment")
    f.set_defaults(func=cmd_fetch_sentiment)

    a = sub.add_parser("fetch-av-sentiment",
                       help="fetch & cache historical Alpha Vantage sentiment")
    a.add_argument("--start", default="2022-03-01")
    a.add_argument("--end", default=CFG.universe.end_date)
    a.add_argument("--max-requests", type=int, default=25,
                   help="API calls this run (free tier ~25/day)")
    a.set_defaults(func=cmd_fetch_av)

    e = sub.add_parser("execute-trades", help="place automated orders in Trading212")
    e.add_argument("--live", action="store_true", help="actually place the trades (default is dry-run)")
    e.add_argument("--capital", type=float, default=None, help="override the account value for sizing")
    e.add_argument("--force", action="store_true",
                   help="rebalance even if this period was already traded "
                        "(the bot normally acts once per CFG.portfolio.rebalance "
                        "period — daily trading destroys the backtested edge)")
    e.set_defaults(func=cmd_execute_trades)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)

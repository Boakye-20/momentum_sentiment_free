"""
executor.py — Automated trading execution via Trading212 API.
"""

import os
import time
import base64
import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime
import pandas as pd

from config import CFG
from src import momentum, signals
from src.data import load_prices

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Rebalance gate
# ──────────────────────────────────────────────────────────────────────────
# The scheduled task runs this bot EVERY morning, but the strategy is a
# monthly-rebalance strategy. Acting daily is not a milder version of it — it
# is a different, far worse strategy. Measured 2016-2026, same rules, only the
# cadence changed:
#
#     monthly : CAGR +25.61%  Sharpe 1.275  MaxDD -23.4%   37d hold   19x turnover
#     weekly  : CAGR +13.60%  Sharpe 0.756  MaxDD -25.7%   11d hold   64x turnover
#     daily   : CAGR  -0.29%  Sharpe 0.077  MaxDD -41.7%    4d hold  192x turnover
#
# The ~37-day average hold is the MECHANISM, not a side effect: momentum needs
# weeks to pay out, and the entry rule's RSI band makes names flicker in and out
# of the book day to day. So we keep running daily (a missed day then heals
# itself) but only ACT once per rebalance period.
#
# Why a period-CHANGE test rather than "is today month-end": backtest's
# _rebalance_dates() does groupby(period).last(), which for the current,
# incomplete month returns the latest bar — i.e. today. Reusing it live would
# mark every single day a rebalance day, which is precisely the bug. Detecting
# the true last trading day of a month needs a forward market calendar we do
# not have.
#
# Acting on the first run of a NEW period is equivalent to the backtest, not a
# compromise: the backtest computes weights at month-end close and executes
# shift(execution_delay_days=1) — the first trading day of the next month. The
# 08:30 run sees px.index[-1] = the month-end close and places orders that fill
# that same first trading day.
_STATE_FILE = "bot_state.json"


def _state_path() -> str:
    return os.path.join(CFG.paths.data_dir, _STATE_FILE)


def _load_state() -> dict:
    try:
        with open(_state_path(), "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(CFG.paths.data_dir, exist_ok=True)
        with open(_state_path(), "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[Warn] Could not write {_state_path()}: {e}")


def _current_period(ts) -> str:
    """The rebalance period `ts` falls in, per CFG.portfolio.rebalance."""
    return str(pd.Timestamp(ts).to_period(CFG.portfolio.rebalance))


def should_rebalance(today, force: bool = False) -> tuple[bool, str]:
    """(may_trade, human-readable reason).

    No stored state means first run ever -> rebalance, so deploying this aligns
    the book immediately instead of waiting up to a month.
    """
    period = _current_period(today)
    if force:
        return True, f"--force: rebalancing in period {period}"
    last = _load_state().get("last_rebalance_period")
    if last is None:
        return True, f"no previous rebalance recorded -> rebalancing ({period})"
    if last == period:
        return False, (f"already rebalanced in {period} — holding. "
                       f"Next rebalance when the {CFG.portfolio.rebalance} "
                       f"period rolls over.")
    return True, f"new period {period} (last was {last}) -> rebalancing"


def _record_rebalance(today) -> None:
    """Called ONLY after a live run actually placed orders. A dry run or a
    crashed run must not consume the period."""
    state = _load_state()
    state["last_rebalance_period"] = _current_period(today)
    state["last_rebalance_date"] = str(pd.Timestamp(today).date())
    _save_state(state)


class Trading212Client:
    def __init__(self, key: str, secret: str = "", env: str = "demo"):
        self.host = "demo" if env.lower() == "demo" else "live"
        if secret:
            token = base64.b64encode(f"{key}:{secret}".encode()).decode()
            self.auth = f"Basic {token}"
        else:
            self.auth = key
            
        self.instruments_cache = {}

    def _request(self, method: str, endpoint: str, data: dict = None):
        url = f"https://{self.host}.trading212.com/api/v0/equity/{endpoint}"
        headers = {
            "Authorization": self.auth,
            "Content-Type": "application/json"
        }
        
        req_data = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise RuntimeError(f"T212 API Error {e.code}: {error_body}")
            
    def get_account_cash(self):
        """Returns account cash details including total account value."""
        return self._request("GET", "account/cash")
        
    def get_positions(self):
        """Returns open positions."""
        return self._request("GET", "positions")
        
    def get_instruments(self):
        """Returns metadata for all available instruments."""
        if not self.instruments_cache:
            self.instruments_cache = self._request("GET", "metadata/instruments")
        return self.instruments_cache

    def place_market_order(self, t212_ticker: str, quantity: float):
        """Place a market order. Positive quantity buys, negative quantity sells."""
        payload = {
            "ticker": t212_ticker,
            "quantity": quantity
        }
        return self._request("POST", "orders/market", data=payload)


def _get_t212_ticker(sym: str, instruments: list, current_positions: list) -> str:
    """Finds the correct T212 ticker for our symbol (e.g. AAPL -> AAPL_US_EQ)."""
    # 1. Check existing positions first for an exact match
    for p in current_positions:
        t212_tick = p.get("instrument", {}).get("ticker", "")
        if t212_tick.split("_")[0] == sym:
            return t212_tick
            
    # 2. Check metadata
    matches = [i for i in instruments if i.get("shortName") == sym and i.get("type") == "STOCK"]
    if matches:
        # Prefer US listings if multiple exist
        us_matches = [m for m in matches if "US" in m.get("ticker", "")]
        if us_matches:
            return us_matches[0]["ticker"]
        return matches[0]["ticker"]
        
    # 3. Fallback guess
    return f"{sym}_US_EQ"


def execute_trades(live: bool = False, override_capital: float = None,
                   force: bool = False):
    """
    Computes delta between target portfolio and current T212 portfolio,
    and places market orders to align them.

    Only places orders once per CFG.portfolio.rebalance period (see the
    rebalance-gate notes at the top of this module) — `force=True` overrides.
    The trade plan is always computed and printed so drift stays visible even
    on a held day.
    """
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    key = os.environ.get("T212_API_KEY", "").strip()
    secret = os.environ.get("T212_API_SECRET", "").strip()
    env = os.environ.get("T212_ENV", "demo").strip()
    
    if not key or key.startswith("your_"):
        print("[Error] T212_API_KEY not set in .env")
        return

    print(f"--- Initialising Trading212 Executor ({env.upper()} mode) ---")
    client = Trading212Client(key, secret, env)
    
    # 1. Get Account Value
    print("Fetching account details...")
    cash_info = client.get_account_cash()
    total_value = float(cash_info.get("total", 0.0))
    free_cash = float(cash_info.get("free", 0.0))
    
    capital = override_capital if override_capital else total_value
    print(f"Total Account Value: £{total_value:,.2f}")
    print(f"Free Cash: £{free_cash:,.2f}")
    print(f"Using Capital for Sizing: £{capital:,.2f}")
    
    # 2. Get Target Signals
    print("\nCalculating Target Signals...")
    px_all = load_prices(use_cache=True)
    
    # Import split_universe_benchmark safely
    from src.data import split_universe_benchmark
    px, _ = split_universe_benchmark(px_all)
    
    panels = momentum.build_panels(px)
    today = px.index[-1]
    
    # Get sentiment
    sent_row = pd.Series(0.0, index=px.columns)
    try:
        from pathlib import Path
        p = Path(CFG.paths.sentiment_log)
        if p.exists():
            hist = pd.read_csv(p, parse_dates=["date"])
            latest = hist.loc[hist.date == hist.date.max()]
            scores = latest.set_index("ticker")["score"].reindex(px.columns)
            # Missing sentiment must mean "average", NOT 0.0. News sentiment is
            # mildly positive by nature (mean ~+0.17), so a 0.0 fill sits near
            # the 17th percentile and reads as bad news. signals.weights_for_date
            # z-scores this row for its ranking tilt, so zero-filling actively
            # demoted every ticker without Alpha Vantage coverage — which is the
            # whole EM sleeve and all the global ADRs. Same bug as, and same fix
            # as, sentiment.load_sentiment_panel.
            mean = scores.mean()
            sent_row = scores.fillna(mean if pd.notna(mean) else 0.0)
    except Exception:
        pass
        
    # use_sentiment must match CFG.backtest.use_sentiment_in_backtest (False),
    # otherwise the bot trades a strategy the Backtest page never validated.
    # Measured 2016-2026: the sentiment overlay is WORSE on every axis (Sharpe
    # 1.195 vs 1.271, CAGR 25.33 vs 25.52, MaxDD -25.30 vs -23.36), because
    # history only starts 2022-03 and covers 83/156 names with ZERO EM
    # coverage. Turning this back on means opting into an unvalidated,
    # coverage-biased signal — revisit only when AV backfill is broad enough
    # and a fresh A/B actually favours it.
    w = signals.weights_for_date(today, px, panels, sentiment=sent_row,
                                 use_sentiment=CFG.backtest.use_sentiment_in_backtest)
    target_weights = w[w > 0]
    
    target_positions = {}
    for t, weight in target_weights.items():
        price = float(px[t].iloc[-1])
        target_val = float(weight) * capital
        target_qty = target_val / price if price > 0 else 0
        target_positions[t] = {
            "weight": weight,
            "target_value": target_val,
            "target_qty": target_qty,
            "price": price
        }
        
    # 3. Get Current T212 Positions
    print("\nFetching Current T212 Positions...")
    current_t212 = client.get_positions()
    instruments = []
    try:
        instruments = client.get_instruments()
    except Exception as e:
        print(f"[Warn] Could not fetch instruments metadata: {e}")
        
    current_portfolio = {}
    for p in current_t212:
        raw_tick = p.get("instrument", {}).get("ticker", "")
        sym = raw_tick.split("_")[0]
        qty = float(p.get("quantity", 0))
        if abs(qty) < 0.000001:
            continue
        current_portfolio[sym] = {
            "t212_ticker": raw_tick,
            "qty": qty,
            "value": float(p.get("walletImpact", {}).get("currentValue", 0))
        }
        
    # 4. Calculate Delta & Generate Trades
    print("\n--- Trade Plan ---")
    trades_to_execute = []

    # No-trade band: ignore adjustments too small to be worth the spread. A
    # full EXIT is never banded (target_qty == 0) or dust positions would live
    # forever. See CFG.portfolio.min_trade_pct_of_book.
    min_notional = capital * getattr(
        CFG.portfolio, "min_trade_pct_of_book", 0.0)
    skipped_small = []

    def _too_small(sym: str, delta_qty: float, is_exit: bool) -> bool:
        if is_exit or min_notional <= 0:
            return False
        price = float(px[sym].iloc[-1]) if sym in px.columns else 0.0
        notional = abs(delta_qty) * price
        if notional < min_notional:
            skipped_small.append((sym, notional))
            return True
        return False

    # Process Sells (Stocks we hold but aren't in target, or hold too much of)
    for sym, current in current_portfolio.items():
        if sym not in px.columns:
            continue

        target_qty = target_positions.get(sym, {}).get("target_qty", 0)
        delta_qty = target_qty - current["qty"]

        # If we need to sell (delta is negative)
        if delta_qty < -0.01:
            is_exit = target_qty <= 0
            if _too_small(sym, delta_qty, is_exit):
                continue
            trades_to_execute.append({
                "ticker": sym,
                "t212_ticker": current["t212_ticker"],
                "side": "SELL",
                "qty": delta_qty,
                "reason": "Reduce/Exit" if target_qty > 0 else "Exit Position"
            })

    # Process Buys (Stocks in target we don't hold enough of)
    for sym, target in target_positions.items():
        current_qty = current_portfolio.get(sym, {}).get("qty", 0)
        delta_qty = target["target_qty"] - current_qty

        if delta_qty > 0.01:
            if _too_small(sym, delta_qty, is_exit=False):
                continue
            t212_ticker = _get_t212_ticker(sym, instruments, current_t212)
            trades_to_execute.append({
                "ticker": sym,
                "t212_ticker": t212_ticker,
                "side": "BUY",
                "qty": delta_qty,
                "reason": "New Position" if current_qty == 0 else "Increase Position"
            })

    if skipped_small:
        print(f"({len(skipped_small)} adjustment(s) below the £{min_notional:,.0f} "
              f"no-trade band, skipped: "
              f"{', '.join(f'{s} £{n:,.0f}' for s, n in skipped_small[:6])}"
              f"{' ...' if len(skipped_small) > 6 else ''})")

    if not trades_to_execute:
        print("Portfolio is perfectly aligned. No trades needed.")
        return

    # Sort trades: Sells first, then Buys to free up cash
    trades_to_execute.sort(key=lambda x: 0 if x["side"] == "SELL" else 1)
    
    for t in trades_to_execute:
        print(f"{t['side']:<4} {t['ticker']:<5} | Qty: {abs(t['qty']):>8.4f} | {t['reason']}")
        
    # 5. Rebalance gate — the plan above is informational on a held day.
    may_trade, reason = should_rebalance(today, force=force)
    print(f"\nRebalance gate ({CFG.portfolio.rebalance}): {reason}")
    if not may_trade:
        print("[HOLDING] No orders placed. The backtest holds between "
              "rebalances too — trading this drift daily is what turns "
              "+25.6% CAGR into -0.3%. Use --force to override.")
        return

    # 6. Execute Trades
    if not live:
        print("\n[DRY RUN] No orders placed. Run with --live to execute.")
        return

    print("\n--- Executing Trades ---")
    placed = 0
    for t in trades_to_execute:
        print(f"Submitting {t['side']} for {t['ticker']} (Qty: {t['qty']:.4f})...", end=" ", flush=True)
        try:
            # Try with progressively lower precision to bypass T212 precision limits
            order_id = None
            current_qty = t["qty"]
            
            # Start at 3 decimal places, then 2, 1, 0
            for prec in [3, 2, 1, 0]:
                q = round(current_qty, prec) if prec > 0 else int(current_qty)
                if abs(q) < 0.001:
                    break
                try:
                    resp = client.place_market_order(t["t212_ticker"], q)
                    order_id = resp.get('id')
                    print(f"SUCCESS (ID: {order_id or 'N/A'}, Executed Qty: {q})")
                    break
                except Exception as e:
                    err_msg = str(e)
                    if "quantity-precision-mismatch" in err_msg or "invalid quantity precision" in err_msg:
                        continue
                    else:
                        raise e # Re-raise if it's a different error
            
            if not order_id:
                print(f"FAILED: Could not find acceptable precision for {t['qty']}")
                continue
                
            if order_id:
                placed += 1
                try:
                    bot_file = os.path.join(CFG.paths.data_dir, "bot_orders.json")
                    bot_orders = []
                    if os.path.exists(bot_file):
                        with open(bot_file, "r") as f:
                            bot_orders = json.load(f)
                    bot_orders.append(order_id)
                    with open(bot_file, "w") as f:
                        json.dump(bot_orders, f)
                except Exception as ex:
                    print(f"Failed to log bot order ID: {ex}")
                    
            time.sleep(1.2) # Rate limit protection (1 req/sec)
        except Exception as e:
            print(f"FAILED: {e}")
            
    # Consume the period only if orders actually went through. A run that
    # placed nothing (every order failed) must be retried tomorrow, not
    # silently counted as this month's rebalance.
    if placed:
        _record_rebalance(today)
        print(f"\nExecution complete — {placed} order(s) placed. "
              f"Rebalance recorded for period {_current_period(today)}.")
    else:
        print("\nExecution complete — NO orders placed, so the rebalance was "
              "NOT recorded. The next run will retry.")


if __name__ == "__main__":
    execute_trades()

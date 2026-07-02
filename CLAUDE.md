# CLAUDE.md

Project memory for Claude Code. Read this before making changes.

## What this is

A momentum + sentiment trading research tool for ~30 large-cap US stocks.
100% free data: yfinance (prices), RSS + yfinance news + VADER (live sentiment),
Alpha Vantage NEWS_SENTIMENT (historical sentiment, free key, ~2022+).
Bloomberg-terminal-style Streamlit dashboard (`dashboard.py`) plus a CLI (`main.py`).

Not investment advice. This is a research/backtesting tool.

## Run it

```bash
pip install -r requirements.txt
python -m streamlit run dashboard.py     # dashboard (primary UI)
python main.py backtest --synthetic      # CLI, offline smoke test
python tests/test_smoke.py               # full pipeline test, no network needed
```

## Layout

- `config.py` — every tunable parameter lives here (dataclasses). Edit here, not
  hardcoded in modules.
- `src/data.py` — yfinance prices, cached to `data/price_cache.parquet`.
  `source="synthetic"` for offline testing — never silently substitute fake
  data for real data anywhere else.
- `src/momentum.py` — TSM (12-1: skips the most recent month), 52w-high ratio,
  RSI, MAs, realised vol (for inverse-vol sizing), breadth regime.
- `src/sentiment.py` — free live sentiment (RSS + yfinance news + VADER).
  Recent-only, no real history.
- `src/av_sentiment.py` — Alpha Vantage NEWS_SENTIMENT. Real history back to
  ~2022. Free tier caps at ~25 requests/day — `fetch_history()` caches and
  skips already-fetched tickers, designed to run incrementally across days.
- `src/signals.py` — turns momentum + sentiment panels into target weights.
- `src/backtest.py` — daily-mark-to-market vector backtest. Metrics MUST be
  annualised from daily returns (`×252` / `×√252`), never from the monthly
  rebalance series — that bug previously inflated Sharpe ~4.6×.
- `src/report.py` — static charts + markdown report for the CLI path.
- `dashboard.py` — Streamlit UI, modern dev/fintech aesthetic (Linear/Vercel
  style: deep slate bg `#101419`, panels `#151a21`, 1px borders, radius ≤4px,
  off-white text, Inter + JetBrains Mono for numerics; saturated green/red/amber
  reserved for data and status only). Every interactive widget needs a unique
  `key=` or Streamlit throws `StreamlitDuplicateElementId`.

## Hard-won fixes — don't reintroduce these bugs

1. **Sentiment must be real, never random/mocked.** An earlier version used
   `np.random` as a stand-in for historical sentiment. If real data isn't
   available for a date range, return zeros/neutral — don't fabricate.
2. **The LONG entry filter must not be self-contradictory.** "Near 52-week
   high" AND "RSI ≤ 30 (oversold)" almost never co-occur — that produced ~2
   trades in 11 years. Current rule: positive 12m momentum + within 30% of
   52w high + RSI in a 25–55 *pullback* band (not a crash). If changing entry
   logic, sanity-check trade count stays in the dozens-to-hundreds range over
   a 10-year backtest, not single digits.
3. **Annualise from daily data, not monthly.** The equity curve must be
   marked to market daily before computing Sharpe/vol/drawdown.

## Project agents

`.claude/agents/` defines three subagents for delegated work: `quant-researcher`
(signal/backtest changes and A/B experiments), `dashboard-engineer` (Streamlit
UI, holds the design tokens), `data-ops` (price cache, sentiment fetching,
AV rate budget). Prefer them for work in their lane — each carries the
project-specific pitfalls for its area.

## Conventions

- All money in £ in UI/report labels (user is UK-based) but yfinance returns
  USD — no FX conversion is applied; treat figures as nominal currency units,
  not GBP-converted.
- Tests: `tests/test_smoke.py` runs the whole pipeline on synthetic prices,
  fully offline. Run it after any change to `src/signals.py` or
  `src/backtest.py` — it asserts trade count > 20 and Sharpe is in a sane
  range, which would have caught both bugs above.
- Don't add paid APIs without flagging it clearly — the whole point of this
  build is free data. Alpha Vantage's free key is the one paid-adjacent step
  (still free, but requires signup) — keep it optional, never required for
  the core backtest/signals path to run.

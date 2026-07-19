# CLAUDE.md

Project memory for Claude Code. Read this before making changes.

## What this is

A momentum + sentiment trading research tool for ~132 global stocks in four
sleeves (`config.SLEEVES`): core (US large caps, all with banked AV history),
quality_value (underrated high-ROE/cheap compounders), niche_growth (liquid
mid-cap growth), global (ex-US via US-listed ADRs ONLY — native .L/.T/.DE
listings break AV sentiment + fundamentals, and LSE quotes are in pence).
Sector map in `config.SECTORS`; sleeve map in `config.TICKER_SLEEVE`.
100% free data: yfinance (prices), RSS + yfinance news + VADER (live sentiment),
Alpha Vantage NEWS_SENTIMENT (historical sentiment, free key, ~2022+).
Danelfin-style Streamlit screener (`dashboard.py`) plus a CLI (`main.py`).
Optional: GPT-4.1 Mini AI Copilot chat panel (requires OpenAI key — paid but optional).

Not investment advice. This is a research/backtesting tool.

## Run it

```bash
pip install -r requirements.txt
python -m streamlit run dashboard.py     # dashboard (primary UI)
python main.py backtest --synthetic      # CLI, offline smoke test
python tests/test_smoke.py               # full pipeline test, no network needed

# Next.js frontend (TailAdmin-based consumer UI) + FastAPI backend:
pip install fastapi uvicorn
uvicorn api.server:app --port 8000       # terminal 1 — wraps the pipeline, read-only
cd frontend && npm install && npm run dev  # terminal 2 — http://localhost:3000
```

## Next.js frontend (`frontend/` + `api/`)

- `api/server.py` — FastAPI, read-only. `/api/screener`, `/api/stock/{t}`,
  `/api/portfolio` (Trading212 Public API via `T212_API_KEY` env var — grant
  read scopes only, never order permissions), `/api/meta`. Reuses the exact
  screener-table build from dashboard.py; falls back to the real price cache
  when yfinance is unreachable (never synthetic). 15-min in-memory cache.
- `frontend/` — TailAdmin Next.js free template, pruned (ecommerce/calendar/
  forms/ui-demo pages deleted). Pages: `/` screener (tiles, top-pick cards,
  filterable/sortable table), `/stock/[ticker]` detail, `/portfolio` (T212
  holdings joined against AI Scores). New code lives in
  `src/components/screener/` and `src/lib/api.ts`. API calls are proxied via
  a rewrite in `next.config.ts` (`API_URL` env, default 127.0.0.1:8000).
- `src/svg.d.ts` was fixed to type SVG imports as components (template bug).
- Keep the Streamlit dashboard working — it's the research console; the
  Next.js app is the consumer-style UI on the same pipeline.

## Layout

- `config.py` — every tunable parameter lives here (dataclasses). Edit here, not
  hardcoded in modules.
- `src/data.py` — yfinance prices, cached to `data/price_cache.parquet`,
  with an automatic Twelve Data fallback when yfinance fails
  (`TWELVEDATA_API_KEY` in .env; free tier is paced ~1 min per 8 tickers,
  so it suits background jobs, not web requests — the API server serves
  the cache and lets `scripts/daily_fetch.py` call `refresh_price_cache()`).
  `source="synthetic"` for offline testing — never silently substitute fake
  data for real data anywhere else.
- `src/momentum.py` — TSM (12-1: skips the most recent month), 52w-high ratio,
  RSI, MAs, realised vol (for inverse-vol sizing), breadth regime, and a
  native price-normalised MACD histogram (`macd_hist` panel, pure pandas —
  no pandas-ta needed).
- `src/regime.py` — optional 3-state Gaussian-HMM regime detector
  (`CFG.momentum.regime_method = "hmm"`, needs free `hmmlearn`). Walk-forward
  refit on an expanding window — never full-sample-fit (look-ahead). Falls
  back to breadth if unavailable. Deliberately NOT the 7-state YouTube
  version: 7 states overfit daily data.
- `src/sentiment.py` — free live sentiment (RSS + yfinance news + VADER).
  Recent-only, no real history.
- `src/av_sentiment.py` — Alpha Vantage NEWS_SENTIMENT. Real history back to
  ~2022. Free tier caps at ~25 requests/day — `fetch_history()` caches and
  skips already-fetched tickers, designed to run incrementally across days.
  Each run RESUMES a ticker from the end of its contiguous cached block
  (`_resume_from`): the 1000-article request cap truncates busy tickers, so
  full coverage takes several requests per ticker across daily budgets.
  Isolated `fetch_today` snapshot rows are excluded from the block by a
  60-day gap rule — they must never mask missing history (a bug that once
  hid 25 tickers).
- `src/signals.py` — turns momentum + sentiment panels into target weights.
- `src/scoring.py` — composite AI Score (1–10) + BUY/HOLD/AVOID labels.
  Three layers: technical 45% (TSM, RSI pullback, 52w proximity, vol, MACD),
  sentiment 25% (VADER/AV score mapped to [0,1]), fundamentals 30% (ROE, P/E,
  debt-equity, margins). Each layer min-max normalised; missing columns degrade
  gracefully to 0 rather than erroring. Also emits `value_score` (0–10
  valuation-only lens, NOT blended into ai_score) and `under_radar` (strong
  fundamentals + cheap + quiet news — the rerating setup the screener's
  💎 badge and "Under the Radar" view surface). `confidence_pct` tracks how many layers
  had real data.
- `src/fundamentals.py` — fetches 12 fundamental ratios from yfinance.info
  (pe_forward, roe, debt_equity, gross_margin, revenue_growth, etc.) with a
  7-day disk cache (`data/fundamentals_cache.json`) to avoid rate-limiting.
- `src/backtest.py` — daily-mark-to-market vector backtest. Metrics MUST be
  annualised from daily returns (`×252` / `×√252`), never from the monthly
  rebalance series — that bug previously inflated Sharpe ~4.6×.
- `src/report.py` — static charts + markdown report for the CLI path.
- `dashboard.py` — Danelfin-style screener UI. Five tabs:
  SCREENER (primary): `st.column_config.ProgressColumn` for AI Score and
  Sentiment bars, `st.column_config.LineChartColumn` for 3-month price
  sparklines, emoji badges (🟢/🟡/🔴) for BUY/HOLD/AVOID, `st.metric` tiles for
  top picks, and optional GPT-4.1 Mini AI Copilot chat at the bottom.
  SIGNALS/BACKTEST/SENTIMENT/CONFIG: native Streamlit widgets; Plotly dark charts
  (colour constants at top of file) for equity curve, drawdown, monthly heatmap.
  Every interactive widget needs a unique `key=` or Streamlit throws
  `StreamlitDuplicateElementId`.

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

## Automation

A Windows Task Scheduler job ("MomentumSentiment Daily Fetch", daily 07:30,
runs on next boot if missed) executes `scripts/daily_fetch.py` via
`scripts/daily_fetch.cmd`: free RSS+VADER snapshot → incremental Alpha
Vantage history (no-op once complete) → auto-commits
`data/sentiment_history.csv`. Output goes to `outputs/daily_fetch.log`.
The .cmd wrapper hardcodes the repo and python paths — update it if either
moves. Manage with `Get-ScheduledTask`/`Unregister-ScheduledTask`.

## Data status (update when fetches run)

- AV sentiment history (2022-03-01 → 2025-12-31) in
  `data/sentiment_history.csv`, as of 2026-07-19: 45 tickers have real
  multi-year history (all kept in the core sleeve for exactly that
  reason); the ~74 quality_value/niche/global tickers added 2026-07-19
  are not started. `scripts/daily_fetch.py` now fetches in
  `config.av_fetch_order()` priority (quality_value → niche_growth →
  global → core), so new-sleeve coverage builds first; at 25 req/day
  expect several weeks for full universe coverage — no manual
  action needed. `python scripts/coverage_check.py` prints per-sleeve
  progress and says READY when the sentiment-overlay A/B is worth
  rerunning (>=80% of non-core sleeves complete); as of 2026-07-19
  core is 32/58 complete. Check progress with `_resume_from` (see
  src/av_sentiment.py) or the SENTIMENT tab.

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



# CLAUDE.md

Project memory for the AI Equity Screener & Forecasting Dashboard. Read this before making any changes.

## What this is
An AI-driven equity screening and performance forecasting tool. It processes historical market data and technical patterns (1M, 3M, 6M, 1Y horizons) to generate an "AI Score," a "Performance Forecast," and historical win-rate probabilities for global equities. 
The architecture pairs a Python/SQL data pipeline for heavy quantitative processing with a Next.js frontend for a modern, low-latency client dashboard. 

Not financial advice. This is a quantitative research and screening tool.

## Run it
```bash
# Terminal 1: Backend / Data Pipeline
cd backend
source venv/bin/activate
python -m pytest tests/              # Run core quantitative logic tests
python main.py run-pipeline --dev    # Run data ingestion & scoring locally

# Terminal 2: Frontend Dashboard
cd frontend
npm run dev                          # Start Next.js dashboard
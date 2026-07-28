# CLAUDE.md

Project memory for Claude Code. Read this before making changes.

## What this is

A momentum + sentiment trading research tool for ~156 global stocks in five
sleeves (`config.SLEEVES`): core (US large caps, all with banked AV history),
quality_value (underrated high-ROE/cheap compounders), niche_growth (liquid
mid-cap growth), global (ex-US via US-listed ADRs ONLY — native .L/.T/.DE
listings break AV sentiment + fundamentals, and LSE quotes are in pence;
includes 5 Lightman-style European value names via OTC ADRs —
Roche/Nestle/Danone/KPN/DHL, cheap + high-ROE but thin AV sentiment),
em (25 emerging-market ADRs across 11 countries — see the EM sleeve section).
Sector map in `config.SECTORS`; sleeve map in `config.TICKER_SLEEVE`;
country map in `config.COUNTRIES` (EM names only, everything else defaults
to "US" — that default is what keeps the country cap off the developed book).
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

## ALWAYS update the Data & Model page

`frontend/src/app/(admin)/(others-pages)/profile/page.tsx` (component
`DataModelPage`, nav label "Data & Model") is the user-facing explanation of
how every number in the app is produced. **It is documentation that lives in
code, so it goes stale silently — nothing fails, it just starts lying.**

Update it in the SAME change whenever you touch:
- any `SignalConfig` threshold (entry rule numbers are quoted verbatim on the page)
- the universe or sleeves (names, counts, sleeve descriptions)
- position sizing, concentration caps, `max_positions`, rebalance frequency
- scoring weights, the value score, or the Radar/under-the-radar rule
- data sources, refresh cadence, or coverage caveats
- any config default flipped from off to on

This is not optional polish. It had already drifted once: the page claimed
"positive 12-month momentum, within 30% of the 52-week high, RSI 25-55" when
config actually said >5% return, within 25%, RSI 30-50 — three wrong numbers
a user could have traded on. If a change would make a sentence on that page
untrue, fix the sentence in the same commit.

Write it for a non-technical reader: name the behaviour and the number, skip
the config key and the file path. Percentages should be derived from
`config.py`, not remembered.

## Layout

- `config.py` — every tunable parameter lives here (dataclasses). Edit here, not
  hardcoded in modules.
- `src/data.py` — yfinance prices, cached to `data/price_cache.parquet`,
  with an automatic Twelve Data fallback when yfinance fails
  (`TWELVEDATA_API_KEY` in .env; free tier is paced ~1 min per 8 tickers,
  so it suits background jobs, not web requests — the API server serves
  the cache and lets `scripts/daily_fetch.py` call `refresh_price_cache()`).
  `source="synthetic"` for offline testing — never silently substitute fake
  data for real data anywhere else. `load_point_in_time_universe()` +
  `data/universe_2015.csv` are SCAFFOLDING for a survivorship-free universe,
  NOT a finished fix: the CSV is a 5-row stub, and yfinance can't fetch prices
  for delisted names (the ones bias hides), so the current backtest is still
  survivorship-biased — see data/universe_2015.README.md.
- `src/momentum.py` — TSM (12-1: skips the most recent month), 52w-high ratio,
  RSI, MAs, realised vol (for inverse-vol sizing), breadth regime, and a
  native price-normalised MACD histogram (`macd_hist` panel, pure pandas —
  no pandas-ta needed). `breadth_regime` also has a cross-sectional vol-spike
  override: if universe avg 20d realised vol > 2.5x its trailing-year median,
  force risk_off regardless of breadth (catches crashes weeks earlier).
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
  Inverse-vol sizing has a *partial* fallback (missing vol -> median inverse-vol,
  not a full equal-weight collapse) and caps any single position at 2x equal
  weight, so a low-vol name can't balloon to 20%+ of the book.
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
  rebalance series — that bug previously inflated Sharpe ~4.6×. `_apply_sector_cap`
  caps any sector at 40% of gross long exposure but PRESERVES the original gross
  (must renormalise to gross, never 1.0, or it undoes the risk_off 0.5 brake).
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
   52w high + RSI in a 30–50 *pullback* band (not a crash). If changing entry
   logic, sanity-check trade count stays in the dozens-to-hundreds range over
   a 10-year backtest, not single digits.
3. **Annualise from daily data, not monthly.** The equity curve must be
   marked to market daily before computing Sharpe/vol/drawdown.
4. **Missing sentiment is NOT 0.0.** News sentiment is mildly positive by
   nature (the AV log: mean +0.169, 83.7% of scores above zero), so filling
   gaps with 0.0 does not mean "neutral" — it lands near the 17th percentile
   of the cross-section. Because `src/signals.py` z-scores the panel to build
   its ranking tilt, that penalised every ticker with no AV coverage at
   z = -0.97 (vs +0.14 for covered names), silently demoting the entire global
   and EM sleeves for having no data. Cost ~0.9pp of CAGR. `load_sentiment_panel`
   now fills with each day's cross-sectional mean; a wholly empty day still
   falls back to 0.0, which is correctly inert. If you add another data layer
   with a skewed distribution, ask what its true neutral value is — it is
   almost never zero.

## Academic strategy features (opt-in, all default OFF)

Six research-paper features are implemented as config flags, all defaulting
to their behaviour-preserving value so the default backtest is unchanged:
- CS1 vol targeting (Barroso & Santa-Clara) — `PortfolioConfig.use_vol_targeting`
- CS2 crash-risk filter (Daniel & Moskowitz) — `PortfolioConfig.use_crash_risk_filter`
- CS3 residual momentum (Blitz/Huij/Martens) — `MomentumConfig.use_residual_momentum`
- CS4 purged walk-forward (Lopez de Prado) — always on for reporting only
  (`_purged_walk_forward`; old `_walk_forward_legacy` kept). Emits both new
  keys and legacy aliases so the dashboard/report/web UI need no changes.
- CS5 momentum-quality gate (Gray & Vogel) — `SignalConfig.momentum_quality_min`
- CS6 consistent momentum (Chen/Chou/Hsieh) — `SignalConfig.require_consistent_momentum`

**A/B result (2016–2026, momentum-only): none beat the baseline on Sharpe.**
Baseline (all off), 137-name universe = CAGR 22.8% / Sharpe 1.211 / MaxDD
-23%. NOTE: re-running that same 137-name universe on the price cache as of
2026-07-27 now gives CAGR 24.62 / Sharpe 1.259 / MaxDD -23.12. The drift is
pure data refresh, not a code change — verified by running the pre-EM code
from git stash on the same cache and getting identical numbers. Compare any
new A/B against a freshly-run baseline, not against the 22.8 figure.
(Was 24.9% / 1.248 on 132 names before the 5 European value adds — those
value names cost ~2pp CAGR as expected drag on a momentum book). Vol targeting best case Sharpe 1.151 at an 18% target (12% is
far too low for a long-only book and de-levers to ~15% CAGR; above ~19% it
becomes a 2x leverage dial, not a brake — and it is redundant with the
existing vol-spike regime override). Residual momentum HURT (Sharpe 0.97 —
the free size/no-HML proxy can't reproduce the paper's FF3 result). Crash
filter was inert (its bear+rebound trigger never fired in this bull period).
Quality gate and consistent momentum were mild drags. Kept all OFF. These
papers were validated on long-short factor portfolios, broad universes, real
bear markets and full FF3 factors — conditions this test doesn't reproduce.
Revisit on a survivorship-free universe (see load_point_in_time_universe).

## Emerging-markets sleeve (added 2026-07-27)

25 liquid EM ADRs across 11 countries, added per an EM strategy guidance
document. Same ADR-only rule as `global` — native listings break AV sentiment
and yfinance fundamentals, and aren't USD.

Two flags shipped with it:
- `PortfolioConfig.use_country_cap` / `max_country_weight` (0.20) — **default
  TRUE** after the A/B. Caps any single **non-US** country's share of gross
  long. `_apply_country_cap` in src/backtest.py mirrors `_apply_sector_cap`,
  including preserving the original gross rather than renormalising to 1.0.
- `MomentumConfig.use_vol_adjusted_momentum` — **default FALSE**, it lost.
  Ranks on return/vol (`momentum.vol_adj_tsm`) instead of raw return.

**Current shipping baseline (156 names, country cap on, sentiment overlay off,
2016–2026): CAGR 25.52 / Sharpe 1.271 / MaxDD -23.36 / 1195 trades / 59.6% win.**

**Vol-adjusted momentum is applied to RANKING ONLY, never the LONG gate.**
`trend_tsm_min = 0.05` means "5% trailing return"; comparing it against a
return/vol ratio would silently mean something completely different. If you
ever wire it into the gate, re-derive the threshold in ratio units first.

### A/B result (2016–2026, momentum-only, `scripts/em_ab_test.py`)

Pre-EM baseline on 131 names: CAGR 25.89 / Sharpe 1.270 / MaxDD -22.86.

| Arm | CAGR | Sharpe | MaxDD | EM seats |
|-----|------|--------|-------|----------|
| 1 baseline (no EM) | 25.94 | 1.273 | -22.86 | 0% |
| 2 +EM sleeve | 25.72 | 1.286 | -23.36 | 12.9% |
| 3 +country cap | 26.08 | 1.296 | -23.36 | 12.9% |
| 4 +cap +vol-adj mom | 21.30 | 1.157 | -21.77 | 12.0% |

Figures re-run 2026-07-28 after a price-cache refresh. Between the two runs the
EM arm's CAGR delta moved from -0.72pp to -0.22pp and its Sharpe delta from
-0.008 to +0.013 — the SIGN FLIPPED on a routine data refresh. Treat that as
the real finding: the EM effect is inside the noise floor, so do not build an
argument on its direction either way.

- **EM sleeve: roughly neutral.** Sharpe -0.008 (noise), CAGR -0.72pp. Crucially
  this is a REAL null, not a false negative: EM won 13.6% of book seats against
  16% of the universe, and all 25 names were held at some point. The
  US-calibrated gate is NOT mechanically excluding EM — that worry was checked
  and disproved by the `em_selection_rate_pct` instrumentation.
- **Country cap: marginally positive** (+0.010 Sharpe vs arm 2), noise on its
  own, kept ON as a cheap concentration guard. Trade count is identical with it
  on (1193) because it reweights without changing selection.

  **KNOWN LIMITATION — do not oversell this cap.** `_apply_country_cap` scales
  the breaching country down and then renormalises back to the original gross.
  When the breaching country IS effectively the whole long book, scaling then
  renormalising is the IDENTITY, so the cap does nothing. Verified: a
  100%-Brazil book passes through completely unchanged; a 40%-Brazil book
  alongside US names is correctly trimmed to 20%. So it guards ordinary
  over-concentration, NOT the case where only one region qualifies. Making it
  bite there would mean cutting gross exposure (holding cash) rather than
  redistributing — a real strategy change, deliberately not made.

  Uncapped exposure measured over 2016-2026: Brazil peaked at 100% of gross
  long, China at 31.5%, with >20% breaches on only ~1.8% of days.
- **Vol-adjusted momentum: clearly hurts.** Sharpe 1.150, CAGR -3.99pp, alpha
  -2.85pp. It does de-risk (MaxDD -21.77, vol -1.13pp) but surrenders far more
  return than risk. Kept OFF. Mechanism, worth understanding before anyone
  retries it: dividing by vol ranks DOWN exactly the high-vol names that
  produce the big winners, truncating the right tail (largest trade
  +118.95% -> +70.26%, p99 40.56 -> 35.21). It raises win rate to 60.18% while
  LOWERING expectancy 3.01 -> 2.61 — a standing warning that win rate alone
  ranks these arms wrongly. Judge on profit factor/expectancy, not win rate.

### Sentiment overlay: why `use_sentiment_in_backtest` stays False

Measured 2016–2026 (156 names, country cap on): overlay OFF = CAGR 25.52 /
Sharpe 1.271 / MaxDD -23.36; overlay ON = 25.33 / 1.195 / -25.30. Worse on
every axis. Three causes, largest first:
1. **A ~60% dead zone.** `sentiment_history.csv` starts 2022-03-01 but the
   backtest starts 2016. When the overlay is on, `signals.py` SWITCHES the
   ranking tilt from 52w-high proximity to sentiment — so for the first six
   years it deletes 30% of a working ranking signal and substitutes a constant.
2. The zero-fill bug (hard-won fix #4 above), now fixed — was worth ~0.9pp CAGR.
3. Even where data exists, news sentiment ranks worse than 52w-high proximity.

Coverage as of 2026-07-27: 83/156 tickers well covered (>250 rows), and they
are ALL core/quality_value/niche — zero global, only 6 EM tickers with any
history at all. Re-test the overlay once AV backfill reaches the other sleeves;
this is a coverage verdict, not a verdict on sentiment.

### EM caveats that must not be rediscovered later

- **Survivorship bias is WORSE in EM than in the US sleeve**, not equal. These
  25 ADRs all survived to 2026; EM loses names to terminated ADR programmes,
  take-privates and the 2022 China delisting scare at a much higher rate than
  US large caps. Discount any favourable EM result accordingly.
- **Ragged history**: NU starts 2021-12, PDD 2018-07, YUMC 2016-10. The EM
  sleeve's effective size grows through the sample, so early-period "EM
  exposure" is really just the legacy Taiwan/China/Brazil names.
- **Tencent and Samsung are deliberately absent.** No liquid US ADR exists
  (TCEHY/SSNLF are pink sheets with stale quotes) — exactly the data failure
  the ADR-only rule prevents. The same reason makes frontier EM and much of
  mainstream EM (Indonesia, Thailand, Malaysia, Philippines, Saudi, Poland,
  Turkey) simply unreachable on free data. "Niche EM" here can only ever mean
  smaller countries that happen to have a liquid ADR.
- **ERJ (Embraer) was selected but dropped**: yfinance returns
  `YFTzMissingError` for ERJ, ERJ.SA and EMBR3.SA alike despite the company
  trading normally. Re-add if the upstream gap is fixed.
- `UniverseConfig.em_benchmark_tickers` = EEM/EMXC/FRDM. Over 2016-2026 SPY
  compounded 14.94% vs EEM 9.20%; EMXC (from 2017-07) and FRDM (from 2019-06)
  launched mid-sample so their CAGRs are NOT directly comparable to SPY's.

## Project agents

`.claude/agents/` defines three subagents for delegated work: `quant-researcher`
(signal/backtest changes and A/B experiments), `dashboard-engineer` (Streamlit
UI, holds the design tokens), `data-ops` (price cache, sentiment fetching,
AV rate budget). Prefer them for work in their lane — each carries the
project-specific pitfalls for its area.

## Restarting the backend/frontend dev servers

Always use `scripts/restart_servers.ps1` (kills by **port**, not by PID) rather
than stopping a remembered uvicorn/node PID directly. `uvicorn --reload`
spawns a reloader process plus a separate worker process that holds the
socket; killing only the reloader PID orphans the worker, which keeps the
port and keeps serving with the old `.env`/code — so a `.env` edit + "restart"
can silently do nothing. Symptom: an endpoint keeps returning stale data
(e.g. `T212_ENV`) after an edit you're sure was saved and a restart you're
sure you ran — check `Get-NetTCPConnection -LocalPort 8000` for the real
owning PID before assuming the code is wrong.

```powershell
powershell -File scripts\restart_servers.ps1            # both servers
powershell -File scripts\restart_servers.ps1 -Backend   # just :8000
powershell -File scripts\restart_servers.ps1 -Frontend  # just :3000
```

## Automation

A Windows Task Scheduler job ("MomentumSentiment Daily Fetch", daily 07:30,
runs on next boot if missed) executes `scripts/daily_fetch.py` via
`scripts/daily_fetch.cmd`: price cache refresh → free RSS+VADER snapshot →
incremental Alpha Vantage history (no-op once complete) → portfolio
signal-drop email alert (`scripts/portfolio_alerts.py`, see below) →
auto-commits `data/sentiment_history.csv`. Output goes to
`outputs/daily_fetch.log`. The .cmd wrapper hardcodes the repo and python
paths — update it if either moves. Manage with
`Get-ScheduledTask`/`Unregister-ScheduledTask`.

### Portfolio signal-drop email alert

`scripts/portfolio_alerts.py` re-imports `api/server.py`'s own T212 fetch +
`_signal_weights_at` logic directly (no FastAPI process needs to be running)
so it always agrees with what the Portfolio page shows. Best-effort, skipped
silently if `T212_API_KEY`/`GMAIL_USER`/`GMAIL_APP_PASSWORD` aren't set in
`.env`. Sends via Gmail SMTP — needs a Google App Password (2-Step
Verification required): https://myaccount.google.com/apppasswords. This app
is long-only with no sell button, so this is the only nudge the user gets
when a holding drops off the Signal Book; check manually via the Portfolio
page in the meantime. Manual run: `python scripts/portfolio_alerts.py`.

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
uvicorn api.server:app --port 8000 --reload


# Terminal 2: Frontend Dashboard
cd frontend
npm run dev                          # Start Next.js dashboard
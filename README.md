# Free Momentum + Sentiment Trading Model

A clean, runnable research engine that combines **price momentum** with **free
news sentiment**. No paid APIs, no keys. Built to run in VS Code and be edited
with Claude Code.

- **Prices** — [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance), multi-year history, free
- **News** — yfinance per-ticker headlines **+** finance RSS feeds (`feedparser`), free
- **Scoring** — [VADER](https://github.com/cjhutto/vaderSentiment), offline, no model download, no key

---

## Quick start

```bash
cd momentum_sentiment_free
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# ▶ THE DASHBOARD (Bloomberg-style terminal UI):
python -m streamlit run dashboard.py                  # opens http://localhost:8501

# …or the command line:
python main.py backtest --synthetic   # offline proof it runs (no internet)
python main.py backtest               # real Yahoo data
python main.py signals                # today's signals + free news sentiment
python main.py fetch-sentiment        # log today's free sentiment
python main.py fetch-av-sentiment     # pull Alpha Vantage history (needs key)
```

Outputs from the CLI land in `outputs/`. The dashboard is interactive and needs
no files.

---

## The dashboard

`python -m streamlit run dashboard.py` launches a dark, monospace terminal UI
with four panels:

- **SIGNALS** — today's signal book: regime badge, long/short table colour-coded
  by momentum and sentiment, full universe screen. Toggle the sentiment source
  (free / Alpha Vantage) and refresh live.
- **BACKTEST** — set parameters, hit run, get the metric grid (CAGR, active
  return, Sharpe, Sortino, max DD, win rate…), equity vs benchmark, drawdown,
  monthly-returns heatmap, walk-forward table, and a downloadable trade blotter.
- **SENTIMENT** — fetch and inspect logged sentiment; coverage stats by source;
  per-ticker history chart.
- **CONFIG** — live-tune the entry rules (RSI band, 52w floor, sentiment floor,
  max positions, shorts) and watch signals change.

No network? Flip **OFFLINE DEMO** in the sidebar to drive the whole terminal on
synthetic prices.

---

## Alpha Vantage sentiment (free key, ~2022+ history)

The free RSS/yfinance source is recent-only. **Alpha Vantage's `NEWS_SENTIMENT`
archive reaches back to ~March 2022**, so it's the free way to get real
multi-year sentiment for an actual sentiment backtest.

1. Get a free key: <https://www.alphavantage.co/support/#api-key>
2. `cp .env.example .env` and paste your key into `.env`.
3. Pull history (free tier ≈ 25 requests/day, so it fetches a few tickers per
   run and caches — run it across a few days for a big universe):
   ```bash
   python main.py fetch-av-sentiment --start 2022-03-01
   ```
   …or click **FETCH ALPHA VANTAGE** on the dashboard's SENTIMENT tab.
4. Once history is logged, turn on the overlay:
   ```bash
   python main.py backtest --use-sentiment
   ```
   or tick **SENTIMENT OVERLAY** in the dashboard's BACKTEST panel.

Scores are aggregated per day, weighting each article by Alpha Vantage's
relevance score for that ticker.

---

## ⚠️ An honest note on free sentiment data (read this)

This is the single most important design point, and it's why the previous
version's results were meaningless.

**Free news only exists for recent dates.** You can get *today's* headlines for
free, but you cannot get a clean, point-in-time archive of every headline for
every stock going back 10 years without paying (RavenPack, Bloomberg, etc.).

So this project is deliberately split — but Alpha Vantage gives you a real free
shortcut to historical sentiment (see above):

| Mode | What it uses | Honest? |
|---|---|---|
| **Backtest** (`backtest`) | Price/momentum signals only — fully historical & free | ✅ Rigorous |
| **Backtest** (`backtest --use-sentiment`) | + Alpha Vantage sentiment (~2022+) or your own logged history | ✅ Real sentiment over the covered window |
| **Live signals** (`signals`) | Momentum **+** live free news sentiment | ✅ Real sentiment, today |

The previous engine "backtested sentiment" by feeding the model **random
numbers** as historical sentiment. That's not a sentiment strategy — it's noise.
This project refuses to do that.

**Two ways to get real historical sentiment, both free:**
1. **Alpha Vantage** (fastest) — `NEWS_SENTIMENT` reaches back to ~March 2022.
   See the "Alpha Vantage sentiment" section above.
2. **Accumulate your own** — every `signals` / `fetch-sentiment` run appends
   today's scores to `data/sentiment_history.csv`, so you build a point-in-time
   history going forward. Tip: schedule `fetch-sentiment` daily (cron / Task
   Scheduler).

Then enable the overlay (`backtest --use-sentiment`, or `SENTIMENT OVERLAY` in
the dashboard).

---

## What was fixed vs the earlier engine

1. **Sentiment is real, not random.** Live headlines scored by VADER, with an
   exponential recency decay (`src/sentiment.py`).
2. **The entry filter actually trades.** The old LONG rule needed a stock to be
   *near its 52-week high* **and** *RSI ≤ 30 (oversold)* simultaneously — nearly
   impossible, so it took ~2 trades in 11 years. The new rule expresses a
   **pullback within an uptrend**: positive 12-month momentum, within 30% of the
   52w high, above its long MA, with RSI in a *dip* band (≈25–55). On a 30-stock
   / 10-year test it takes ~340 trades with a sane Sharpe.
3. **Correct performance maths.** The book is marked to market **daily**, so
   Sharpe/volatility annualise correctly. The old code annualised a *monthly*
   equity series as if daily and inflated Sharpe ~4.6× (the "Sharpe 3.33" was a
   bug; the strategy actually lagged buy-and-hold).
4. **Realistic frictions kept:** T+1 execution, 10 bps cost on turnover, 30%
   gross short cap, monthly rebalance, walk-forward out-of-sample folds.

---

## Project layout

```
momentum_sentiment_free/
├── dashboard.py            Bloomberg-style Streamlit terminal (the UI)
├── main.py                 CLI: backtest | signals | fetch-sentiment | fetch-av-sentiment
├── config.py               ALL tunable parameters (edit here)
├── requirements.txt
├── .env.example            -> copy to .env, add Alpha Vantage key
├── src/
│   ├── data.py             free prices (yfinance + cache; explicit synthetic mode)
│   ├── momentum.py         TSM, 52w-high ratio, RSI, MAs, breadth regime
│   ├── sentiment.py        free news (RSS + yfinance) + VADER + decay + history log
│   ├── av_sentiment.py     Alpha Vantage NEWS_SENTIMENT (free, ~2022+ history)
│   ├── signals.py          the FIXED double-filter -> target weights
│   ├── backtest.py         daily-MTM vector backtest + correct metrics
│   └── report.py           charts + markdown report
├── tests/test_smoke.py     full offline run (no network needed)
├── data/                   price cache + sentiment_history.csv (gitignored)
└── outputs/                charts, report, trade log
```

---

## The strategy in one paragraph

For each stock, score **trend** (12-month return > 0, price within 30% of its
52-week high and above its long moving average) and look for a **pullback entry**
(RSI dipping into ≈25–55, not a crash). In live mode, require **non-negative news
sentiment** to confirm. Rank qualifying names by a blend of momentum strength and
sentiment, hold the top *N* equal-weighted, rebalance monthly, and scale exposure
down when market **breadth** (a free, price-based regime proxy) is weak. Shorts
are available but off by default.

---

## Editing with Claude Code

Everything tunable lives in `config.py`. Common asks:

- *"Change the universe to FTSE 100 stocks"* → edit `UniverseConfig.tickers` and
  `benchmark_ticker` (e.g. `^FTSE`). Add name variants to `COMPANY_KEYWORDS`.
- *"Make it trade more / fewer names"* → `SignalConfig.rsi_pullback_max`,
  `near_floor_52w`, `PortfolioConfig.max_positions`.
- *"Turn on shorting"* → `SignalConfig.enable_shorts = True`.
- *"Swap VADER for FinBERT"* → replace `score_text()` in `src/sentiment.py` with a
  `transformers` FinBERT call (heavier install, more accurate on financial text).
- *"Add a new signal"* → add a panel function in `src/momentum.py`, include it in
  `build_panels()`, and reference it in `src/signals.weights_for_date()`.

Run `python tests/test_smoke.py` after edits — it executes the whole pipeline
offline and asserts the engine still trades sensibly.

---

## Disclaimer

This is a **research and educational tool**. Backtested or simulated results do
not predict future performance, the sentiment overlay is experimental, and
nothing here is financial advice. Validate independently before risking capital.

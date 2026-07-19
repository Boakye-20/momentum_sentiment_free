# Your Playbook — what to actually do

A simple guide for running this project day to day. (CLAUDE.md is the
technical memory for the AI; this file is for you.)

> Not financial advice. This is a research tool — it finds candidates and
> tests ideas, it doesn't guarantee profits.

---

## Day to day: do nothing

The scheduled task ("MomentumSentiment Daily Fetch", 07:30 every morning)
collects news sentiment automatically and saves it to git. It's currently
filling in history for the ~74 new stocks (underrated/value, niche, global)
— that takes roughly 5–6 weeks and needs no action from you.

---

## When you want to look at stocks

**Option A — new web app** (nicer UI, needs Node.js installed once):

```
# terminal 1 (repo root):
uvicorn api.server:app --port 8000
# terminal 2:
cd frontend
npm run dev        # first time: npm install first
```

Then open http://localhost:3000. The Portfolio page connects to Trading212
using `T212_API_KEY` + `T212_API_SECRET` from the `.env` file (already set
up — read-only scopes only, never grant order permissions).

**Option B — Streamlit research console** (always works, no Node needed):

```
python -m streamlit run dashboard.py
```

On the **SCREENER** tab, use the **Strategy view** dropdown:

| View | What it shows |
|---|---|
| 🌐 All stocks | Everything, ranked by AI Score |
| ⭐ Top Value | Decent-quality companies that are cheap |
| 💎 Under the Radar | Strong fundamentals + cheap + nobody talking about it — the "underrated" setup you asked for |
| 🚀 Momentum Leaders | Top 20 by 12-month momentum |
| 🌍 Global (ex-US) | The international names (ASML, Novo Nordisk, TSMC, …) |

A 💎 next to a stock's signal badge means it qualifies as under-the-radar.

---

## Once a week: check if the big test is ready

```
python scripts/coverage_check.py
```

- **NOT READY** → do nothing, check again next week.
- **READY** → run the A/B test it prints:

```
python main.py backtest
python main.py backtest --use-sentiment
```

Compare the **Sharpe ratio** of the two runs (risk-adjusted return — higher
is better; ignore CAGR alone):

- Sentiment run's Sharpe **wins** → sentiment is earning its keep. Turn it
  on permanently: in `config.py` set `use_sentiment_in_backtest: True`.
- Sentiment run's Sharpe **still loses** → leave it off. That's a real
  answer, not a failure — you tested it properly and momentum-only won.

(Current score to beat, from 2026-07-19: momentum-only Sharpe **0.968**,
with-sentiment 0.891.)

---

## Things to remember

- **Trust Sharpe over CAGR.** More return from a lot more risk is not a win.
- **The backtest flatters slightly.** The stock list was picked today, so
  past results carry some survivorship bias. Treat numbers as indicative.
- **Don't chase the 🚀 list blindly** — that's the most crowded trade. The
  💎 and ⭐ lists are where this tool is designed to add something different.
- **Free data has limits.** ~25 Alpha Vantage requests/day is the bottleneck;
  don't add lots more tickers or history stops filling in.

## If something breaks

- Daily fetch log: `outputs/daily_fetch.log`
- Full offline health check: `python tests/test_smoke.py`
- Ask Claude Code — CLAUDE.md has the technical detail.

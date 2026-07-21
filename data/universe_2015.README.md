# universe_2015.csv — point-in-time constituents (STUB, not complete)

This file backs `data.load_point_in_time_universe()`, the mechanism for a
survivorship-free backtest. **It is a stub with 5 real example rows, not a
usable universe** (the S&P 500 has ~500 names; this has 5). Do not run a
"survivorship-free" backtest off it and trust the result until it is filled in.

## Format

```
ticker,added_date,removed_date,removal_reason
AAPL,1982-11-30,,                       # still a member -> blank removed_date
BBBY,1996-01-01,2019-01-02,dropped_from_index   # a name that later died
```

A ticker is counted for a given backtest start date if
`added_date <= start` and (`removed_date` is blank OR `removed_date > start`).
The point is the removed/delisted names — those are exactly the ones
survivorship bias hides.

## To complete it

Populate from the "Changes" table of
<https://en.wikipedia.org/wiki/List_of_S%26P_500_companies> back to your
backtest start (2015), plus every ticker that was a member at the start.

## The hard limit (read before relying on this)

**yfinance usually cannot fetch prices for delisted tickers** — BBBY, and
every other name that went to zero or was acquired. Those are precisely the
names you need for an honest test. Even with a complete CSV, the free price
source will have gaps on the failures, which re-introduces a softer
survivorship bias. A genuinely survivorship-free backtest most likely needs a
paid data vendor (e.g. an EOD provider with delisted history). Treat this
file as the scaffolding, not the finished fix.

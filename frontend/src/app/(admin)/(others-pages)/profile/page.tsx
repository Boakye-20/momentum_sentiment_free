"use client";
import React, { useEffect, useState } from "react";
import { fetchMeta, Meta } from "@/lib/api";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03]">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
        {value}
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-white/[0.03]">
      <h2 className="mb-3 text-base font-semibold text-gray-900 dark:text-white/90">
        {title}
      </h2>
      <div className="space-y-3 text-sm leading-6 text-gray-600 dark:text-gray-300">
        {children}
      </div>
    </div>
  );
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-gray-100 pb-3 last:border-0 last:pb-0 dark:border-gray-800 sm:flex-row sm:gap-4">
      <span className="w-40 shrink-0 font-medium text-gray-900 dark:text-white/90">
        {term}
      </span>
      <span>{children}</span>
    </div>
  );
}

export default function DataModelPage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetchMeta().catch(() => null).then((m) => {
      if (m) setMeta(m);
      else setErr("API not reachable. Start it with: uvicorn api.server:app --port 8000");
    });
  }, []);

  const universe = meta ? meta.buy + meta.hold + meta.avoid : 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
          Data & Model
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          How every number in this app is calculated, in plain English
        </p>
      </div>

      {err && (
        <div className="rounded-xl border border-warning-500/40 bg-warning-50 p-5 text-sm text-gray-700 dark:bg-warning-500/10 dark:text-gray-200">
          {err}
        </div>
      )}

      {meta && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="Stocks covered" value={String(universe)} />
          <Stat label="Prices as of" value={meta.as_of} />
          <Stat label="Buy / Hold / Avoid" value={`${meta.buy} / ${meta.hold} / ${meta.avoid}`} />
          <Stat label="Average score" value={`${meta.avg_score} / 10`} />
        </div>
      )}

      <Section title="The AI Score (1 to 10)">
        <p>
          Every stock gets one overall score out of 10. It blends three independent
          views of the company, each answering a different question:
        </p>
        <div className="space-y-3 pt-1">
          <Row term="Technicals (45%)">
            Is the share price behaving well? Positive momentum over the last 12
            months, trading near its 52-week high, in a healthy dip rather than a
            crash (RSI), above its long-term trend line, and not too volatile.
          </Row>
          <Row term="News sentiment (25%)">
            Is the news flow positive or negative? See the sentiment section below.
          </Row>
          <Row term="Fundamentals (30%)">
            Is it a good business at a fair price? Return on equity, forward P/E,
            debt levels, profit margins and revenue growth, each compared across
            the whole universe.
          </Row>
        </div>
        <p>
          Scores of <strong>6.5 or higher are labelled BUY</strong>, below{" "}
          <strong>3.5 AVOID</strong>, everything in between HOLD. If a layer has no
          data for a stock (for example missing fundamentals), the score is built
          from the layers that do, and the confidence figure on the stock page
          tells you how much real data backed it.
        </p>
      </Section>

      <Section title="How to use the signals (and how to sell)">
        <p>
          There is no separate SELL button, and that is on purpose. This is a{" "}
          <strong>long-only</strong> model: it only tells you what is worth owning,
          never to bet against a stock. AVOID does not mean &quot;short it&quot;. It
          means &quot;this is a poor stock to own right now&quot;. Selling happens by
          a rule, checked on a schedule, not as a labelled alert.
        </p>
        <p>
          The routine that matches the backtest is a <strong>monthly review</strong>.
          Pick one day a month and, for every stock you hold:
        </p>
        <div className="space-y-3 pt-1">
          <Row term="Still a BUY?">
            If its score is still strong and it is still near the top of the list,
            keep holding. Winners are meant to be held while they keep working.
          </Row>
          <Row term="Slipped to HOLD?">
            It is weakening. Watch it. If better-scoring stocks are available, it may
            be the one to replace.
          </Row>
          <Row term="Dropped to AVOID?">
            The model no longer supports owning it (momentum gone, trend broken, or
            fundamentals and news turned against it). This is your exit signal: close
            the position.
          </Row>
          <Row term="Fill the gaps">
            Put the money from anything you sold into the current highest-scoring
            BUYs you do not already own.
          </Row>
        </div>
        <p>
          The roughly 30-day holding period you see in the backtest is not a fixed
          rule. It is simply a result of reviewing monthly: the shortest a position
          can last is one month, and a strong stock is held for as many months as it
          keeps qualifying. There is also no &quot;stop trading it&quot; list. A stock
          you sell can be bought back later if it earns its way back onto the list.
        </p>
      </Section>

      <Section title="News sentiment, explained">
        <p>
          Every day the system collects headlines about each stock from free news
          feeds and scores each one from <strong>-1 (very negative)</strong> to{" "}
          <strong>+1 (very positive)</strong> using VADER, a standard
          text-analysis model. Recent headlines count more than old ones, and a
          stock&apos;s sentiment number is the weighted average over the last few
          days. Historical sentiment (back to 2022) comes from Alpha Vantage, which
          scores professional financial news articles the same way.
        </p>
        <p>
          A score around 0 means quiet or mixed news. That is not a bad thing: the
          combination of strong fundamentals, cheap valuation and quiet news is
          exactly what the &quot;Radar&quot; tag looks for, because good companies
          nobody is talking about are where re-ratings tend to start.
        </p>
        <p className="text-xs text-gray-400">
          Note: sentiment history for the newer stocks in the universe is still
          being collected (the free data source allows ~25 requests per day), so
          some names show neutral sentiment until their history fills in.
        </p>
      </Section>

      <Section title="Timeframes: what the model uses vs what you see">
        <div className="space-y-3">
          <Row term="Model horizon">
            The score is built for a <strong>weeks-to-months</strong> holding
            period, not day trading. Its core signal is &quot;12-1
            momentum&quot;: the return over the last 12 months, excluding the
            most recent month. The last month is skipped deliberately, because
            stocks that just spiked tend to pull back short-term.
          </Row>
          <Row term="1M / 3M / 6M / 1Y toggle">
            The toggle on the screener only changes the return column and mini
            chart you see in the table. It never changes the AI Score, so you can
            check how a highly scored stock has behaved recently without the
            ranking moving under you.
          </Row>
          <Row term="Other indicators">
            RSI uses 14 days (the industry standard), the trend filter uses a
            200-day average, and volatility uses the last 3 months of daily moves.
          </Row>
        </div>
      </Section>

      <Section title="The strategy views on the screener">
        <p>
          The buttons above the stock table are preset screens over the same
          scored universe. They never change the scores themselves, only which
          stocks you are looking at and how they are ordered.
        </p>
        <div className="space-y-3 pt-1">
          <Row term="All Stocks">
            The whole universe, ranked by AI Score from best to worst.
          </Row>
          <Row term="Buy Rated">
            Only stocks whose AI Score is 6.5 or higher, the model&apos;s BUY
            threshold. This is the shortlist the model likes right now.
          </Row>
          <Row term="Top Value">
            The 25 cheapest stocks by Value score, filtered to decent quality
            (fundamentals score of at least 5). For hunting bargains rather
            than momentum.
          </Row>
          <Row term="Under the Radar">
            Stocks carrying the Radar tag: strong fundamentals, cheap
            valuation, quiet news, and not a mega-cap. The classic setup for a
            re-rating before the crowd notices. Often a short list, and that
            is by design.
          </Row>
          <Row term="Momentum Leaders">
            The 25 strongest stocks by 12-month momentum (excluding the most
            recent month). The market&apos;s current winners. Be aware this is
            the most crowded, fastest-moving list.
          </Row>
          <Row term="Global (ex-US)">
            Only the international names held via US listings: ASML, Novo
            Nordisk, TSMC, Toyota and the rest of the Global group.
          </Row>
        </div>
      </Section>

      <Section title="Value score and the Radar tag">
        <p>
          Separate from the AI Score, each stock gets a <strong>Value score</strong>{" "}
          measuring pure cheapness: forward P/E, EV/EBITDA, price-to-book,
          price-to-sales and PEG, each ranked across the universe. It is kept out
          of the main score on purpose, so you can look for quality (high AI
          Score) and cheapness (high Value score) independently.
        </p>
        <p>
          The <strong>Radar</strong> tag marks stocks with strong fundamentals, a
          cheap valuation and quiet news at the same time. That is the classic
          &quot;good company, nobody excited yet&quot; setup. Mega-caps (above
          roughly $200B) are excluded on principle: a trillion-dollar company
          with neutral headlines is heavily covered news balancing out, not a
          stock nobody is watching.
        </p>
      </Section>

      <Section title="The universe: four groups of stocks">
        <div className="space-y-3">
          <Row term="Core">
            Around 58 large US companies (Apple, JPMorgan, Chevron...). The
            stable backbone with the deepest data history.
          </Row>
          <Row term="Quality Value">
            Around 32 excellent but under-covered businesses: high returns on
            capital, sensible prices, little media attention (McKesson, AutoZone,
            Chubb, homebuilders).
          </Row>
          <Row term="Niche Growth">
            Around 22 liquid mid-cap growth names with real revenue (CrowdStrike,
            Datadog, Axon). The most speculative story stocks are deliberately
            excluded.
          </Row>
          <Row term="Global">
            Around 20 international leaders held via their US listings (ASML,
            Novo Nordisk, TSMC, Toyota), so all data sources keep working.
          </Row>
        </div>
      </Section>

      <Section title="Data sources and freshness">
        <div className="space-y-3">
          <Row term="Prices">
            Yahoo Finance, daily closes back to 2015, refreshed when the API
            restarts or its 15-minute cache expires.
          </Row>
          <Row term="Live sentiment">
            Free financial RSS feeds plus Yahoo Finance headlines, collected
            automatically every morning at 07:30.
          </Row>
          <Row term="Historical sentiment">
            Alpha Vantage news scores back to March 2022, filling in gradually
            within the free daily budget.
          </Row>
          <Row term="Fundamentals">
            Yahoo Finance company data, cached for 7 days to avoid rate limits.
          </Row>
        </div>
        <p className="pt-1 text-xs text-gray-400">
          All data sources are free. This is a research tool, not investment
          advice; scores summarise history and history does not guarantee future
          returns.
        </p>
      </Section>
    </div>
  );
}

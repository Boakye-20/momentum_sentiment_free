"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { fetchMeta, Meta } from "@/lib/api";
import {
  BoltIcon,
  AlertIcon,
  TableIcon,
  GridIcon,
  ChatIcon,
  TimeIcon,
  ShootingStarIcon,
  GroupIcon,
  PlugInIcon,
} from "@/icons";

type IconType = typeof BoltIcon;

const TOC: { id: string; label: string; icon: IconType }[] = [
  { id: "signal-book", label: "The Signal Book", icon: BoltIcon },
  { id: "when-to-sell", label: "When to sell", icon: AlertIcon },
  { id: "portfolio-journal", label: "Portfolio & Journal", icon: TableIcon },
  { id: "browse", label: "The Browse page", icon: GridIcon },
  { id: "sentiment", label: "News sentiment", icon: ChatIcon },
  { id: "timeframes", label: "Timeframes", icon: TimeIcon },
  { id: "value-radar", label: "Value score & Radar", icon: ShootingStarIcon },
  { id: "universe", label: "The universe", icon: GroupIcon },
  { id: "data-sources", label: "Data sources", icon: PlugInIcon },
];

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

function SectionIcon({ icon: Icon }: { icon: IconType }) {
  return (
    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-500 dark:bg-brand-500/10 dark:text-brand-400">
      <Icon className="size-5" />
    </span>
  );
}

function Section({
  id,
  title,
  icon,
  children,
}: {
  id: string;
  title: string;
  icon: IconType;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-24 rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-white/[0.03]"
    >
      <div className="mb-4 flex items-center gap-3">
        <SectionIcon icon={icon} />
        <h2 className="text-base font-semibold text-gray-900 dark:text-white/90">
          {title}
        </h2>
      </div>
      <div className="space-y-3 text-sm leading-6 text-gray-600 dark:text-gray-300">
        {children}
      </div>
    </section>
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

function TableOfContents({ active }: { active: string }) {
  return (
    <nav className="hidden lg:block">
      <div className="sticky top-24 rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-white/[0.03]">
        <p className="px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
          On this page
        </p>
        <ul className="space-y-0.5">
          {TOC.map(({ id, label, icon: Icon }) => (
            <li key={id}>
              <a
                href={`#${id}`}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition ${
                  active === id
                    ? "bg-brand-50 font-medium text-brand-600 dark:bg-brand-500/10 dark:text-brand-400"
                    : "text-gray-500 hover:bg-gray-50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-white/[0.04] dark:hover:text-gray-200"
                }`}
              >
                <Icon className="size-4 shrink-0" />
                {label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

export default function DataModelPage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [err, setErr] = useState("");
  const [active, setActive] = useState(TOC[0].id);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchMeta().catch(() => null).then((m) => {
      if (m) setMeta(m);
      else setErr("API not reachable. Start it with: uvicorn api.server:app --port 8000");
    });
  }, []);

  useEffect(() => {
    const sections = TOC.map(({ id }) => document.getElementById(id)).filter(
      (el): el is HTMLElement => el !== null
    );
    if (sections.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-96px 0px -70% 0px", threshold: 0 }
    );
    sections.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [meta]);

  const stats = useMemo(
    () =>
      meta
        ? [
            { label: "Stocks covered", value: String(meta.universe_size) },
            { label: "Prices as of", value: meta.as_of },
            { label: "Signal Book picks", value: String(meta.signal_count) },
            { label: "Gross long", value: `${meta.gross_long_pct}%` },
          ]
        : [],
    [meta]
  );

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <span className="mb-2 inline-block rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
          Documentation
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
          Data &amp; Model
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          How every number in this app is calculated, and how the Signal Book
          drives every page.
        </p>
      </div>

      {err && (
        <div className="mb-6 rounded-xl border border-warning-500/40 bg-warning-50 p-5 text-sm text-gray-700 dark:bg-warning-500/10 dark:text-gray-200">
          {err}
        </div>
      )}

      {meta && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          {stats.map((s) => (
            <Stat key={s.label} label={s.label} value={s.value} />
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
        <TableOfContents active={active} />

        <div ref={contentRef} className="space-y-6">
          <Section id="signal-book" title="The Signal Book: the one rating system in this app" icon={BoltIcon}>
            <p>
              Every page in this app, Browse, Signals, Portfolio, Journal and
              Backtest, is built around a <strong>single, rules-based
              system</strong>: the Signal Book. It is exactly what the Backtest
              page&apos;s numbers (CAGR, Sharpe) measure, so there is one
              consistent answer to &quot;does this stock currently qualify&quot;
              everywhere you look.
            </p>
            <div className="space-y-3 pt-1">
              <Row term="Entry rule">
                A 12-month return above <strong>5%</strong> (a real winner, not
                barely positive), trading within <strong>25%</strong> of the
                52-week high, price above its 200-day average, and RSI in a{" "}
                <strong>30-50</strong> <em>pullback</em> band (a dip within an
                uptrend, not a crash). A stock passing all four becomes a pick.
              </Row>
              <Row term="Position sizing">
                Picks are weighted <strong>inverse to their volatility</strong>,
                so calmer stocks get a larger slice, capped at 2x an equal-weight
                share so one very low-vol name can&apos;t dominate the book. Up
                to <strong>15 positions</strong> at a time.
              </Row>
              <Row term="Concentration limits">
                No single sector may exceed <strong>40%</strong> of the invested
                book, and no single country outside the US may exceed{" "}
                <strong>20%</strong>. Both work by trimming the oversized slice
                and spreading it across the other holdings, so the limit only
                bites when there is somewhere else to put the money — in a month
                where nearly every qualifying stock is from one country, it
                cannot help. Treat these as a guard against ordinary
                over-concentration, not as protection against a market where
                only one region qualifies.
              </Row>
              <Row term="Rebalance">
                Monthly, matching the backtest exactly. A pick&apos;s weight
                shown on Signals, Portfolio and Journal is the % of your entered
                capital the strategy would allocate to it today.
              </Row>
              <Row term="Not picked">
                A stock missing from the Signal Book just does not currently
                meet the entry filter&apos;s momentum/RSI/52-week conditions.
                It is not blacklisted, and can reappear on a later review.
              </Row>
            </div>
          </Section>

          <Section id="when-to-sell" title="When to sell" icon={AlertIcon}>
            <p>
              There is no separate SELL button, on purpose: the model tells you
              what currently qualifies, and selling is a rule you check on a
              schedule, not a labelled alert. The routine that matches the
              backtest exactly is a <strong>monthly review</strong>. Pick one day
              a month and, for every stock you hold, check its current Signal
              Book status, shown directly on <strong>Portfolio</strong> and{" "}
              <strong>Journal</strong> (or look it up on <strong>Signals</strong>):
            </p>
            <div className="space-y-3 pt-1">
              <Row term="Still a pick?">
                If it still appears in the Signal Book (any weight greater than
                0%), keep holding, even if its weight has changed since you
                bought it. The strategy still wants this position.
              </Row>
              <Row term="Not picked anymore?">
                That is the mechanical exit signal: it no longer meets the entry
                filter&apos;s conditions. Sell it and put the freed capital into
                a current pick you do not already own.
              </Row>
              <Row term="No blacklist">
                A stock that drops off the list is not banned. If it re-qualifies
                on a later monthly review, the Signal Book will pick it again and
                you can buy back in then.
              </Row>
              <Row term="Email alert">
                A daily check compares your Trading212 holdings against the
                Signal Book and emails you if a position has dropped off, so
                you don&apos;t have to remember to look. It is a nudge, not a
                replacement for the monthly review.
              </Row>
            </div>
            <p>
              The roughly 30-day holding period you see in the backtest is not a
              fixed rule. It is simply a result of reviewing monthly: the
              shortest a position can last is one month, and a strong stock is
              held for as many months as it keeps qualifying.
            </p>
          </Section>

          <Section id="portfolio-journal" title="Portfolio and Journal" icon={TableIcon}>
            <div className="space-y-3">
              <Row term="Portfolio">
                Your actual Trading212 holdings (read-only), one row per ticker
                you currently own, cross-checked against today&apos;s Signal
                Book status, the same check used for the sell decision above.
              </Row>
              <Row term="Journal">
                Every filled Trading212 order, individually, not aggregated
                like Portfolio. Each trade shows its Signal Book weight both{" "}
                <strong>at the time you traded</strong> and <strong>now</strong>,
                so you can see whether you followed the strategy and whether
                that pick has since dropped off the list.
              </Row>
            </div>
          </Section>

          <Section id="browse" title="The Browse page" icon={GridIcon}>
            <p>
              Browse is for exploring stocks you <strong>don&apos;t currently
              hold</strong> (anything in your Portfolio is excluded
              automatically). It has no scores or badges, on purpose, it is a
              plain, quick way to look around the universe, not a second
              decision system.
            </p>
            <div className="space-y-3 pt-1">
              <Row term="Group tabs">
                All / Core / Quality Value / Niche Growth / Global, filtering
                which sleeve of the universe you are looking at.
              </Row>
              <Row term="1M / 3M / 6M / 1Y">
                Changes the return shown on every card and the sparkline range,
                plus which names appear under Top gainers/losers.
              </Row>
              <Row term="Top gainers / losers">
                The five best and worst performers over the selected period,
                scoped to whichever group tab is currently active.
              </Row>
              <Row term="Search">
                Filters by ticker or company name across whichever group is
                selected.
              </Row>
            </div>
            <p>
              Clicking any card opens the same chart page used everywhere else in
              the app, with that stock&apos;s Signal Book status, fundamentals
              and sentiment if you want that context, it is just not shown on
              the Browse cards themselves.
            </p>
          </Section>

          <Section id="sentiment" title="News sentiment, explained" icon={ChatIcon}>
            <p>
              Every day the system collects headlines about each stock from free
              news feeds and scores each one from <strong>-1 (very
              negative)</strong> to <strong>+1 (very positive)</strong> using
              VADER, a standard text-analysis model. Recent headlines count more
              than old ones, and a stock&apos;s sentiment number is the weighted
              average over the last few days. Historical sentiment (back to
              2022) comes from Alpha Vantage, which scores professional
              financial news articles the same way. The Signal Book uses this as
              a secondary tilt on top of momentum, not a gate on its own.
            </p>
            <p className="text-xs text-gray-400">
              Note: sentiment history for the newer stocks in the universe is still
              being collected (the free data source allows ~25 requests per day), so
              some names have no score yet — the emerging-markets group especially.
              Where a score is missing the stock is treated as{" "}
              <em>average</em> rather than as bad news, so a gap in the data can
              never count against a stock. The historical Backtest page runs on
              momentum alone for the same reason: sentiment history only starts in
              2022 and does not yet cover enough of the universe to test fairly.
            </p>
          </Section>

          <Section id="timeframes" title="Timeframes: what the model uses vs what you see" icon={TimeIcon}>
            <div className="space-y-3">
              <Row term="Model horizon">
                The Signal Book is built for a <strong>weeks-to-months</strong>{" "}
                holding period, not day trading. Its core signal is &quot;12-1
                momentum&quot;: the return over the last 12 months, excluding the
                most recent month. The last month is skipped deliberately, because
                stocks that just spiked tend to pull back short-term.
              </Row>
              <Row term="1M / 3M / 6M / 1Y toggle">
                The toggle on the Browse page only changes the return shown and
                the sparkline range on each card. It never touches the Signal
                Book underneath, so you can check how a stock has behaved
                recently without anything actually being recalculated.
              </Row>
              <Row term="Other indicators">
                RSI uses 14 days (the industry standard), the trend filter uses a
                200-day average, and volatility uses the last 3 months of daily moves.
              </Row>
            </div>
          </Section>

          <Section id="value-radar" title="Value score and the Radar tag" icon={ShootingStarIcon}>
            <p>
              Independent of the Signal Book, each stock also gets a{" "}
              <strong>Value score</strong> measuring pure cheapness: forward
              P/E, EV/EBITDA, price-to-book, price-to-sales and PEG, each ranked
              across the universe. It is a separate lens for hunting bargains,
              not a factor in what the Signal Book picks or how it sizes
              positions.
            </p>
            <p>
              The <strong>Radar</strong> tag marks stocks with strong
              fundamentals, a cheap valuation and quiet news at the same time.
              That is the classic &quot;good company, nobody excited yet&quot;
              setup. Mega-caps (above roughly $200B) are excluded on principle: a
              trillion-dollar company with neutral headlines is heavily covered
              news balancing out, not a stock nobody is watching.
            </p>
          </Section>

          <Section id="universe" title="The universe: five groups of stocks" icon={GroupIcon}>
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
              <Row term="Global (developed)">
                Around 19 developed-market leaders outside the US, held via their
                US-listed ADR (ASML, Novo Nordisk, Toyota, Sony), plus five cheap
                European quality names from the Lightman funds (Roche, Nestle,
                Danone, KPN, DHL).
              </Row>
              <Row term="Emerging Markets">
                Around 25 emerging-market companies across 11 countries, again
                only via US-listed ADRs (TSMC, Alibaba, HDFC Bank, Itau,
                MercadoLibre, Gold Fields). Liquid large and mid caps only. Two
                well-known names are deliberately absent: Tencent and Samsung
                have no properly traded US listing, and their thinly-traded
                stand-ins give unreliable prices.
              </Row>
            </div>
            <p className="pt-1 text-xs text-gray-400">
              Emerging markets are held for diversification rather than for
              extra return. On the historical test they performed roughly in
              line with the rest of the book, and because this test can only
              include companies that still exist today, their real record is if
              anything slightly flattered.
            </p>
          </Section>

          <Section id="data-sources" title="Data sources and freshness" icon={PlugInIcon}>
            <div className="space-y-3">
              <Row term="Prices">
                Yahoo Finance, daily closes back to 2015. Refreshed automatically
                once a day by a scheduled job shortly after 07:30; the API also
                tops up on restart if its 15-minute in-memory cache has expired.
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
              advice; the Signal Book summarises history and history does not
              guarantee future returns.
            </p>
          </Section>
        </div>
      </div>
    </div>
  );
}

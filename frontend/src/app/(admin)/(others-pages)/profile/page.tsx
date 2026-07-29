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
              Every page is built on one rules-based system: the Signal Book.
              It is exactly what the Backtest page&apos;s numbers measure, so
              &quot;does this stock qualify&quot; has one answer everywhere.
            </p>
            <div className="space-y-3 pt-1">
              <Row term="Entry rule">
                12-month return above <strong>5%</strong>, within{" "}
                <strong>25%</strong> of the 52-week high, price above its
                200-day average, and RSI <strong>30-50</strong> (a dip in an
                uptrend, not a crash). All four required.
              </Row>
              <Row term="Position sizing">
                Weighted <strong>inverse to volatility</strong>, so calmer
                stocks get a larger slice, capped at 2x equal weight. Up to{" "}
                <strong>15 positions</strong>.
              </Row>
              <Row term="Concentration limits">
                No sector above <strong>40%</strong> of the book, no non-US
                country above <strong>20%</strong>. Both trim the oversized
                slice and spread it across the other holdings, so they only bite
                when there is somewhere else to put the money. In a month where
                nearly every pick comes from one country, they cannot help.
              </Row>
              <Row term="Rebalance">
                <strong>Monthly.</strong> The list refreshes daily but is only
                meant to be acted on once a month. Trading the daily changes
                turns a backtested +25.6% a year into roughly 0%. A pick&apos;s
                weight is the % of your capital allocated to it.
              </Row>
              <Row term="Not picked">
                Does not meet the entry conditions today. Not blacklisted, and
                can reappear.{" "}
                <strong>On a random day this is not a sell signal</strong>:
                names near the RSI edge drop on and off constantly. Only your
                review day counts.
              </Row>
            </div>
          </Section>

          <Section id="when-to-sell" title="When to sell" icon={AlertIcon}>
            <p>
              There is no SELL button by design: selling is a rule you check on
              a schedule. The routine that matches the backtest is a{" "}
              <strong>monthly review</strong>. Pick one day a month and check
              each holding&apos;s status on <strong>Portfolio</strong> or{" "}
              <strong>Journal</strong>:
            </p>
            <div className="space-y-3 pt-1">
              <Row term="Still a pick?">
                Any weight above 0% means keep holding, even if the weight has
                changed since you bought it.
              </Row>
              <Row term="Not picked anymore?">
                <em>On your review day</em>, that is the exit signal: sell and
                rotate into a current pick you don&apos;t own. On any other day,
                ignore it. A stock can leave and rejoin several times in a month,
                and selling each time is the most expensive mistake available
                here.
              </Row>
              <Row term="No blacklist">
                Dropping off is not a ban. If it re-qualifies on a later
                review, the Signal Book picks it again.
              </Row>
              <Row term="Email alert">
                A daily check emails you if a holding drops off.{" "}
                <strong>Information, not an instruction</strong>: act only if it
                is still off on your review day.
              </Row>
              <Row term="The automated bot">
                Enforces this for you. Runs every morning, trades once a month,
                holds otherwise, and skips adjustments under ~0.5% of your book.
              </Row>
            </div>
            <p>
              The ~30-day holding period in the backtest is not a rule. It falls
              out of reviewing monthly, and a strong stock is held for as long as
              it keeps qualifying.
            </p>
            <p className="text-xs text-gray-400">
              Why frequency matters: identical rules return ~25.6% a year
              monthly (23% worst fall), roughly half that weekly, and ~0% daily
              (42% fall).
            </p>
          </Section>

          <Section id="portfolio-journal" title="Portfolio and Journal" icon={TableIcon}>
            <div className="space-y-3">
              <Row term="Portfolio">
                Your Trading212 holdings (read-only), one row per ticker,
                checked against today&apos;s Signal Book status.
              </Row>
              <Row term="Journal">
                Every filled order individually. Each shows its Signal Book
                weight <strong>when you traded</strong> and <strong>now</strong>,
                so you can see whether you followed the strategy.
              </Row>
            </div>
          </Section>

          <Section id="browse" title="The Browse page" icon={GridIcon}>
            <p>
              Browse covers stocks you <strong>don&apos;t hold</strong>{" "}
              (Portfolio names are excluded). No scores or badges by design: a
              quick way to look around, not a second decision system.
            </p>
            <div className="space-y-3 pt-1">
              <Row term="Group tabs">
                All / Core / Quality Value / Niche Growth / Global / Emerging
                Markets, filtering which sleeve you are looking at.
              </Row>
              <Row term="1M / 3M / 6M / 1Y">
                Changes the return and sparkline range on each card, and which
                names appear under Top gainers/losers.
              </Row>
              <Row term="Top gainers / losers">
                Best and worst five over the selected period, scoped to the
                active tab.
              </Row>
              <Row term="Search">
                Filters by ticker or name within the selected group.
              </Row>
            </div>
            <p>
              Clicking a card opens the full chart page, with that stock&apos;s
              Signal Book status, fundamentals and sentiment.
            </p>
          </Section>

          <Section id="sentiment" title="News sentiment, explained" icon={ChatIcon}>
            <p>
              Each day the system scores headlines from free news feeds using
              VADER, from <strong>-1 (very negative)</strong> to{" "}
              <strong>+1 (very positive)</strong>. Recent headlines count more,
              and a stock&apos;s number is the weighted average over the last few
              days. History back to 2022 comes from Alpha Vantage. The Signal
              Book uses this as a secondary tilt on momentum, not a gate.
            </p>
            <p className="text-xs text-gray-400">
              History for newer names is still being collected (~25 requests a
              day), so some have no score yet, the emerging-markets group
              especially. A missing score counts as <em>average</em>, not bad
              news, so a data gap never counts against a stock. The Backtest page
              runs on momentum alone for the same reason.
            </p>
          </Section>

          <Section id="timeframes" title="Timeframes: what the model uses vs what you see" icon={TimeIcon}>
            <div className="space-y-3">
              <Row term="Model horizon">
                Built for <strong>weeks-to-months</strong> holds, not day
                trading. The core signal is 12-1 momentum: the 12-month return
                excluding the most recent month, which is skipped because stocks
                that just spiked tend to pull back.
              </Row>
              <Row term="1M / 3M / 6M / 1Y toggle">
                Only changes the return and sparkline shown on Browse cards. It
                never touches the Signal Book underneath.
              </Row>
              <Row term="Other indicators">
                RSI 14 days, trend filter 200-day average, volatility from the
                last 3 months of daily moves.
              </Row>
            </div>
          </Section>

          <Section id="value-radar" title="Value score and the Radar tag" icon={ShootingStarIcon}>
            <p>
              Separate from the Signal Book, each stock gets a{" "}
              <strong>Value score</strong> for cheapness: forward P/E, EV/EBITDA,
              price-to-book, price-to-sales and PEG, ranked across the universe.
              A lens for bargains, not a factor in what gets picked.
            </p>
            <p>
              The <strong>Radar</strong> tag marks strong fundamentals, cheap
              valuation and quiet news together: the &quot;good company, nobody
              excited yet&quot; setup. Mega-caps above ~$200B are excluded, since
              neutral headlines there mean heavy coverage balancing out, not
              obscurity.
            </p>
          </Section>

          <Section id="universe" title="The universe: five groups of stocks" icon={GroupIcon}>
            <div className="space-y-3">
              <Row term="Core">
                ~58 large US companies (Apple, JPMorgan, Chevron). The stable
                backbone with the deepest data history.
              </Row>
              <Row term="Quality Value">
                ~32 under-covered businesses: high returns on capital, sensible
                prices, little media attention (McKesson, AutoZone, Chubb).
              </Row>
              <Row term="Niche Growth">
                ~22 liquid mid-cap growth names with real revenue (CrowdStrike,
                Datadog, Axon). Speculative story stocks are excluded.
              </Row>
              <Row term="Global (developed)">
                ~19 developed-market leaders outside the US via US-listed ADRs
                (ASML, Novo Nordisk, Toyota, Sony), plus five cheap European
                quality names (Roche, Nestle, Danone, KPN, DHL).
              </Row>
              <Row term="Emerging Markets">
                ~25 emerging-market companies across 11 countries, again only
                via US-listed ADRs (TSMC, Alibaba, HDFC Bank, Itau, MercadoLibre,
                Gold Fields). Liquid large and mid caps only. Tencent and Samsung
                are absent: neither has a properly traded US listing, and their
                stand-ins give unreliable prices.
              </Row>
            </div>
            <p className="pt-1 text-xs text-gray-400">
              Emerging markets are held for diversification, not extra return.
              They performed roughly in line with the rest of the book, and since
              the test only includes companies that still exist, that record is if
              anything flattered.
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

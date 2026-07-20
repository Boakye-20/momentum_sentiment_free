"use client";
import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Badge from "@/components/ui/badge/Badge";
import Sparkline from "./Sparkline";
import ScoreBar from "./ScoreBar";
import RadarTag from "./RadarTag";
import Copilot from "./Copilot";
import { fetchScreener, fmtPct, sleeveLabel, Stock } from "@/lib/api";

const VIEWS = [
  "All stocks",
  "Buy rated",
  "Top Value",
  "Under the Radar",
  "Momentum Leaders",
  "Global (ex-US)",
] as const;
type View = (typeof VIEWS)[number];

// Display timeframes: trading days per window. The AI Score itself always
// uses the model's 12-1 momentum; this only changes the return column
// and sparkline shown in the table.
const PERIODS = { "1M": 21, "3M": 63, "6M": 126, "1Y": 252 } as const;
type Period = keyof typeof PERIODS;

type SortKey = "ai_score" | "period_ret" | "sentiment_score" | "last_price" | "ticker";

function actionBadge(s: Stock) {
  const color =
    s.action === "BUY" ? "success" : s.action === "AVOID" ? "error" : "warning";
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge size="sm" color={color}>
        {s.action}
      </Badge>
      {s.under_radar ? <RadarTag /> : null}
    </span>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03]">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className={`mt-1.5 text-2xl font-semibold tracking-tight ${accent ?? "text-gray-900 dark:text-white/90"}`}>
        {value}
      </p>
    </div>
  );
}

export default function ScreenerDashboard() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [asOf, setAsOf] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("All stocks");
  const [period, setPeriod] = useState<Period>("3M");
  const [sleeve, setSleeve] = useState("all");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("ai_score");
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    fetchScreener()
      .then((r) => {
        setStocks(r.stocks);
        setAsOf(r.as_of);
      })
      .catch(() =>
        setError(
          "Could not reach the API. Start it with: uvicorn api.server:app --port 8000 (from the repo root)."
        )
      )
      .finally(() => setLoading(false));
  }, []);

  const sleeves = useMemo(
    () => Array.from(new Set(stocks.map((s) => s.sleeve))).sort(),
    [stocks]
  );

  const periodReturn = React.useCallback(
    (s: Stock): number | null => {
      const t = s.price_trend;
      if (!t || t.length < 2) return null;
      const slice = t.slice(-Math.min(PERIODS[period] + 1, t.length));
      return slice[slice.length - 1] / slice[0] - 1;
    },
    [period]
  );

  const filtered = useMemo(() => {
    let out = stocks;
    if (view === "Buy rated") out = out.filter((s) => s.action === "BUY");
    if (view === "Top Value")
      out = [...out].sort((a, b) => (b.value_score ?? 0) - (a.value_score ?? 0)).slice(0, 25);
    if (view === "Under the Radar") out = out.filter((s) => s.under_radar);
    if (view === "Momentum Leaders")
      out = [...out].sort((a, b) => (b.mom_12m ?? -9) - (a.mom_12m ?? -9)).slice(0, 25);
    if (view === "Global (ex-US)") out = out.filter((s) => s.sleeve === "global");
    if (sleeve !== "all") out = out.filter((s) => s.sleeve === sleeve);
    if (query)
      out = out.filter((s) =>
        s.ticker.toLowerCase().includes(query.toLowerCase())
      );
    return [...out].sort((a, b) => {
      const av =
        sortKey === "period_ret" ? periodReturn(a) : (a[sortKey] as number | string | null);
      const bv =
        sortKey === "period_ret" ? periodReturn(b) : (b[sortKey] as number | string | null);
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortAsc ? cmp : -cmp;
    });
  }, [stocks, view, sleeve, query, sortKey, sortAsc, periodReturn]);

  const buy = stocks.filter((s) => s.action === "BUY").length;
  const avoid = stocks.filter((s) => s.action === "AVOID").length;
  const avg = stocks.length
    ? stocks.reduce((a, s) => a + s.ai_score, 0) / stocks.length
    : 0;
  const topPicks = [...stocks].sort((a, b) => b.ai_score - a.ai_score).slice(0, 4);

  const sort = (k: SortKey) => {
    if (k === sortKey) setSortAsc(!sortAsc);
    else {
      setSortKey(k);
      setSortAsc(false);
    }
  };
  const arrow = (k: SortKey) => (sortKey === k ? (sortAsc ? " ↑" : " ↓") : "");

  if (loading)
    return <p className="p-8 text-gray-500 dark:text-gray-400">Loading scores…</p>;
  if (error)
    return (
      <div className="rounded-2xl border border-warning-500/40 bg-warning-50 p-6 text-sm text-gray-700 dark:bg-warning-500/10 dark:text-gray-200">
        {error}
      </div>
    );

  const staleDays = asOf
    ? Math.round((Date.now() - new Date(asOf).getTime()) / 86400000)
    : 0;

  return (
    <div className="space-y-6">
      {staleDays > 5 && (
        <div className="rounded-xl border border-warning-500/40 bg-warning-50 px-4 py-3 text-sm text-gray-700 dark:bg-warning-500/10 dark:text-gray-200">
          Prices last updated <b>{asOf}</b> ({staleDays} days ago). The live
          yfinance fetch failed, so you&apos;re seeing cached data. Restart
          the API (or wait 15 min for its cache to expire) to retry.
        </div>
      )}
      {/* Summary tiles */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 md:gap-6">
        <Tile label="BUY signals" value={String(buy)} accent="text-success-600" />
        <Tile label="HOLD" value={String(stocks.length - buy - avoid)} />
        <Tile label="AVOID" value={String(avoid)} accent="text-error-500" />
        <Tile label="Avg AI Score" value={`${avg.toFixed(1)} / 10`} />
      </div>

      {/* Top pick cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 md:gap-6">
        {topPicks.map((s) => (
          <Link
            key={s.ticker}
            href={`/stock/${s.ticker}`}
            className="rounded-2xl border border-gray-200 bg-white p-5 transition hover:shadow-md dark:border-gray-800 dark:bg-white/[0.03]"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-800 dark:text-white/90">
                  {s.ticker}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {s.name ?? s.sector}
                </p>
              </div>
              {actionBadge(s)}
            </div>
            <div className="mt-3 flex items-end justify-between">
              <div>
                <p className="text-lg font-bold text-gray-800 dark:text-white/90">
                  {s.last_price.toFixed(2)}
                </p>
                <p
                  className={`text-xs font-medium ${
                    (s.mom_12m ?? 0) >= 0 ? "text-success-600" : "text-error-500"
                  }`}
                >
                  {fmtPct(s.mom_12m)} · 12m
                </p>
              </div>
              <Sparkline data={s.price_trend} width={90} height={30} />
            </div>
          </Link>
        ))}
      </div>

      {/* Filters + table */}
      <div className="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
        <div className="flex flex-col gap-3 border-b border-gray-100 p-4 dark:border-gray-800 sm:flex-row sm:items-center">
          <div className="flex flex-wrap gap-2">
            {VIEWS.map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  view === v
                    ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10"
                }`}
              >
                {v}
              </button>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex rounded-lg border border-gray-200 p-0.5 dark:border-gray-700">
              {(Object.keys(PERIODS) as Period[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                    period === p
                      ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                      : "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
            <select
              value={sleeve}
              onChange={(e) => setSleeve(e.target.value)}
              className="rounded-lg border border-gray-200 bg-transparent px-3 py-1.5 text-sm text-gray-600 dark:border-gray-700 dark:text-gray-300 dark:bg-gray-900"
            >
              <option value="all">All groups</option>
              {sleeves.map((s) => (
                <option key={s} value={s}>
                  {sleeveLabel(s)}
                </option>
              ))}
            </select>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search ticker…"
              className="w-36 rounded-lg border border-gray-200 bg-transparent px-3 py-1.5 text-sm text-gray-600 placeholder:text-gray-400 dark:border-gray-700 dark:text-gray-300"
            />
          </div>
        </div>

        <div className="max-h-[560px] max-w-full overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 bg-white dark:bg-gray-900">
              <tr className="border-b border-gray-100 text-xs uppercase text-gray-500 dark:border-gray-800 dark:text-gray-400">
                <th className="cursor-pointer px-5 py-3" onClick={() => sort("ticker")}>
                  Ticker{arrow("ticker")}
                </th>
                <th className="px-5 py-3">Signal</th>
                <th className="cursor-pointer px-5 py-3" onClick={() => sort("ai_score")}>
                  AI Score{arrow("ai_score")}
                </th>
                <th className="cursor-pointer px-5 py-3" onClick={() => sort("sentiment_score")}>
                  Sentiment{arrow("sentiment_score")}
                </th>
                <th className="cursor-pointer px-5 py-3" onClick={() => sort("period_ret")}>
                  {period} Return{arrow("period_ret")}
                </th>
                <th className="cursor-pointer px-5 py-3" onClick={() => sort("last_price")}>
                  Price{arrow("last_price")}
                </th>
                <th className="px-5 py-3">3m Trend</th>
                <th className="px-5 py-3">Sector</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr
                  key={s.ticker}
                  className="border-b border-gray-50 transition hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-white/[0.02]"
                >
                  <td className="px-5 py-3">
                    <Link
                      href={`/stock/${s.ticker}`}
                      className="font-semibold text-gray-800 hover:text-brand-500 dark:text-white/90"
                    >
                      {s.ticker}
                    </Link>
                    <span className="block text-xs text-gray-400">
                      {s.name ?? sleeveLabel(s.sleeve)}
                    </span>
                  </td>
                  <td className="px-5 py-3">{actionBadge(s)}</td>
                  <td className="px-5 py-3">
                    <ScoreBar score={s.ai_score} />
                  </td>
                  <td className="px-5 py-3 text-gray-600 dark:text-gray-300">
                    {s.sentiment_score == null ? "-" : s.sentiment_score.toFixed(2)}
                  </td>
                  <td
                    className={`px-5 py-3 font-medium ${
                      (periodReturn(s) ?? 0) >= 0 ? "text-success-600" : "text-error-500"
                    }`}
                  >
                    {fmtPct(periodReturn(s))}
                  </td>
                  <td className="px-5 py-3 text-gray-700 dark:text-gray-300">
                    {s.last_price.toFixed(2)}
                  </td>
                  <td className="px-5 py-3">
                    <Sparkline data={s.price_trend.slice(-PERIODS[period])} />
                  </td>
                  <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                    {s.sector}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="px-5 py-3 text-xs text-gray-400">
          {filtered.length} stocks · data as of {asOf} · research tool, not
          investment advice
        </p>
      </div>

      <Copilot />
    </div>
  );
}

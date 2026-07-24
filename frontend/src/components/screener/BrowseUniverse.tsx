"use client";
import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Sparkline from "@/components/screener/Sparkline";
import { fetchScreener, fetchPortfolio, sleeveLabel, Stock } from "@/lib/api";

const SLEEVE_ORDER = ["core", "quality_value", "niche_growth", "global"];
const PERIODS = { "1M": 21, "3M": 63, "6M": 126, "1Y": 252 } as const;
type Period = keyof typeof PERIODS;

interface Row extends Stock {
  periodReturn: number | null;
  trendSlice: number[];
}

function Card({ s }: { s: Row }) {
  const up = (s.periodReturn ?? 0) >= 0;
  return (
    <Link
      href={`/stock/${s.ticker}`}
      className="rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-sm dark:border-gray-800 dark:bg-white/[0.03] dark:hover:border-brand-500/40"
    >
      <div className="mb-1 flex items-baseline justify-between">
        <span className="font-semibold text-gray-800 dark:text-white/90">{s.ticker}</span>
        <span className="text-sm text-gray-500 dark:text-gray-400">{s.last_price.toFixed(2)}</span>
      </div>
      {s.name && <p className="mb-2 truncate text-xs text-gray-400">{s.name}</p>}
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-gray-400">{s.sector}</span>
        <span className={`text-xs font-medium ${up ? "text-success-600" : "text-error-500"}`}>
          {s.periodReturn != null ? `${(s.periodReturn * 100).toFixed(1)}%` : "-"}
        </span>
      </div>
      <Sparkline data={s.trendSlice} width={140} height={32} />
    </Link>
  );
}

export default function BrowseUniverse() {
  const [stocks, setStocks] = useState<Stock[] | null>(null);
  const [held, setHeld] = useState<Set<string>>(new Set());
  const [err, setErr] = useState("");
  const [period, setPeriod] = useState<Period>("3M");
  const [sleeve, setSleeve] = useState<string>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchScreener()
      .then((r) => setStocks(r.stocks))
      .catch((e) => setErr(String(e)));
    // Best-effort: if Trading212 isn't connected, just show every stock.
    fetchPortfolio()
      .then((r) => setHeld(new Set((r.positions ?? []).map((p) => p.ticker))))
      .catch(() => setHeld(new Set()));
  }, []);

  const rows: Row[] = useMemo(() => {
    if (!stocks) return [];
    const days = PERIODS[period];
    return stocks
      .filter((s) => !held.has(s.ticker))
      .map((s) => {
        const trend = s.price_trend ?? [];
        const slice = trend.slice(-Math.min(days + 1, trend.length));
        const periodReturn = slice.length > 1 ? slice[slice.length - 1] / slice[0] - 1 : null;
        return { ...s, periodReturn, trendSlice: trend.slice(-days) };
      });
  }, [stocks, held, period]);

  const filtered = useMemo(() => {
    let out = rows;
    if (sleeve !== "all") out = out.filter((s) => s.sleeve === sleeve);
    if (search.trim()) {
      const q = search.trim().toUpperCase();
      out = out.filter(
        (s) => s.ticker.toUpperCase().includes(q) || (s.name ?? "").toUpperCase().includes(q)
      );
    }
    return out;
  }, [rows, sleeve, search]);

  const groups = useMemo(() => {
    const bySleeve = new Map<string, Row[]>();
    for (const s of filtered) {
      const key = s.sleeve || "core";
      if (!bySleeve.has(key)) bySleeve.set(key, []);
      bySleeve.get(key)!.push(s);
    }
    for (const list of bySleeve.values()) {
      list.sort((a, b) => (b.periodReturn ?? -Infinity) - (a.periodReturn ?? -Infinity));
    }
    const ordered = SLEEVE_ORDER.filter((k) => bySleeve.has(k)).map((k) => [k, bySleeve.get(k)!] as const);
    const extra = [...bySleeve.keys()].filter((k) => !SLEEVE_ORDER.includes(k));
    return [...ordered, ...extra.map((k) => [k, bySleeve.get(k)!] as const)];
  }, [filtered]);

  const movers = useMemo(() => {
    const withReturn = filtered.filter((s) => s.periodReturn != null);
    const gainers = [...withReturn].sort((a, b) => b.periodReturn! - a.periodReturn!).slice(0, 5);
    const losers = [...withReturn].sort((a, b) => a.periodReturn! - b.periodReturn!).slice(0, 5);
    return { gainers, losers };
  }, [filtered]);

  if (err) return <p className="text-error-500">{err}</p>;
  if (!stocks) return <p className="text-gray-500">Loading…</p>;

  const sleeveTabs = ["all", ...SLEEVE_ORDER.filter((k) => stocks.some((s) => s.sleeve === k))];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1">
          {sleeveTabs.map((k) => (
            <button
              key={k}
              onClick={() => setSleeve(k)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                sleeve === k
                  ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                  : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
              }`}
            >
              {k === "all" ? "All" : sleeveLabel(k)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {(Object.keys(PERIODS) as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  period === p
                    ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                    : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ticker or name…"
            className="w-48 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-800 outline-none focus:border-brand-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
          />
        </div>
      </div>

      {!search && (movers.gainers.length > 0 || movers.losers.length > 0) && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <h2 className="mb-3 text-sm font-semibold text-success-600">
              Top gainers · {sleeve === "all" ? "All" : sleeveLabel(sleeve)} · {period}
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
              {movers.gainers.map((s) => (
                <Card key={s.ticker} s={s} />
              ))}
            </div>
          </div>
          <div>
            <h2 className="mb-3 text-sm font-semibold text-error-500">
              Top losers · {sleeve === "all" ? "All" : sleeveLabel(sleeve)} · {period}
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
              {movers.losers.map((s) => (
                <Card key={s.ticker} s={s} />
              ))}
            </div>
          </div>
        </div>
      )}

      {groups.map(([sleeveKey, list]) => (
        <div key={sleeveKey}>
          <h2 className="mb-3 text-base font-semibold text-gray-800 dark:text-white/90">
            {sleeveLabel(sleeveKey)}{" "}
            <span className="font-normal text-gray-400">({list.length})</span>
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {list.map((s) => (
              <Card key={s.ticker} s={s} />
            ))}
          </div>
        </div>
      ))}

      {groups.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-400">No stocks match.</p>
      )}
    </div>
  );
}

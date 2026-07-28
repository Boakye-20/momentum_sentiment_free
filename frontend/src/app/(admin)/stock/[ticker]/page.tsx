"use client";
import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import RadarTag from "@/components/screener/RadarTag";
import PriceChart from "@/components/screener/PriceChart";
import {
  fetchStock, fetchPortfolio, fetchSignals, fmtPct, fmtNum, sleeveLabel,
  StockDetail, Position,
} from "@/lib/api";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-100 p-3 dark:border-gray-800">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-0.5 font-semibold text-gray-800 dark:text-white/90">{value}</p>
    </div>
  );
}

export default function StockPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const [d, setD] = useState<StockDetail | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [signalWeight, setSignalWeight] = useState<number | null>(null);
  const [signalChecked, setSignalChecked] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (ticker) fetchStock(ticker).then(setD).catch((e) => setErr(String(e)));
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    // Best-effort: if Trading212 isn't connected or the call fails, just
    // don't show the investment card — the rest of the page still works.
    fetchPortfolio()
      .then((r) => {
        const held = r.positions?.find(
          (p) => p.ticker.toUpperCase() === ticker.toUpperCase()
        );
        setPosition(held ?? null);
      })
      .catch(() => setPosition(null));
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    // Capital doesn't affect weight_pct, only alloc/shares, so any value works.
    fetchSignals(100_000)
      .then((r) => {
        const pick = r.positions.find((p) => p.ticker.toUpperCase() === ticker.toUpperCase());
        setSignalWeight(pick?.weight_pct ?? null);
      })
      .catch(() => setSignalWeight(null))
      .finally(() => setSignalChecked(true));
  }, [ticker]);

  if (err) return <p className="p-8 text-error-500">{err}</p>;
  if (!d) return <p className="p-8 text-gray-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/" className="text-sm text-gray-400 hover:text-brand-500">
          ← Browse
        </Link>
        <h1 className="text-2xl font-bold text-gray-800 dark:text-white/90">
          {d.ticker}
        </h1>
        {d.name && (
          <span className="text-lg text-gray-500 dark:text-gray-400">
            {d.name}
          </span>
        )}
        {d.under_radar ? <RadarTag /> : null}
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {String(d.sector)} · {sleeveLabel(String(d.sleeve))} · as of {d.as_of}
        </span>
      </div>

      <div className="grid grid-cols-12 gap-4 md:gap-6">
        <div className="col-span-12 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] xl:col-span-8">
          <div className="mb-2 flex items-baseline gap-3">
            <p className="text-2xl font-bold text-gray-800 dark:text-white/90">
              {fmtNum(d.last_price)}
            </p>
            <p
              className={`text-sm font-medium ${
                (d.mom_12m ?? 0) >= 0 ? "text-success-600" : "text-error-500"
              }`}
            >
              {fmtPct(d.mom_12m)} over 12m
            </p>
          </div>
          <PriceChart
            dates={d.prices.dates}
            values={d.prices.close}
            height={320}
            avgPrice={position?.average_price ?? undefined}
            buyDate={position?.opened_at ?? undefined}
          />
        </div>

        <div className="col-span-12 space-y-4 xl:col-span-4">
          {position && (
            <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03]">
              <p className="mb-3 text-sm font-medium text-gray-500 dark:text-gray-400">
                Your investment
              </p>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Value</span>
                  <span className="font-semibold text-gray-800 dark:text-white/90">
                    {position.market_value != null ? `£${position.market_value.toFixed(2)}` : "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Return</span>
                  <span
                    className={`font-semibold ${
                      (position.ppl ?? 0) >= 0 ? "text-success-600" : "text-error-500"
                    }`}
                  >
                    {position.ppl != null ? `£${position.ppl.toFixed(2)}` : "-"}
                    {position.ppl != null && position.average_price != null && position.quantity != null && (
                      <>
                        {" "}
                        (
                        {(
                          (position.ppl /
                            (position.average_price * position.quantity)) *
                          100
                        ).toFixed(2)}
                        %)
                      </>
                    )}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Shares</span>
                  <span className="font-semibold text-gray-800 dark:text-white/90">
                    {position.quantity ?? "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Average price</span>
                  <span className="font-semibold text-gray-800 dark:text-white/90">
                    {position.average_price?.toFixed(2) ?? "-"}
                  </span>
                </div>
              </div>
            </div>
          )}
          <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03]">
            <p className="mb-2 text-sm font-medium text-gray-500 dark:text-gray-400">
              Signal Book
            </p>
            {!signalChecked ? (
              <p className="text-sm text-gray-400">Checking…</p>
            ) : signalWeight != null ? (
              <p className="text-lg font-semibold text-success-600">
                Current pick · {signalWeight.toFixed(1)}%
              </p>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">Not currently picked</p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="RSI (14)" value={fmtNum(d.rsi as number, 1)} />
            <Stat label="52w ratio" value={fmtNum(d.ratio_52w as number)} />
            <Stat label="Volatility" value={fmtPct(d.volatility as number)} />
            <Stat label="Sentiment" value={fmtNum(d.sentiment_score as number)} />
            <Stat label="Fwd P/E" value={fmtNum(d.pe_forward as number, 1)} />
            <Stat label="ROE" value={fmtPct(d.roe as number)} />
            <Stat label="Gross margin" value={fmtPct(d.gross_margin as number)} />
            <Stat label="Debt/Equity" value={fmtNum(d.debt_equity as number, 1)} />
          </div>
        </div>
      </div>
      <p className="text-xs text-gray-400">Research tool, not investment advice.</p>
    </div>
  );
}

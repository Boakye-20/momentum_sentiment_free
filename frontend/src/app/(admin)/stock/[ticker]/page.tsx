"use client";
import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import type { ApexOptions } from "apexcharts";
import Badge from "@/components/ui/badge/Badge";
import ScoreBar from "@/components/screener/ScoreBar";
import RadarTag from "@/components/screener/RadarTag";
import { fetchStock, fmtPct, fmtNum, StockDetail } from "@/lib/api";

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

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
  const [err, setErr] = useState("");

  useEffect(() => {
    if (ticker) fetchStock(ticker).then(setD).catch((e) => setErr(String(e)));
  }, [ticker]);

  if (err) return <p className="p-8 text-error-500">{err}</p>;
  if (!d) return <p className="p-8 text-gray-500">Loading…</p>;

  const options: ApexOptions = {
    chart: { type: "area", fontFamily: "Inter, sans-serif", toolbar: { show: false } },
    colors: ["#465FFF"],
    stroke: { curve: "smooth", width: 2 },
    fill: { type: "gradient", gradient: { opacityFrom: 0.35, opacityTo: 0 } },
    dataLabels: { enabled: false },
    xaxis: {
      categories: d.prices.dates,
      tickAmount: 8,
      labels: { rotate: 0, style: { colors: "#98A2B3" } },
      axisTicks: { show: false },
    },
    yaxis: { labels: { style: { colors: "#98A2B3" } } },
    grid: { borderColor: "rgba(152,162,179,0.15)" },
    tooltip: { x: { show: true } },
  };

  const badgeColor =
    d.action === "BUY" ? "success" : d.action === "AVOID" ? "error" : "warning";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/" className="text-sm text-gray-400 hover:text-brand-500">
          ← Screener
        </Link>
        <h1 className="text-2xl font-bold text-gray-800 dark:text-white/90">
          {d.ticker}
        </h1>
        <Badge color={badgeColor}>{d.action}</Badge>
        {d.under_radar ? <RadarTag /> : null}
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {String(d.sector)} · {String(d.sleeve)} · as of {d.as_of}
        </span>
      </div>

      <div className="grid grid-cols-12 gap-4 md:gap-6">
        <div className="col-span-12 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] xl:col-span-8">
          <div className="mb-2 flex items-baseline gap-3">
            <p className="text-2xl font-bold text-gray-800 dark:text-white/90">
              {d.last_price.toFixed(2)}
            </p>
            <p
              className={`text-sm font-medium ${
                (d.mom_12m ?? 0) >= 0 ? "text-success-600" : "text-error-500"
              }`}
            >
              {fmtPct(d.mom_12m)} over 12m
            </p>
          </div>
          <ReactApexChart
            options={options}
            series={[{ name: d.ticker, data: d.prices.close }]}
            type="area"
            height={320}
          />
        </div>

        <div className="col-span-12 space-y-4 xl:col-span-4">
          <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03]">
            <p className="mb-2 text-sm font-medium text-gray-500 dark:text-gray-400">
              AI Score
            </p>
            <ScoreBar score={d.ai_score} />
            {d.confidence_pct != null && (
              <p className="mt-2 text-xs text-gray-400">
                Confidence: {String(d.confidence_pct)}% of layers had real data
              </p>
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

"use client";
import React, { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { ApexOptions } from "apexcharts";

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

const RANGES = ["1M", "6M", "YTD", "1Y", "5Y", "Max"] as const;
type Range = (typeof RANGES)[number];
const DAYS: Record<"1M" | "6M" | "1Y" | "5Y", number> = {
  "1M": 21,
  "6M": 126,
  "1Y": 252,
  "5Y": 1260,
};

/** Google-Finance-style price chart: green-when-up / red-when-down gradient
 *  area with a datetime axis and a 1M / 6M / YTD / 1Y / 5Y / Max timeframe
 *  toggle. Expects the full history from the API and slices client-side. */
export default function PriceChart({
  dates,
  values,
  height = 340,
  avgPrice,
  buyDate,
}: {
  dates: string[];
  values: number[];
  height?: number;
  /** Optional: draws a dashed horizontal reference line at this price
   *  (your average buy price), like Trading212's own position chart. */
  avgPrice?: number;
  /** Optional: draws a dashed vertical marker at this date (when the
   *  position was opened). Only visible on ranges that include the date. */
  buyDate?: string;
}) {
  const [range, setRange] = useState<Range>("1Y");

  const { series, up, hasData } = useMemo(() => {
    if (!dates.length) return { series: [], up: true, hasData: false };
    let start = 0;
    if (range === "Max") start = 0;
    else if (range === "YTD") {
      const yr = new Date(dates[dates.length - 1]).getFullYear();
      const i = dates.findIndex((d) => new Date(d).getFullYear() === yr);
      start = i < 0 ? 0 : i;
    } else {
      start = Math.max(0, dates.length - DAYS[range]);
    }
    const d = dates.slice(start);
    const v = values.slice(start);
    const pts = d.map((dd, i) => ({ x: new Date(dd).getTime(), y: v[i] }));
    const rising = v.length > 1 ? v[v.length - 1] >= v[0] : true;
    return { series: pts, up: rising, hasData: pts.length > 1 };
  }, [dates, values, range]);

  const color = up ? "#22C55E" : "#EF4444";

  const yaxisAnnotations =
    avgPrice != null
      ? [
          {
            y: avgPrice,
            borderColor: "#98A2B3",
            strokeDashArray: 4,
            label: {
              text: `Your avg $${avgPrice.toFixed(2)}`,
              position: "left",
              style: { color: "#fff", background: "#98A2B3", fontSize: "11px" },
            },
          },
        ]
      : [];

  // Price bars are anchored to midnight UTC of each date, but a same-day
  // buy timestamp includes intraday time (e.g. "...T16:33:18+03:00"),
  // which can land AFTER the last bar's midnight timestamp and fail an
  // exact-time range check. Compare calendar dates only, then snap the
  // marker to the nearest bar so it lines up with the actual chart data.
  const buyDateOnly = buyDate
    ? new Date(new Date(buyDate).toDateString()).getTime()
    : null;
  const inRange =
    buyDateOnly != null && series.length > 0 &&
    buyDateOnly >= new Date(new Date(series[0].x).toDateString()).getTime() &&
    buyDateOnly <= new Date(new Date(series[series.length - 1].x).toDateString()).getTime();
  const buyTs = inRange
    ? series.reduce((closest, pt) =>
        Math.abs(pt.x - buyDateOnly!) < Math.abs(closest - buyDateOnly!) ? pt.x : closest,
        series[0].x)
    : null;
  // Anchor the label inward when the marker sits near either edge, so
  // "Bought" doesn't get clipped off the side of the chart (it lands at
  // the very last bar often, since most buys are recent).
  const rangeStart = series.length ? series[0].x : 0;
  const rangeEnd = series.length ? series[series.length - 1].x : 1;
  const pct = buyTs != null ? (buyTs - rangeStart) / (rangeEnd - rangeStart || 1) : 0.5;
  const textAnchor: "start" | "middle" | "end" =
    pct > 0.85 ? "end" : pct < 0.15 ? "start" : "middle";

  const xaxisAnnotations =
    inRange && buyTs != null
      ? [
          {
            x: buyTs,
            borderColor: "#775DD0",
            strokeDashArray: 4,
            label: {
              text: "Bought",
              orientation: "horizontal" as const,
              textAnchor,
              style: { color: "#fff", background: "#775DD0", fontSize: "11px" },
            },
          },
        ]
      : [];

  const options: ApexOptions = {
    chart: {
      type: "area",
      fontFamily: "Inter, sans-serif",
      toolbar: { show: false },
      animations: { enabled: false },
    },
    colors: [color],
    stroke: { curve: "straight", width: 1.8 },
    fill: {
      type: "gradient",
      gradient: { opacityFrom: 0.3, opacityTo: 0, stops: [0, 100] },
    },
    dataLabels: { enabled: false },
    xaxis: {
      type: "datetime",
      tickAmount: 6,
      labels: { datetimeUTC: false, style: { colors: "#98A2B3" } },
      axisTicks: { show: false },
      axisBorder: { show: false },
    },
    yaxis: {
      labels: {
        style: { colors: "#98A2B3" },
        formatter: (v: number) => v.toFixed(0),
      },
    },
    grid: { borderColor: "rgba(152,162,179,0.12)" },
    tooltip: {
      x: { format: "dd MMM yyyy" },
      y: { formatter: (v: number) => v.toFixed(2) },
    },
    annotations: { yaxis: yaxisAnnotations, xaxis: xaxisAnnotations },
  };

  return (
    <div>
      <div className="mb-3 flex gap-1">
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
              range === r
                ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
            }`}
          >
            {r}
          </button>
        ))}
      </div>
      {hasData ? (
        <ReactApexChart
          options={options}
          series={[{ name: "Price", data: series }]}
          type="area"
          height={height}
        />
      ) : (
        <p className="py-16 text-center text-sm text-gray-400">
          Not enough history for this range.
        </p>
      )}
    </div>
  );
}

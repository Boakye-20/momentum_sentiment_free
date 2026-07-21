"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { ApexOptions } from "apexcharts";
import { fetchBacktest, BacktestResponse } from "@/lib/api";
import DurationExplorer from "@/components/backtest/DurationExplorer";

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

function Stat({ label, value, good }: { label: string; value: string; good?: boolean | null }) {
  const color =
    good == null
      ? "text-gray-900 dark:text-white/90"
      : good
      ? "text-success-600"
      : "text-error-500";
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-white/[0.03]">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className={`mt-1 text-xl font-semibold tracking-tight ${color}`}>{value}</p>
    </div>
  );
}

export default function BacktestPage() {
  const [sentiment, setSentiment] = useState(false);
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [polling, setPolling] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback((withSentiment: boolean) => {
    if (timer.current) clearInterval(timer.current);
    setData(null);
    setPolling(true);
    const tick = async () => {
      try {
        const r = await fetchBacktest(withSentiment);
        if (r.status !== "running") {
          setData(r);
          setPolling(false);
          if (timer.current) clearInterval(timer.current);
        }
      } catch {
        setData({ status: "error", message: "API not reachable. Start it with: uvicorn api.server:app --port 8000" });
        setPolling(false);
        if (timer.current) clearInterval(timer.current);
      }
    };
    tick();
    timer.current = setInterval(tick, 4000);
  }, []);

  useEffect(() => {
    poll(sentiment);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [sentiment, poll]);

  const m = data?.metrics;
  const eq = data?.equity;
  // Datetime series so the x-axis always spans the real date range and the
  // right edge lands on the most recent date (a category axis with even ticks
  // left the last label at ~2025-09 even though data ran to 2026-07).
  const dates = eq?.dates ?? [];
  const toSeries = (vals: number[] = []) =>
    dates.map((d, i) => ({ x: new Date(d).getTime(), y: vals[i] }));
  const firstTs = dates.length ? new Date(dates[0]).getTime() : undefined;
  const lastTs = dates.length ? new Date(dates[dates.length - 1]).getTime() : undefined;

  const stratUp = (eq?.strategy?.length ?? 0) > 1
    && eq!.strategy[eq!.strategy.length - 1] >= eq!.strategy[0];
  const chartOptions: ApexOptions = {
    chart: { type: "area", fontFamily: "Inter, sans-serif", toolbar: { show: false }, animations: { enabled: false } },
    colors: [stratUp ? "#22C55E" : "#EF4444", "#98A2B3"],
    stroke: { curve: "straight", width: [2, 1.5], dashArray: [0, 4] },
    fill: { type: ["gradient", "solid"], opacity: [1, 0], gradient: { opacityFrom: 0.28, opacityTo: 0, stops: [0, 100] } },
    dataLabels: { enabled: false },
    xaxis: {
      type: "datetime",
      min: firstTs,
      max: lastTs,
      tickAmount: 8,
      labels: {
        rotate: 0,
        datetimeUTC: false,
        format: "MMM yyyy",
        style: { colors: "#98A2B3" },
      },
      axisTicks: { show: false },
    },
    yaxis: {
      labels: {
        style: { colors: "#98A2B3" },
        formatter: (v: number) => `${Math.round(v / 1000)}k`,
      },
    },
    grid: { borderColor: "rgba(152,162,179,0.15)" },
    legend: { labels: { colors: "#98A2B3" } },
    tooltip: {
      x: { format: "dd MMM yyyy" },
      y: { formatter: (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }) },
    },
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
            Backtest
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Monthly rebalance, up to 15 positions by momentum, T+1 execution, 0.1% costs, marked to market daily
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
          <input
            type="checkbox"
            checked={sentiment}
            onChange={(e) => setSentiment(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300"
          />
          Include sentiment overlay
        </label>
      </div>

      {polling && (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-800 dark:bg-white/[0.03]">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Running the backtest on the full universe. This takes up to a minute
            the first time; results are then cached for an hour.
          </p>
        </div>
      )}

      {data?.status === "error" && (
        <div className="rounded-xl border border-warning-500/40 bg-warning-50 p-5 text-sm text-gray-700 dark:bg-warning-500/10 dark:text-gray-200">
          Backtest failed: {data.message}
        </div>
      )}

      {data?.status === "done" && m && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat
              label="CAGR vs benchmark"
              value={`${m.cagr_pct}% vs ${m.benchmark_cagr_pct}%`}
              good={m.cagr_pct >= m.benchmark_cagr_pct}
            />
            <Stat label="Sharpe ratio" value={String(m.sharpe)} good={m.sharpe >= 0.7 ? true : null} />
            <Stat label="Max drawdown" value={`${m.max_drawdown_pct}%`} good={false} />
            <Stat
              label="Win rate"
              value={`${m.win_rate_pct}% of ${m.n_trades} trades`}
              good={null}
            />
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03]">
            <h2 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white/90">
              Growth of {`£`}100,000 (strategy vs SPY) · data through {data.as_of}
            </h2>
            <ReactApexChart
              options={chartOptions}
              series={[
                { name: "Strategy", data: toSeries(eq?.strategy) },
                { name: "SPY benchmark", data: toSeries(eq?.benchmark) },
              ]}
              type="area"
              height={340}
            />
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Annual volatility" value={`${m.ann_vol_pct}%`} good={null} />
            <Stat label="Sortino" value={String(m.sortino)} good={null} />
            <Stat label="Beta vs SPY" value={String(m.beta)} good={null} />
            <Stat label="Avg hold" value={`${m.avg_hold_days} days`} good={null} />
          </div>

          {data.walk_forward && data.walk_forward.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
              <div className="border-b border-gray-100 p-4 dark:border-gray-800">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white/90">
                  Walk-forward check
                </h2>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  Purged cross-validation: the history is split into equal folds,
                  each scored out-of-sample with an embargo around its boundary.
                  If out-of-sample CAGR holds up across folds, the strategy is not
                  just fitted to one era.
                </p>
              </div>
              <div className="max-w-full overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-xs uppercase text-gray-500 dark:border-gray-800 dark:text-gray-400">
                      <th className="px-5 py-3">Window</th>
                      <th className="px-5 py-3">In-sample CAGR</th>
                      <th className="px-5 py-3">Out-of-sample CAGR</th>
                      <th className="px-5 py-3">Benchmark (same period)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.walk_forward.map((f) => (
                      <tr key={f.window} className="border-b border-gray-50 dark:border-gray-800/60">
                        <td className="px-5 py-3 text-gray-600 dark:text-gray-300">{f.window}</td>
                        <td className="px-5 py-3">{f.in_cagr}%</td>
                        <td
                          className={`px-5 py-3 font-medium ${
                            f.out_cagr >= f.out_bench ? "text-success-600" : "text-error-500"
                          }`}
                        >
                          {f.out_cagr}%
                        </td>
                        <td className="px-5 py-3 text-gray-500 dark:text-gray-400">{f.out_bench}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {data.duration && (
            <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
              <div className="border-b border-gray-100 p-4 dark:border-gray-800">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white/90">
                  Trade duration analytics
                </h2>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  How time affects this strategy: when trades win, how fast they
                  peak, and how long the portfolio stays underwater.
                </p>
              </div>

              <DurationExplorer pairs={data.duration.hold_returns} />

              <div className="grid grid-cols-2 gap-4 border-t border-gray-100 p-4 dark:border-gray-800 md:grid-cols-4">
                <Stat
                  label="Winners peak at"
                  value={`${data.duration.time_to_peak.avg_days_to_peak} days`}
                  good={null}
                />
                <Stat
                  label="But held for"
                  value={`${data.duration.time_to_peak.avg_hold_days_winners} days`}
                  good={null}
                />
                <Stat
                  label="Best unrealised gain"
                  value={`${data.duration.time_to_peak.avg_mfe_pct}%`}
                  good={null}
                />
                <Stat
                  label="Longest recovery"
                  value={`${data.duration.drawdown_duration.longest_recovery_days} days`}
                  good={null}
                />
              </div>
              <p className="px-4 pb-4 text-xs text-gray-500 dark:text-gray-400">
                Winners reach their best profit around day{" "}
                {data.duration.time_to_peak.avg_days_to_peak} but are held about{" "}
                {data.duration.time_to_peak.avg_hold_days_winners} days, so some gain
                decays before exit. The worst the whole portfolio ever stayed below a
                previous high was{" "}
                {data.duration.drawdown_duration.longest_recovery_days} days (about{" "}
                {Math.round(data.duration.drawdown_duration.longest_recovery_days / 30)}{" "}
                months), across {data.duration.drawdown_duration.n_drawdowns} dips
                averaging {data.duration.drawdown_duration.avg_recovery_days} days each.
                {data.duration.drawdown_duration.currently_underwater_days > 0
                  ? ` Currently ${data.duration.drawdown_duration.currently_underwater_days} days below the last peak.`
                  : " Currently at or near a fresh high."}
              </p>
            </div>
          )}

          {data.trades && data.trades.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
              <div className="border-b border-gray-100 p-4 dark:border-gray-800">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white/90">
                  Most recent trades
                </h2>
              </div>
              <div className="max-h-96 max-w-full overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-white dark:bg-gray-900">
                    <tr className="border-b border-gray-100 text-xs uppercase text-gray-500 dark:border-gray-800 dark:text-gray-400">
                      <th className="px-5 py-3">Ticker</th>
                      <th className="px-5 py-3">Entry</th>
                      <th className="px-5 py-3">Exit</th>
                      <th className="px-5 py-3">Return</th>
                      <th className="px-5 py-3">Held</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.trades].reverse().map((t, i) => (
                      <tr key={`${t.ticker}-${t.entry_date}-${i}`} className="border-b border-gray-50 dark:border-gray-800/60">
                        <td className="px-5 py-3 font-semibold text-gray-800 dark:text-white/90">
                          {t.ticker}
                        </td>
                        <td className="px-5 py-3 text-gray-600 dark:text-gray-300">
                          {t.entry_date} at {t.entry_price}
                        </td>
                        <td className="px-5 py-3 text-gray-600 dark:text-gray-300">
                          {t.exit_date} at {t.exit_price}
                        </td>
                        <td
                          className={`px-5 py-3 font-medium ${
                            t.return_pct >= 0 ? "text-success-600" : "text-error-500"
                          }`}
                        >
                          {t.return_pct}%
                        </td>
                        <td className="px-5 py-3 text-gray-500 dark:text-gray-400">
                          {t.hold_days}d
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <p className="text-xs text-gray-400">
            Past performance from a hand-picked universe carries survivorship
            bias. Research tool, not investment advice.
          </p>
        </>
      )}
    </div>
  );
}

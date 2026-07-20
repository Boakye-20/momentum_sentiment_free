"use client";
import React, { useEffect, useMemo, useState } from "react";

/** Interactive holding-window explorer. Slide the From/To handles (or use a
 *  preset) over the distribution of trades and the win rate + average return
 *  recompute live for exactly that window. */
export default function DurationExplorer({ pairs = [] }: { pairs?: [number, number][] }) {
  const maxHold = useMemo(
    () => pairs.reduce((m, [h]) => Math.max(m, h), 0),
    [pairs]
  );
  const [lo, setLo] = useState(0);
  const [hi, setHi] = useState(30);

  useEffect(() => {
    setLo(0);
    setHi(Math.min(30, maxHold));
  }, [maxHold]);

  if (pairs.length === 0) {
    return (
      <p className="p-4 text-sm text-gray-500 dark:text-gray-400">
        Trade duration data is not available. If you just updated the app,
        restart the API server (uvicorn api.server:app --port 8000) so it sends
        the latest backtest fields.
      </p>
    );
  }

  const inWindow = pairs.filter(([h]) => h >= lo && h <= hi);
  const n = inWindow.length;
  const winRate = n ? (inWindow.filter(([, r]) => r > 0).length / n) * 100 : 0;
  const avgRet = n ? inWindow.reduce((s, [, r]) => s + r, 0) / n : 0;

  // 10-day histogram bins for the distribution graph.
  const binSize = 10;
  const nBins = Math.max(1, Math.ceil((maxHold + 1) / binSize));
  const bins = Array.from({ length: nBins }, (_, i) => {
    const bl = i * binSize;
    const bh = bl + binSize - 1;
    const count = pairs.filter(([h]) => h >= bl && h <= bh).length;
    return { bl, bh, count, active: bh >= lo && bl <= hi };
  });
  const maxCount = Math.max(...bins.map((b) => b.count), 1);

  const presets: [string, number, number][] = [
    ["~1 week", 0, 7],
    ["~1 month", 0, 30],
    ["1-2 months", 31, 60],
    ["2 months+", 61, maxHold],
    ["All", 0, maxHold],
  ];

  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Explore a holding window
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {presets.map(([label, a, b]) => {
            const on = lo === a && hi === b;
            return (
              <button
                key={label}
                onClick={() => {
                  setLo(a);
                  setHi(b);
                }}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  on
                    ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                    : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Distribution graph: bars in the selected window are highlighted. */}
      <div className="flex h-28 items-end gap-1">
        {bins.map((b) => (
          <div
            key={b.bl}
            title={`${b.bl}-${b.bh} days: ${b.count} trades`}
            className="flex-1 rounded-t transition-colors"
            style={{
              height: `${Math.max(3, (b.count / maxCount) * 100)}%`,
              backgroundColor: b.active ? "#465FFF" : "#E5E7EB",
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-400">
        <span>0 days</span>
        <span>{maxHold} days</span>
      </div>

      {/* From / To sliders */}
      <div className="mt-4 space-y-3">
        <div>
          <div className="mb-1 flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>From</span>
            <span className="font-medium text-gray-800 dark:text-white/90">{lo} days</span>
          </div>
          <input
            type="range"
            min={0}
            max={maxHold}
            value={lo}
            onChange={(e) => setLo(Math.min(Number(e.target.value), hi))}
            className="w-full accent-brand-500"
          />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>To</span>
            <span className="font-medium text-gray-800 dark:text-white/90">{hi} days</span>
          </div>
          <input
            type="range"
            min={0}
            max={maxHold}
            value={hi}
            onChange={(e) => setHi(Math.max(Number(e.target.value), lo))}
            className="w-full accent-brand-500"
          />
        </div>
      </div>

      {/* Live stats for the selected window */}
      <div className="mt-4 grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-gray-200 p-3 text-center dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">Trades</p>
          <p className="mt-0.5 text-lg font-semibold text-gray-900 dark:text-white/90">{n}</p>
        </div>
        <div className="rounded-lg border border-gray-200 p-3 text-center dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">Win rate</p>
          <p className="mt-0.5 text-lg font-semibold text-gray-900 dark:text-white/90">
            {n ? `${winRate.toFixed(1)}%` : "-"}
          </p>
        </div>
        <div className="rounded-lg border border-gray-200 p-3 text-center dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">Avg return</p>
          <p
            className={`mt-0.5 text-lg font-semibold ${
              avgRet >= 0 ? "text-success-600" : "text-error-500"
            }`}
          >
            {n ? `${avgRet.toFixed(2)}%` : "-"}
          </p>
        </div>
      </div>
      <p className="mt-2 text-xs text-gray-400">
        Showing trades held between {lo} and {hi} days. Win rate is how often those
        trades made money; average return is the mean profit or loss per trade.
      </p>
    </div>
  );
}

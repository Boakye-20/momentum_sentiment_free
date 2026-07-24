"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSignals, sleeveLabel, SignalsResponse } from "@/lib/api";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-white/[0.03]">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
        {value}
      </p>
    </div>
  );
}

export default function SignalsPage() {
  const [capitalInput, setCapitalInput] = useState("50000");
  const [capital, setCapital] = useState(50000);
  const [data, setData] = useState<SignalsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    setLoading(true);
    setErr("");
    fetchSignals(capital)
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [capital]);

  const applyCapital = () => {
    const v = parseFloat(capitalInput);
    if (!isNaN(v) && v > 0) setCapital(v);
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800 dark:text-white/90">
            Signal Book
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Names passing today&apos;s entry filter, inverse-vol weighted, sized to your capital
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Capital (£)
            </label>
            <input
              type="number"
              value={capitalInput}
              onChange={(e) => setCapitalInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyCapital()}
              className="w-36 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none focus:border-brand-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
            />
          </div>
          <button
            onClick={applyCapital}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
          >
            Recalculate
          </button>
        </div>
      </div>

      {err && (
        <p className="text-error-500">
          {err}. Is the API running?{" "}
          <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-white/10">
            uvicorn api.server:app --port 8000
          </code>
        </p>
      )}
      {loading && !data && !err && <p className="text-gray-500">Loading…</p>}

      {data && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Positions" value={String(data.count)} />
            <Stat label="Gross long" value={`${data.gross_long_pct.toFixed(1)}%`} />
            <Stat label="Capital" value={`£${data.capital.toLocaleString()}`} />
            <Stat label="As of" value={data.as_of} />
          </div>

          {data.positions.length === 0 ? (
            <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center text-gray-500 dark:border-gray-800 dark:bg-white/[0.03]">
              No names pass the entry filter today.
            </div>
          ) : (
            <div className="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
              <div className="max-w-full overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-xs uppercase text-gray-500 dark:border-gray-800 dark:text-gray-400">
                      <th className="px-5 py-3">Ticker</th>
                      <th className="px-5 py-3">Sector</th>
                      <th className="px-5 py-3">Sleeve</th>
                      <th className="px-5 py-3">Weight</th>
                      <th className="px-5 py-3">Price</th>
                      <th className="px-5 py-3">Suggested alloc</th>
                      <th className="px-5 py-3">Shares</th>
                      <th className="px-5 py-3">12m mom</th>
                      <th className="px-5 py-3">RSI</th>
                      <th className="px-5 py-3">Sentiment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.positions.map((p) => (
                      <tr
                        key={p.ticker}
                        className="border-b border-gray-50 hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-white/[0.02]"
                      >
                        <td className="px-5 py-3 font-semibold text-gray-800 dark:text-white/90">
                          <Link href={`/stock/${p.ticker}`} className="hover:text-brand-500">
                            {p.ticker}
                          </Link>
                          {p.name && (
                            <div className="text-xs font-normal text-gray-400">{p.name}</div>
                          )}
                        </td>
                        <td className="px-5 py-3 text-gray-600 dark:text-gray-300">{p.sector}</td>
                        <td className="px-5 py-3 text-gray-600 dark:text-gray-300">
                          {sleeveLabel(p.sleeve)}
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-2 min-w-[90px]">
                            <span className="w-10 font-medium text-gray-800 dark:text-white/90">
                              {p.weight_pct.toFixed(1)}%
                            </span>
                            <div className="h-2 flex-1 rounded-full bg-gray-100 dark:bg-white/10">
                              <div
                                className="h-2 rounded-full bg-brand-500"
                                style={{ width: `${Math.min(100, p.weight_pct * 5)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3">{p.last_price.toFixed(2)}</td>
                        <td className="px-5 py-3 font-medium text-gray-800 dark:text-white/90">
                          £{p.alloc_gbp.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </td>
                        <td className="px-5 py-3">{p.suggested_shares}</td>
                        <td
                          className={`px-5 py-3 ${
                            (p.mom_12m ?? 0) >= 0 ? "text-success-600" : "text-error-500"
                          }`}
                        >
                          {p.mom_12m != null ? `${(p.mom_12m * 100).toFixed(1)}%` : "-"}
                        </td>
                        <td className="px-5 py-3">{p.rsi?.toFixed(0) ?? "-"}</td>
                        <td className="px-5 py-3">{p.sentiment_score?.toFixed(2) ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="px-5 py-3 text-xs text-gray-400">
                Every price here is in USD (this app has no FX conversion), including
                foreign names like GSK or ASML held via their US-listed ADR, not their
                LSE/Euronext listing. &quot;Suggested shares&quot; divides your £ allocation by
                that $ price without converting, so treat it as illustrative only, not a
                literal share count. Enter the £ allocation directly as a value-based order
                in T212 instead (like the Citigroup trade) and let T212 handle the FX
                conversion. Not a live quote, and not investment advice. Weights come from
                the same inverse-vol sizing used in the backtest (max 15 positions, capped
                at 2x equal weight per name).
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

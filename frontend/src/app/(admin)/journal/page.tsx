"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import Badge from "@/components/ui/badge/Badge";
import { fetchJournal, JournalResponse } from "@/lib/api";

function SignalCell({ weight }: { weight: number | null }) {
  if (weight == null) {
    return <span className="text-xs text-gray-400">not picked</span>;
  }
  return (
    <Badge size="sm" color="success">
      {weight.toFixed(1)}%
    </Badge>
  );
}

export default function JournalPage() {
  const [data, setData] = useState<JournalResponse | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetchJournal().then(setData).catch((e) => setErr(String(e)));
  }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-800 dark:text-white/90">
          Trade Journal
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Your actual filled Trading212 orders, checked against the Signal Book
        </p>
      </div>

      {err && <p className="text-error-500">{err}</p>}
      {!data && !err && <p className="text-gray-500">Loading…</p>}

      {data && !data.connected && (
        <div className="rounded-2xl border border-gray-200 bg-white p-8 dark:border-gray-800 dark:bg-white/[0.03]">
          <h2 className="mb-2 font-semibold text-gray-800 dark:text-white/90">
            Connect Trading212
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">{data.message}</p>
        </div>
      )}

      {data?.connected && (
        <>
          {data.env === "live" && (
            <div className="mb-4 rounded-xl border border-warning-200 bg-warning-50 px-4 py-3 text-sm text-warning-700 dark:border-warning-500/30 dark:bg-warning-500/10 dark:text-warning-400">
              Showing your <strong>live</strong> account&apos;s order history (T212_ENV=live in .env).
            </div>
          )}
          {data.trades && data.trades.length === 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center text-gray-500 dark:border-gray-800 dark:bg-white/[0.03]">
              No filled orders yet on this account ({data.env}). Place a trade in the
              Trading212 app and it will show up here.
            </div>
          )}
          {data.trades && data.trades.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
              <div className="max-w-full overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-xs uppercase text-gray-500 dark:border-gray-800 dark:text-gray-400">
                      <th className="px-5 py-3">Date</th>
                      <th className="px-5 py-3">Ticker</th>
                      <th className="px-5 py-3">Side</th>
                      <th className="px-5 py-3">Qty</th>
                      <th className="px-5 py-3">Fill price</th>
                      <th className="px-5 py-3">Value</th>
                      <th className="px-5 py-3">Source</th>
                      <th className="px-5 py-3">Signal @ trade</th>
                      <th className="px-5 py-3">Signal now</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades.map((t, i) => (
                      <tr
                        key={t.id ?? i}
                        className="border-b border-gray-50 hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-white/[0.02]"
                      >
                        <td className="px-5 py-3 text-gray-600 dark:text-gray-300">
                          {t.date ? new Date(t.date).toLocaleString() : "-"}
                        </td>
                        <td className="px-5 py-3 font-semibold text-gray-800 dark:text-white/90">
                          {t.in_universe ? (
                            <Link href={`/stock/${t.ticker}`} className="hover:text-brand-500">
                              {t.ticker}
                            </Link>
                          ) : (
                            t.ticker
                          )}
                        </td>
                        <td className="px-5 py-3">
                          <Badge size="sm" color={t.side === "BUY" ? "success" : "error"}>
                            {t.side}
                          </Badge>
                        </td>
                        <td className="px-5 py-3">{t.quantity ?? "-"}</td>
                        <td className="px-5 py-3">{t.fill_price?.toFixed(2) ?? "-"}</td>
                        <td className="px-5 py-3">{t.fill_value?.toFixed(2) ?? "-"}</td>
                        <td className="px-5 py-3">
                          <Badge size="sm" color={t.is_bot ? "primary" : "light"}>
                            {t.is_bot ? "Bot" : "Manual"}
                          </Badge>
                        </td>
                        <td className="px-5 py-3">
                          <SignalCell weight={t.signal_weight_at_trade} />
                        </td>
                        <td className="px-5 py-3">
                          <SignalCell weight={t.signal_weight_now} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="px-5 py-3 text-xs text-gray-400">
                Read-only via Trading212 Public API · &quot;Signal&quot; is the same entry-filter
                + inverse-vol weighting shown on the Signals page and used by the backtest.
                A weight means the ticker was a Signal Book pick on that date, &quot;not
                picked&quot; means it wasn&apos;t · not investment advice
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

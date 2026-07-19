"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import Badge from "@/components/ui/badge/Badge";
import ScoreBar from "@/components/screener/ScoreBar";
import { fetchPortfolio, PortfolioResponse } from "@/lib/api";

export default function PortfolioPage() {
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetchPortfolio().then(setData).catch((e) => setErr(String(e)));
  }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-800 dark:text-white/90">
          My Portfolio
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Trading212 holdings, cross-checked against your AI Scores
        </p>
      </div>

      {err && <p className="text-error-500">{err}</p>}
      {!data && !err && <p className="text-gray-500">Loading…</p>}

      {data && !data.connected && (
        <div className="rounded-2xl border border-gray-200 bg-white p-8 dark:border-gray-800 dark:bg-white/[0.03]">
          <h2 className="mb-2 font-semibold text-gray-800 dark:text-white/90">
            Connect Trading212
          </h2>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-600 dark:text-gray-300">
            <li>
              In the Trading212 app: Settings → API (Beta) → generate a key
              pair (key ID + secret).
            </li>
            <li>
              Tick only the read scopes (account data, history, portfolio).
              Never grant order permissions.
            </li>
            <li>
              Open the <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-white/10">.env</code>{" "}
              file in the project folder and fill in{" "}
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-white/10">T212_API_KEY</code>{" "}
              and{" "}
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-white/10">T212_API_SECRET</code>
              .
            </li>
            <li>
              Restart the API:{" "}
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-white/10">
                uvicorn api.server:app --port 8000
              </code>
            </li>
          </ol>
        </div>
      )}

      {data?.connected && data.positions && (
        <div className="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
          <div className="max-w-full overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs uppercase text-gray-500 dark:border-gray-800 dark:text-gray-400">
                  <th className="px-5 py-3">Ticker</th>
                  <th className="px-5 py-3">Qty</th>
                  <th className="px-5 py-3">Avg price</th>
                  <th className="px-5 py-3">Current</th>
                  <th className="px-5 py-3">P/L</th>
                  <th className="px-5 py-3">AI Score</th>
                  <th className="px-5 py-3">Model view</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((p) => (
                  <tr
                    key={p.t212_ticker}
                    className="border-b border-gray-50 hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-white/[0.02]"
                  >
                    <td className="px-5 py-3 font-semibold text-gray-800 dark:text-white/90">
                      {p.in_universe ? (
                        <Link href={`/stock/${p.ticker}`} className="hover:text-brand-500">
                          {p.ticker}
                        </Link>
                      ) : (
                        p.ticker
                      )}
                    </td>
                    <td className="px-5 py-3">{p.quantity ?? "-"}</td>
                    <td className="px-5 py-3">{p.average_price?.toFixed(2) ?? "-"}</td>
                    <td className="px-5 py-3">{p.current_price?.toFixed(2) ?? "-"}</td>
                    <td
                      className={`px-5 py-3 font-medium ${
                        (p.ppl ?? 0) >= 0 ? "text-success-600" : "text-error-500"
                      }`}
                    >
                      {p.ppl?.toFixed(2) ?? "-"}
                    </td>
                    <td className="px-5 py-3">
                      <ScoreBar score={p.ai_score} />
                    </td>
                    <td className="px-5 py-3">
                      {p.action ? (
                        <Badge
                          size="sm"
                          color={
                            p.action === "BUY"
                              ? "success"
                              : p.action === "AVOID"
                              ? "error"
                              : "warning"
                          }
                        >
                          {p.action}
                        </Badge>
                      ) : (
                        <span className="text-xs text-gray-400">not in universe</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-5 py-3 text-xs text-gray-400">
            Read-only via Trading212 Public API · not investment advice
          </p>
        </div>
      )}
    </div>
  );
}

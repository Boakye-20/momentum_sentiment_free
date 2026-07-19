import React from "react";

/** AI Score (0-10) rendered as a Danelfin-style pill + bar. */
export default function ScoreBar({ score }: { score: number | null }) {
  if (score == null) return <span className="text-gray-400">-</span>;
  const pct = Math.max(0, Math.min(100, score * 10));
  const color =
    score >= 7 ? "bg-success-500" : score >= 4.5 ? "bg-warning-500" : "bg-error-500";
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <span className="w-8 text-sm font-semibold text-gray-800 dark:text-white/90">
        {score.toFixed(1)}
      </span>
      <div className="h-2 flex-1 rounded-full bg-gray-100 dark:bg-white/10">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

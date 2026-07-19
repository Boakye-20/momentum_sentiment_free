import type { Metadata } from "next";
import React from "react";
import ScreenerDashboard from "@/components/screener/ScreenerDashboard";

export const metadata: Metadata = {
  title: "AI Stock Screener",
  description: "Momentum, sentiment and fundamentals screener with composite AI Scores (1-10)",
};

export default function ScreenerPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
          Screener
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Ranked by composite AI Score: technicals, news sentiment and fundamentals
        </p>
      </div>
      <ScreenerDashboard />
    </div>
  );
}

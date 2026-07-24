import type { Metadata } from "next";
import React from "react";
import BrowseUniverse from "@/components/screener/BrowseUniverse";

export const metadata: Metadata = {
  title: "Browse",
  description: "Browse the universe of stocks you don't currently hold, grouped by sleeve",
};

export default function BrowsePage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-white/90">
          Browse
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Stocks you don&apos;t currently hold, grouped by sleeve. Click through for the full chart.
        </p>
      </div>
      <BrowseUniverse />
    </div>
  );
}

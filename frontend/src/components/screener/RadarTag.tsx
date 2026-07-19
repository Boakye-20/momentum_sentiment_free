import React from "react";

/** Subtle tag for the "under the radar" setup: strong fundamentals,
 *  cheap valuation, quiet news. Replaces the old emoji marker. */
export default function RadarTag() {
  return (
    <span
      title="Under the radar: strong fundamentals, cheap valuation, quiet news"
      className="inline-flex items-center rounded border border-gray-300 px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:border-gray-600 dark:text-gray-400"
    >
      Radar
    </span>
  );
}

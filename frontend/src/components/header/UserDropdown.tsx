"use client";
import Link from "next/link";
import React from "react";

/** Simple identity chip - no accounts in this app, so no dropdown menu. */
export default function UserDropdown() {
  return (
    <Link
      href="/profile"
      className="flex items-center gap-3 text-gray-700 dark:text-gray-400"
      title="Data & Model status"
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-500/10 font-semibold text-brand-500">
        P
      </span>
      <span className="hidden font-medium text-theme-sm sm:block">Paul</span>
    </Link>
  );
}

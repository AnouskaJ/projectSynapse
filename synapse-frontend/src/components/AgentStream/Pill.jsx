import React from "react";

export default function Pill({ children, tone = "neutral" }) {
  const cls =
    tone === "ok"
      ? "bg-emerald-900/40 text-emerald-300 border-emerald-800"
      : tone === "warn"
      ? "bg-amber-900/40 text-amber-300 border-amber-800"
      : tone === "err"
      ? "bg-rose-900/40 text-rose-300 border-rose-800"
      : "bg-slate-800/60 text-slate-300 border-slate-700";

  return <span className={`pill border ${cls}`}>{children}</span>;
}

"use client";

import { useEffect, useState } from "react";

function left(to: string, now: number) {
  const ms = new Date(to).getTime() - now;
  if (ms <= 0) return "passed";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

/** Live time left to the target submit time and the hard deadline. */
export function Countdown({ target, deadline }: { target: string; deadline: string }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) + " IST";
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="font-mono text-xs uppercase tracking-widest text-muted">Target submit (6 h early)</p>
        <p className="mt-1 text-3xl font-bold tabular-nums">{now === null ? "…" : left(target, now)}</p>
        <p className="text-sm text-muted">{fmt(target)}</p>
      </div>
      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="font-mono text-xs uppercase tracking-widest text-muted">Hard deadline</p>
        <p className="mt-1 text-3xl font-bold tabular-nums">{now === null ? "…" : left(deadline, now)}</p>
        <p className="text-sm text-muted">{fmt(deadline)}</p>
      </div>
    </div>
  );
}

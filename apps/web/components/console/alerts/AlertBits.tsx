import { bandLabel, pct, type Band, type FactorRow } from "@/lib/alerts";

/** Circular score gauge (score is computed by the pipeline in code; F2). */
export function ScoreRing({ score, band, size = 64 }: { score: number; band: Band; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const colour = band === "high" ? "var(--signal)" : "var(--accent)";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={6} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={colour} strokeWidth={6} strokeLinecap="round"
          strokeDasharray={`${c * score} ${c}`}
        />
      </svg>
      <span className="absolute text-sm font-bold tabular-nums" aria-label={`score ${pct(score)}`}>{pct(score)}</span>
    </div>
  );
}

export function BandPill({ band }: { band: Band }) {
  const cls = band === "high" ? "bg-signal-soft text-signal" : "bg-accent-soft text-accent";
  return <span className={`rounded-full px-2 py-0.5 font-mono text-xs uppercase tracking-wider ${cls}`}>{bandLabel(band)}</span>;
}

export function StatusPill({ state }: { state: "pending" | "awaiting_worker" | "approved" | "rejected" }) {
  const map = {
    pending: ["Pending", "border-line text-muted"],
    awaiting_worker: ["Decision recorded · applying", "border-accent text-accent"],
    approved: ["Approved", "border-signal text-signal"],
    rejected: ["Rejected", "border-red-500 text-red-600"],
  } as const;
  const [label, cls] = map[state];
  return <span className={`rounded-full border px-2 py-0.5 text-xs ${cls}`}>{label}</span>;
}

/** Factor bars: bar length = value, label shows weight; struck factors are crossed out (spec G2, D3.11). */
export function FactorBars({ rows, compact = false }: { rows: FactorRow[]; compact?: boolean }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No factor rows recorded.</p>;
  return (
    <ul className="space-y-1.5">
      {rows.map((f) => (
        <li key={f.factor} className="grid grid-cols-[minmax(9rem,14rem)_1fr_auto] items-center gap-3 text-sm">
          <span className={f.struck_by_skeptic ? "text-muted line-through" : ""}>
            {f.label}
            {!compact && <span className="ml-1 font-mono text-xs text-muted">w {f.weight.toFixed(2)}</span>}
          </span>
          <span className="h-2 overflow-hidden rounded-full bg-bg" aria-hidden>
            <span
              className={`block h-full rounded-full ${f.struck_by_skeptic ? "bg-line" : "bg-signal"}`}
              style={{ width: `${Math.round(f.value * 100)}%` }}
            />
          </span>
          <span className="w-24 text-right font-mono text-xs tabular-nums text-muted">
            {f.struck_by_skeptic ? "struck" : `${f.value.toFixed(2)} → ${f.contribution.toFixed(3)}`}
          </span>
        </li>
      ))}
    </ul>
  );
}

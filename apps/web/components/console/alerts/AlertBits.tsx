import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { Badge, bandTone } from "@/components/ui";
import { bandLabel, pct, type Band, type FactorRow } from "@/lib/alerts";

/** Band colours follow the foundation (G3): high = sev-high, medium = warn, low = sev-low. Gold is for evidence only. */
const BAND_VAR: Record<string, string> = { high: "var(--sev-high)", medium: "var(--warn)", low: "var(--sev-low)" };

/** Circular score gauge (score is computed by the pipeline in code; F2). */
export function ScoreRing({ score, band, size = 64 }: { score: number; band: Band; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const colour = BAND_VAR[band] ?? "var(--signal)";
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

/**
 * The band pill. High stays the short "HIGH" tag; medium reads "Lead · analyst review" in plain sentence case, so a band
 * that is right only about half the time is not presented like a high alert (copy only: scores and bands are unchanged).
 */
export function BandPill({ band }: { band: Band }) {
  return band === "high"
    ? <Badge tone={bandTone(band)} mono className="uppercase">{bandLabel(band)}</Badge>
    : <Badge tone={bandTone(band)} title="Medium band: a lead for an analyst to review, not a confirmed link">{bandLabel(band)}</Badge>;
}

const STATE = {
  pending: { label: "Pending", tone: "warn", icon: Clock },
  awaiting_worker: { label: "Decision recorded · applying", tone: "info", icon: Loader2 },
  approved: { label: "Approved", tone: "ok", icon: CheckCircle2 },
  rejected: { label: "Rejected", tone: "danger", icon: XCircle },
} as const;

export function StatusPill({ state }: { state: "pending" | "awaiting_worker" | "approved" | "rejected" }) {
  const s = STATE[state];
  return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>;
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

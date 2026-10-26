import { cx } from "./cx";
import { bandTone, type Tone } from "./Badge";

const FILL: Record<Tone, string> = {
  neutral: "bg-muted", signal: "bg-signal", accent: "bg-accent", ok: "bg-ok", warn: "bg-warn",
  danger: "bg-danger", info: "bg-info", brand: "bg-brand", high: "bg-sev-high", low: "bg-sev-low",
};

/**
 * A 0–1 score as a bar plus the number. Colour follows the band if given, else the tone.
 * The number is always shown as text, so the colour is never the only signal.
 */
export function ScoreBar({ value, band, tone, label, className, digits = 3 }: {
  value: number | null | undefined; band?: string | null; tone?: Tone; label?: string; className?: string; digits?: number;
}) {
  const v = value == null || Number.isNaN(value) ? null : Math.max(0, Math.min(1, value));
  const t = tone ?? (band ? bandTone(band) : "signal");
  return (
    <div className={cx("flex items-center gap-2", className)}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2 ring-1 ring-inset ring-line"
        role="img" aria-label={`${label ?? "score"} ${v == null ? "not available" : v.toFixed(digits)}`}>
        {v != null && <div className={cx("h-full rounded-full", FILL[t])} style={{ width: `${v * 100}%` }} />}
      </div>
      <span className="font-mono text-xs tabular-nums text-ink">{v == null ? "—" : v.toFixed(digits)}</span>
    </div>
  );
}

export default ScoreBar;

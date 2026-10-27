import { cx } from "./cx";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Short form of an identifier: a UUID (or anything longer than `max`) keeps its head and tail around an ellipsis. */
export function shortId(value: string, max = 24): string {
  if (UUID.test(value)) return `${value.slice(0, 8)}…${value.slice(-4)}`;
  if (value.length <= max) return value;
  const keep = Math.max(4, Math.floor((max - 1) / 2));
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

/**
 * An identifier as data: mono, small, one line. Long values are shortened in the middle; the full value
 * stays in the tooltip and in the selected/copied text (a visually hidden copy), so nothing is lost.
 * `tone="evidence"` marks Zetaris / evidence ids in gold.
 */
export function Id({ value, max, tone = "muted", className }: { value: string; max?: number; tone?: "muted" | "ink" | "evidence"; className?: string }) {
  const short = shortId(value, max);
  const color = tone === "evidence" ? "text-accent" : tone === "ink" ? "text-ink" : "text-muted";
  if (short === value) return <span className={cx("whitespace-nowrap font-mono text-xs", color, className)}>{value}</span>;
  return (
    // `relative` keeps the absolutely positioned sr-only copy inside this span. Without it the copy is placed
    // against a far ancestor and, inside a horizontally scrolling table, widens the whole page on phones.
    <span title={value} className={cx("relative whitespace-nowrap font-mono text-xs", color, className)}>
      <span aria-hidden className="select-none">{short}</span>
      <span className="sr-only">{value}</span>
    </span>
  );
}

export default Id;

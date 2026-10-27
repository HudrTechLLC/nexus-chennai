import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "./cx";
import type { Tone } from "./Badge";

type IconType = LucideIcon;

const ICON_TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted", signal: "bg-signal-soft text-signal", accent: "bg-accent-soft text-accent",
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info", brand: "bg-brand text-accent-bright", high: "bg-sev-high-soft text-sev-high", low: "bg-sev-low-soft text-sev-low",
};

/**
 * One key figure: label, a big number, a line of context. Optional icon and link.
 * `emphasis`: "primary" colours the number (the one figure that leads a row), "quiet" mutes it (zeros shouldn't shout).
 */
export function StatTile({ label, value, sub, icon: Icon, tone = "signal", href, className, emphasis = "default" }:
  { label: ReactNode; value: ReactNode; sub?: ReactNode; icon?: IconType; tone?: Tone; href?: string; className?: string; emphasis?: "default" | "primary" | "quiet" }) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-medium text-muted">{label}</div>
        {Icon && (
          <span className={cx("grid size-9 shrink-0 place-items-center rounded-lg", ICON_TONE[tone])}>
            <Icon className="size-[18px]" aria-hidden />
          </span>
        )}
      </div>
      <div className={cx("mt-1 text-3xl tabular-nums tracking-tight", emphasis === "primary" ? "font-semibold text-signal" : emphasis === "quiet" ? "font-normal text-muted" : "font-semibold text-ink")}>{value}</div>
      {sub && <div className="mt-1 text-xs leading-snug text-muted">{sub}</div>}
    </>
  );
  const cls = cx("block rounded-xl border border-line bg-surface p-4 shadow-card", className);
  return href ? (
    <Link href={href} className={cx(cls, "transition-shadow duration-150 hover:shadow-raised")}>{body}</Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export default StatTile;

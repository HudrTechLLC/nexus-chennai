import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cx } from "./cx";

type IconType = LucideIcon;

/** What an empty list means and what fills it. The title and text are the caller's copy, unchanged. */
export function EmptyState({ title, children, icon: Icon = Inbox, action, compact = false, className }: {
  title?: ReactNode; children?: ReactNode; icon?: IconType; action?: ReactNode; compact?: boolean; className?: string;
}) {
  return (
    <div className={cx(
      "flex gap-3 rounded-xl border border-dashed border-line bg-surface-2",
      compact ? "items-start p-3 text-sm" : "items-start p-5", className,
    )}>
      <span className={cx("grid shrink-0 place-items-center rounded-lg bg-surface text-muted ring-1 ring-inset ring-line", compact ? "size-8" : "size-10")}>
        <Icon className={compact ? "size-4" : "size-5"} aria-hidden />
      </span>
      <div className="min-w-0 space-y-1">
        {title && <p className="font-medium text-ink">{title}</p>}
        {children && <div className="text-sm leading-relaxed text-muted">{children}</div>}
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  );
}

export default EmptyState;

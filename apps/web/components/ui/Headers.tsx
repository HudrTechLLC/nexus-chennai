import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { ChevronLeft } from "lucide-react";
import { cx } from "./cx";

type IconType = LucideIcon;

/** Top of a page: optional back link, icon, title (h1), one line of description, actions on the right. */
export function PageHeader({ title, description, icon: Icon, back, actions, children, className }: {
  title: ReactNode; description?: ReactNode; icon?: IconType; back?: { href: string; label: string };
  actions?: ReactNode; children?: ReactNode; className?: string;
}) {
  return (
    <header className={cx("space-y-2", className)}>
      {back && (
        <Link href={back.href} className="inline-flex items-center gap-1 text-sm text-muted underline-offset-2 hover:text-ink hover:underline">
          <ChevronLeft className="size-4" aria-hidden />{back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {Icon && (
            <span className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-xl bg-brand text-accent-bright shadow-card">
              <Icon className="size-5" aria-hidden />
            </span>
          )}
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[1.75rem] sm:leading-tight">{title}</h1>
            {description && <div className="mt-1 max-w-3xl text-[15px] leading-relaxed text-muted">{description}</div>}
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

/** Heading inside a page or card (h2 by default). */
export function SectionHeader({ title, description, icon: Icon, actions, as: As = "h2", id, className }: {
  title: ReactNode; description?: ReactNode; icon?: IconType; actions?: ReactNode; as?: "h2" | "h3"; id?: string; className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <As id={id} className="flex items-center gap-2 text-base font-semibold text-ink">
          {Icon && <Icon className="size-[18px] shrink-0 text-signal" aria-hidden />}
          {title}
        </As>
        {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

import type { CSSProperties } from "react";
import type { LucideIcon } from "lucide-react";
import { Activity, Car, CircleDot, CreditCard, House, OctagonAlert, ShieldAlert, ShoppingBag, Wallet } from "lucide-react";
import { categoryStyle, categoryVars, type CategoryIcon as IconName } from "@/lib/categoryStyle";

/** lib/categoryStyle names the icon; this maps the name to the lucide component (the kit in components/ui). */
export const CATEGORY_ICONS: Record<IconName, LucideIcon> = {
  bag: ShoppingBag, wallet: Wallet, home: House, pulse: Activity, card: CreditCard, shield: ShieldAlert,
  octagon: OctagonAlert, car: Car, dot: CircleDot,
};

/** The lucide icon for a crime category (neutral dot for unknown categories). */
export function categoryIcon(category: string | null | undefined): LucideIcon {
  return CATEGORY_ICONS[categoryStyle(category).icon];
}

/** A category's icon in its tinted circle (light and dark tones from lib/categoryStyle). Decorative. */
export function CategoryMark({ category, size = "md" }: { category: string | null | undefined; size?: "sm" | "md" | "lg" }) {
  const Icon = categoryIcon(category);
  const box = size === "lg" ? "size-11" : size === "sm" ? "size-6" : "size-9";
  const icon = size === "lg" ? "size-6" : size === "sm" ? "size-3.5" : "size-5";
  return (
    <span style={categoryVars(category) as CSSProperties}
      className={`inline-flex ${box} shrink-0 items-center justify-center rounded-full bg-[var(--cat-bg)] text-[color:var(--cat-fg)] dark:bg-[var(--cat-bg-d)] dark:text-[color:var(--cat-fg-d)]`}>
      <Icon className={icon} aria-hidden />
    </span>
  );
}

/** Icon plus label pill in the category's colours, shaped like the kit's Badge. `label` is the caller's text. */
export function CategoryBadge({ category, label }: { category: string | null | undefined; label: string }) {
  const Icon = categoryIcon(category);
  return (
    <span style={categoryVars(category) as CSSProperties}
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-[var(--cat-bg)] px-2 py-0.5 text-xs font-medium text-[color:var(--cat-fg)] dark:bg-[var(--cat-bg-d)] dark:text-[color:var(--cat-fg-d)]">
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {label}
    </span>
  );
}

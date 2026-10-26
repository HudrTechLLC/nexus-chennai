import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export type CardTone = "default" | "raised" | "signal" | "accent" | "subtle";

const TONE: Record<CardTone, string> = {
  default: "border border-line bg-surface shadow-card",
  raised: "border border-line bg-surface shadow-raised",
  signal: "border border-[color-mix(in_srgb,var(--signal)_40%,transparent)] bg-surface shadow-card ring-1 ring-inset ring-[color-mix(in_srgb,var(--signal)_10%,transparent)]",
  accent: "border border-[color-mix(in_srgb,var(--accent)_40%,transparent)] bg-surface shadow-card",
  subtle: "border border-line bg-surface-2",
};

const PAD = { none: "", sm: "p-4", md: "p-5", lg: "p-6" } as const;

/** A panel. Never nest one Card in another; use a SectionHeader or a divider inside instead. */
export function Card({ tone = "default", pad = "md", as: As = "section", className, children, ...rest }:
  HTMLAttributes<HTMLElement> & { tone?: CardTone; pad?: keyof typeof PAD; as?: "section" | "div" | "article" | "aside" | "li"; children?: ReactNode }) {
  return <As className={cx("rounded-xl", TONE[tone], PAD[pad], className)} {...rest}>{children}</As>;
}

export default Card;

import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-150 " +
  "disabled:cursor-not-allowed disabled:opacity-60 [&_svg]:size-4 [&_svg]:shrink-0";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-signal text-on-signal shadow-card hover:bg-signal-strong",
  secondary: "border border-line bg-surface text-ink shadow-card hover:bg-surface-2",
  ghost: "text-ink hover:bg-surface-2",
  danger: "border border-[color-mix(in_srgb,var(--danger)_40%,transparent)] bg-surface text-danger hover:bg-danger-soft",
};

const SIZE: Record<ButtonSize, string> = { sm: "h-8 px-3 text-xs", md: "h-10 px-4 text-sm" };

/** Class string for a button look, for <Link> or <a> that should read as a button. */
export function buttonClass({ variant = "primary", size = "md", className }: { variant?: ButtonVariant; size?: ButtonSize; className?: string } = {}) {
  return cx(BASE, VARIANT[variant], SIZE[size], className);
}

/** The one button. type defaults to "button" so it never submits a form by accident. */
export function Button({ variant = "primary", size = "md", className, type = "button", ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <button type={type} className={buttonClass({ variant, size, className })} {...rest} />;
}

export default Button;

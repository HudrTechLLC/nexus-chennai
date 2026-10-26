import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  AlertTriangle, Ban, CheckCircle2, CircleDashed, CircleDot, Clock, Info, Loader2, ShieldCheck, XCircle,
} from "lucide-react";
import { cx } from "./cx";

/** accent (gold) means "from Zetaris / evidence"; high / warn / low are the link-alert bands. */
export type Tone = "neutral" | "signal" | "accent" | "ok" | "warn" | "danger" | "info" | "brand" | "high" | "low";

export const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted ring-line",
  signal: "bg-signal-soft text-signal ring-[color-mix(in_srgb,var(--signal)_25%,transparent)]",
  accent: "bg-accent-soft text-accent ring-[color-mix(in_srgb,var(--accent)_25%,transparent)]",
  ok: "bg-ok-soft text-ok ring-[color-mix(in_srgb,var(--ok)_25%,transparent)]",
  warn: "bg-warn-soft text-warn ring-[color-mix(in_srgb,var(--warn)_25%,transparent)]",
  danger: "bg-danger-soft text-danger ring-[color-mix(in_srgb,var(--danger)_25%,transparent)]",
  info: "bg-info-soft text-info ring-[color-mix(in_srgb,var(--info)_25%,transparent)]",
  brand: "bg-brand text-brand-ink ring-brand-line",
  high: "bg-sev-high-soft text-sev-high ring-[color-mix(in_srgb,var(--sev-high)_25%,transparent)]",
  low: "bg-sev-low-soft text-sev-low ring-[color-mix(in_srgb,var(--sev-low)_25%,transparent)]",
};

type IconType = LucideIcon;

/** A small pill: tone colour, optional icon, the text exactly as given. */
export function Badge({ tone = "neutral", icon: Icon, children, className, mono = false, title }:
  { tone?: Tone; icon?: IconType; children: ReactNode; className?: string; mono?: boolean; title?: string }) {
  return (
    <span title={title} className={cx(
      "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
      mono && "font-mono tracking-wide", TONE_CLASS[tone], className,
    )}>
      {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

/** Status word → tone + icon. Unknown statuses fall back to neutral; the label is always the caller's text. */
const STATUS: Record<string, { tone: Tone; icon: IconType }> = {
  pending: { tone: "warn", icon: Clock },
  proposed: { tone: "warn", icon: Clock },
  open: { tone: "info", icon: CircleDot },
  requested: { tone: "info", icon: Clock },
  queued: { tone: "info", icon: Clock },
  uploaded: { tone: "info", icon: Clock },
  running: { tone: "info", icon: Loader2 },
  profiling: { tone: "info", icon: Loader2 },
  registering: { tone: "info", icon: Loader2 },
  approved: { tone: "ok", icon: CheckCircle2 },
  registered: { tone: "ok", icon: ShieldCheck },
  published: { tone: "ok", icon: CheckCircle2 },
  ok: { tone: "ok", icon: CheckCircle2 },
  done: { tone: "ok", icon: CheckCircle2 },
  success: { tone: "ok", icon: CheckCircle2 },
  live: { tone: "ok", icon: CheckCircle2 },
  screened: { tone: "ok", icon: CheckCircle2 },
  rejected: { tone: "danger", icon: XCircle },
  failed: { tone: "danger", icon: XCircle },
  error: { tone: "danger", icon: XCircle },
  quarantined: { tone: "danger", icon: Ban },
  withdrawn: { tone: "neutral", icon: Ban },
  degraded: { tone: "warn", icon: AlertTriangle },
  sample: { tone: "accent", icon: Info },
  draft: { tone: "neutral", icon: CircleDashed },
};

export function statusTone(status: string | null | undefined): { tone: Tone; icon: IconType } {
  return STATUS[(status ?? "").toLowerCase()] ?? { tone: "neutral", icon: CircleDot };
}

/** A status pill with the matching colour and icon. `label` defaults to the status itself. */
export function StatusPill({ status, label, className }: { status: string | null | undefined; label?: ReactNode; className?: string }) {
  const { tone, icon } = statusTone(status);
  return <Badge tone={tone} icon={icon} className={className}>{label ?? status ?? "unknown"}</Badge>;
}

/** Band → tone, for link-alert confidence bands. */
export function bandTone(band: string | null | undefined): Tone {
  const b = (band ?? "").toLowerCase();
  return b === "high" ? "high" : b === "medium" ? "warn" : b === "low" ? "low" : "neutral";
}

export default Badge;

import { guardBadges, type Guard, type TipStatus } from "@/lib/tips";

const TONE = {
  ok: "bg-signal-soft text-signal",
  warn: "bg-accent-soft text-accent",
  bad: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  muted: "bg-bg text-muted",
} as const;

export function GuardBadges({ guard, status }: { guard: Guard; status: TipStatus }) {
  return (
    <span className="flex flex-wrap gap-1">
      {guardBadges(guard, status).map((b, i) => (
        <span key={i} className={`rounded-full px-2 py-0.5 text-xs ${TONE[b.tone]}`}>{b.label}</span>
      ))}
    </span>
  );
}

/** Untrusted tip text: plain text in a fenced box, never rendered as markup or links (spec J2). */
export function UntrustedText({ text, clamp = false }: { text: string; clamp?: boolean }) {
  return (
    <div className="rounded-md border border-dashed border-line bg-bg p-3">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-muted">Untrusted tip text</p>
      <p className={`whitespace-pre-wrap break-words text-sm ${clamp ? "line-clamp-4" : ""}`}>{text}</p>
    </div>
  );
}

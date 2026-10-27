import { KeyRound } from "lucide-react";
import type { DemoLogin } from "@/lib/demoLogins";
import { ROLE_LABEL, type Role } from "@/lib/roles";

const roleLabel = (d: DemoLogin) => ROLE_LABEL[d.role as Role] ?? d.label;

/**
 * "Demo accounts" tiles under the sign-in form: one row on wide screens, wrapping, stacked on phones.
 * A tile fills the form; the user still presses Sign in. The admin tile fills the email only.
 */
export function DemoPanel({ demos, picked, onPick }: { demos: DemoLogin[]; picked?: string | null; onPick?: (d: DemoLogin) => void }) {
  if (demos.length === 0) return null;
  const pickedDemo = demos.find((d) => d.email === picked);
  return (
    <section aria-labelledby="demo-accounts" className="mt-6 rounded-xl border border-line bg-surface p-5 shadow-card">
      <h2 id="demo-accounts" className="text-sm font-semibold">Demo accounts</h2>
      <p className="mt-1 text-xs text-muted">Synthetic data. Pick one to fill the form, then press Sign in.</p>
      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
        {demos.map((d) => (
          <li key={d.email} className="min-w-0">
            <button
              type="button"
              onClick={() => onPick?.(d)}
              aria-pressed={picked === d.email}
              className="flex h-full w-full flex-col rounded-lg border border-line bg-bg px-3 py-2.5 text-left text-sm transition-colors duration-150 hover:border-signal aria-pressed:border-signal aria-pressed:bg-signal-soft"
            >
              <span className="font-semibold">{roleLabel(d)}</span>
              {d.station && <span className="text-xs text-ink">{d.station}</span>}
              {/* wrap at the @ first; anywhere only if a part still does not fit */}
              <span className="mt-1 font-mono text-xs text-muted [overflow-wrap:anywhere]">
                {d.email.split("@")[0]}<wbr />@{d.email.split("@").slice(1).join("@")}
              </span>
              {d.password === null && (
                <span className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted">
                  <KeyRound className="size-3.5" aria-hidden />Type the password
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      <p aria-live="polite" className="sr-only">
        {pickedDemo
          ? pickedDemo.password === null
            ? `Filled ${pickedDemo.email}. Type the password, then press Sign in.`
            : `Filled ${pickedDemo.email}. Press Sign in.`
          : ""}
      </p>
    </section>
  );
}

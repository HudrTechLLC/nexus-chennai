import type { DemoLogin } from "@/lib/demoLogins";

/** "Demo accounts" list under the sign-in form. Buttons fill the form; the user still presses Sign in. */
export function DemoPanel({ demos, picked, onPick }: { demos: DemoLogin[]; picked?: string | null; onPick?: (d: DemoLogin) => void }) {
  if (demos.length === 0) return null;
  return (
    <section aria-labelledby="demo-accounts" className="mt-6 rounded-xl border border-line bg-surface p-5">
      <h2 id="demo-accounts" className="text-sm font-semibold">Demo accounts</h2>
      <p className="mt-1 text-xs text-muted">Synthetic data. Pick one to fill the form, then press Sign in.</p>
      <ul className="mt-3 space-y-2">
        {demos.map((d) => (
          <li key={d.email}>
            <button
              type="button"
              onClick={() => onPick?.(d)}
              aria-pressed={picked === d.email}
              className="w-full rounded-md border border-line px-3 py-2 text-left text-sm hover:border-signal focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal aria-pressed:border-signal aria-pressed:bg-signal-soft"
            >
              <span className="block font-medium">{d.label}</span>
              <span className="block break-all font-mono text-xs text-muted">{d.email}</span>
            </button>
          </li>
        ))}
      </ul>
      <p aria-live="polite" className="sr-only">{picked ? `Filled ${picked}. Press Sign in.` : ""}</p>
    </section>
  );
}

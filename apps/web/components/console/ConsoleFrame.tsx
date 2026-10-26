import Link from "next/link";
import type { ReactNode } from "react";
import { navFor, ROLE_LABEL } from "@/lib/roles";
import type { Officer } from "@/lib/auth";

/** Police console frame: role-gated nav, who is signed in, sign out. */
export function ConsoleFrame({ officer, children }: { officer: Officer; children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Link href="/console" className="text-lg font-bold uppercase tracking-wide">
            Nexus <span className="text-muted">· Console</span>
          </Link>
          <nav className="flex flex-1 flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
            {navFor(officer.role).map((n) => (
              <Link key={n.href} href={n.href} className="hover:text-ink">
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-muted">{officer.name}</span>
            <span className="rounded-full bg-signal-soft px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-signal">
              {ROLE_LABEL[officer.role]}
              {officer.stationId ? ` · ${officer.stationId}` : ""}
            </span>
            <form action="/console/signout" method="post">
              <button className="text-muted underline-offset-2 hover:text-ink hover:underline">Sign out</button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-7xl px-4 pb-6 text-xs text-muted">
        Hackathon prototype. All data is synthetic.
      </footer>
    </div>
  );
}

/** Honest placeholder for a console screen that is not built yet. */
export function ConsoleNotYet({ title, task, what }: { title: string; task: string; what: string }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-6">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">Not built yet · {task}</p>
      <h1 className="mt-1 text-2xl font-bold">{title}</h1>
      <p className="mt-2 max-w-prose text-muted">{what}</p>
    </section>
  );
}

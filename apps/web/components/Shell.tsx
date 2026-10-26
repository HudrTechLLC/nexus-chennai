import Link from "next/link";
import type { ReactNode } from "react";

/** Page frame shared by the public portal pages. */
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-5xl flex-wrap items-baseline gap-x-6 gap-y-2 px-4 py-3">
          <Link href="/" className="text-xl font-bold uppercase tracking-wide">Nexus · Chennai</Link>
          <nav className="flex gap-4 text-sm text-muted">
            <Link href="/appeals" className="hover:text-ink">Appeals</Link>
            <Link href="/map" className="hover:text-ink">Crime map</Link>
            <Link href="/tip" className="hover:text-ink">Send a tip</Link>
            <Link href="/console" className="hover:text-ink">Police login</Link>
            <Link href="/docs/progress" className="hover:text-ink">Engg Docs</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-muted">
        Hackathon prototype. All data is synthetic. Not an official police service.
      </footer>
    </div>
  );
}

/** Honest placeholder for a screen that is not built yet. */
export function NotYet({ title, phase, what }: { title: string; phase: string; what: string }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-6">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">Coming in {phase}</p>
      <h1 className="mt-1 text-3xl font-bold">{title}</h1>
      <p className="mt-2 max-w-prose text-muted">{what}</p>
    </section>
  );
}

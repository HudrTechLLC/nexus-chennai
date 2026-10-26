import Link from "next/link";
import type { ReactNode } from "react";
import { BrandLockup } from "@/components/ui";
import { PublicNav } from "./PublicNav";

/** Page frame shared by the public portal pages: navy brand bar with the hex mark, icon nav, police login. */
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="on-brand sticky top-0 z-sticky h-14 border-b border-brand-line bg-brand-bar text-brand-ink">
        <div className="relative mx-auto flex h-full max-w-5xl items-center gap-6 px-4">
          <Link href="/" className="rounded-md"><BrandLockup /></Link>
          <PublicNav />
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
    <section className="rounded-xl border border-line bg-surface p-6 shadow-card">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">Coming in {phase}</p>
      <h1 className="mt-1 text-3xl font-bold">{title}</h1>
      <p className="mt-2 max-w-prose text-muted">{what}</p>
    </section>
  );
}

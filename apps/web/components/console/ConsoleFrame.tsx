import Link from "next/link";
import type { ReactNode } from "react";
import { navFor, ROLE_LABEL } from "@/lib/roles";
import type { Officer } from "@/lib/auth";
import { NotificationBell } from "./notifications/NotificationBell";

/** Police console frame: role-gated nav, who is signed in, sign out. */
export function ConsoleFrame({ officer, unread = 0, children }: { officer: Officer; unread?: number; children: ReactNode }) {
  const links = navFor(officer.role).map((n) => (
    <Link key={n.href} href={n.href} className="hover:text-ink">
      {n.label}
    </Link>
  ));
  const who = (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      {/* the role pill already says who is signed in; the name only shows on wide screens so the nav stays on one line at 1080p + zoom */}
      <span className="text-muted md:hidden min-[1700px]:inline">{officer.name}</span>
      <span className="rounded-full bg-signal-soft px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-signal">
        {ROLE_LABEL[officer.role]}
        {officer.stationId ? ` · ${officer.stationId}` : ""}
      </span>
      <form action="/console/signout" method="post">
        <button className="text-muted underline-offset-2 hover:text-ink hover:underline">Sign out</button>
      </form>
    </div>
  );
  return (
    <div className="min-h-screen">
      <header className="relative border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl items-center gap-x-6 gap-y-2 px-4 py-3 md:flex-wrap">
          <Link href="/console" className="text-lg font-bold uppercase tracking-wide">
            Nexus <span className="text-muted">· Console</span>
          </Link>
          {/* md and up: inline nav + who is signed in */}
          <nav className="hidden flex-1 flex-wrap gap-x-3 gap-y-1 text-sm text-muted md:flex xl:gap-x-4">
            {links}
          </nav>
          <div className="hidden md:flex">{who}</div>
          {/* the bell is mounted once (one Realtime channel), outside both copies of the nav */}
          <div className="ml-auto md:ml-0"><NotificationBell userId={officer.userId} initial={unread} /></div>
          {/* phones: one-line bar, everything else behind a native disclosure (no client JS) */}
          <details className="group md:hidden">
            <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md border border-line px-3 py-1.5 text-sm [&::-webkit-details-marker]:hidden">
              <span aria-hidden>☰</span> Menu
            </summary>
            <div className="absolute inset-x-0 z-30 mt-3 border-b border-line bg-surface px-4 pb-4 shadow-lg">
              <nav className="grid grid-cols-2 gap-x-4 gap-y-2 py-3 text-sm text-muted">{links}</nav>
              <div className="border-t border-line pt-3">{who}</div>
            </div>
          </details>
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

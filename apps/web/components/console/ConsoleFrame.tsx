import Link from "next/link";
import type { ReactNode } from "react";
import { LogOut } from "lucide-react";
import { navFor, ROLE_LABEL } from "@/lib/roles";
import type { Officer } from "@/lib/auth";
import { BrandLockup } from "@/components/ui";
import { NotificationBell } from "./notifications/NotificationBell";
import { ConsoleMenuButton, ConsoleSidebar } from "./ConsoleNav";

/** Police console frame: navy brand bar, grouped role-gated sidebar (drawer on narrow screens), who is signed in. */
export function ConsoleFrame({ officer, unread = 0, children }: { officer: Officer; unread?: number; children: ReactNode }) {
  const items = navFor(officer.role);
  const role = (
    <span className="rounded-full bg-white/10 px-2.5 py-1 font-mono text-[11px] font-medium uppercase tracking-wider text-accent-bright">
      {ROLE_LABEL[officer.role]}
      {officer.stationId ? ` · ${officer.stationId}` : ""}
    </span>
  );
  const signOut = (
    <form action="/console/signout" method="post">
      <button className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-brand-muted hover:bg-brand-hover hover:text-brand-ink">
        <LogOut className="size-4" aria-hidden />Sign out
      </button>
    </form>
  );
  return (
    <div className="min-h-screen">
      <header className="on-brand sticky top-0 z-sticky h-14 border-b border-brand-line bg-brand-bar text-brand-ink">
        <div className="flex h-full items-center gap-3 px-4">
          <Link href="/console" className="rounded-md">
            <BrandLockup sub="Console" />
          </Link>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <span className="hidden text-sm text-brand-muted min-[1100px]:inline">{officer.name}</span>
            <span className="hidden sm:inline-flex">{role}</span>
            {/* the bell is mounted once (one Realtime channel) */}
            <NotificationBell userId={officer.userId} initial={unread} />
            <span className="hidden lg:block">{signOut}</span>
            <ConsoleMenuButton items={items} footer={<div className="flex flex-wrap items-center gap-3">{role}<span className="text-sm text-brand-muted">{officer.name}</span>{signOut}</div>} />
          </div>
        </div>
      </header>
      <div className="flex">
        <ConsoleSidebar items={items} />
        <div className="min-w-0 flex-1">
          <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
          <footer className="mx-auto max-w-7xl px-4 pb-6 text-xs text-muted sm:px-6">
            Hackathon prototype. All data is synthetic.
          </footer>
        </div>
      </div>
    </div>
  );
}

/** Honest placeholder for a console screen that is not built yet. */
export function ConsoleNotYet({ title, task, what }: { title: string; task: string; what: string }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-6 shadow-card">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">Not built yet · {task}</p>
      <h1 className="mt-1 text-2xl font-bold">{title}</h1>
      <p className="mt-2 max-w-prose text-muted">{what}</p>
    </section>
  );
}

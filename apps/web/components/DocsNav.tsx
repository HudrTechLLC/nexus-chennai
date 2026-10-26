"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Note, SpecTab } from "@/lib/docs";

/** Engg Docs menu: progress, the 16 spec tabs, and the project notes. */
export function DocsNav({ tabs, notes }: { tabs: SpecTab[]; notes: Note[] }) {
  const path = usePathname();
  const tab = (href: string, label: string) => {
    const on = path === href;
    return (
      <Link
        key={href}
        href={href}
        aria-current={on ? "page" : undefined}
        className={`flex-none border-b-[3px] px-3 py-2 text-sm font-semibold uppercase tracking-wide ${
          on ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
        }`}
      >
        {label}
      </Link>
    );
  };
  return (
    <div className="grid gap-1">
      <nav aria-label="Spec tabs" className="flex overflow-x-auto">
        {tab("/docs/progress", "Progress")}
        {tabs.map((t) => tab(`/docs/${t.id}`, t.label))}
      </nav>
      <nav aria-label="Project notes" className="flex flex-wrap gap-x-4 gap-y-1 px-3 pb-2 text-xs text-muted">
        <span className="font-mono uppercase tracking-widest">Notes</span>
        {notes.map((n) => (
          <Link
            key={n.slug}
            href={`/docs/notes/${n.slug}`}
            className={path === `/docs/notes/${n.slug}` ? "text-ink underline" : "hover:text-ink"}
          >
            {n.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import type { NavGroup } from "@/lib/docs";

function Groups({ groups, path }: { groups: NavGroup[]; path: string }) {
  return (
    <div className="grid gap-6">
      {groups.map((g) => (
        <section key={g.title} aria-labelledby={`nav-${g.title}`}>
          <h2 id={`nav-${g.title}`} className="mb-1.5 px-3 text-xs font-semibold text-muted">
            {g.title}
          </h2>
          <ul className="grid gap-0.5">
            {g.items.map((it) => {
              const on = path === it.href;
              return (
                <li key={it.href}>
                  <Link
                    href={it.href}
                    aria-current={on ? "page" : undefined}
                    className={`block rounded-lg px-3 py-1.5 text-[14px] leading-snug transition-colors duration-150 ${
                      on
                        ? "bg-signal-soft font-semibold text-signal"
                        : "text-muted hover:bg-surface-2 hover:text-ink"
                    }`}
                  >
                    {it.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** Desktop: sticky grouped sidebar. Phone: a collapsible menu that closes on navigation. */
export function DocsNav({ groups }: { groups: NavGroup[] }) {
  const path = usePathname();
  const current = groups.flatMap((g) => g.items).find((i) => i.href === path)?.label ?? "Menu";
  const mobile = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (mobile.current) mobile.current.open = false;
  }, [path]);

  return (
    <>
      <details ref={mobile} className="group border-b border-line bg-surface lg:hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold">
          <span>
            <span className="mr-2 font-mono text-[11px] uppercase tracking-widest text-muted">Docs</span>
            {current}
          </span>
          <span aria-hidden className="text-muted transition-transform group-open:rotate-180">▾</span>
        </summary>
        <nav aria-label="Documentation" className="max-h-[70vh] overflow-y-auto px-2 pb-4">
          <Groups groups={groups} path={path} />
        </nav>
      </details>

      <nav
        aria-label="Documentation"
        className="sticky top-14 hidden h-[calc(100vh-3.5rem)] overflow-y-auto border-r border-line py-6 pr-3 [scrollbar-width:thin] lg:block"
      >
        <Groups groups={groups} path={path} />
      </nav>
    </>
  );
}

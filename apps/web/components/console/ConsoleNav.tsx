"use client";

import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bell, Boxes, Brain, Car, Database, FileText, FolderSearch, LayoutDashboard, Map as MapIcon, Megaphone, Menu,
  MessageSquareText, Network, Search, Server, ShieldAlert, Sparkles, UserCog, Users, Workflow, X,
} from "lucide-react";
import { NAV_GROUPS, type NavItem } from "@/lib/roles";
import { cx } from "@/components/ui";

type IconType = LucideIcon;

/** Icon per nav item key (lib/roles.ts NAV[].icon). */
export const NAV_ICONS: Record<string, IconType> = {
  overview: LayoutDashboard, map: MapIcon, ask: Sparkles, bell: Bell,
  cases: FolderSearch, search: Search, vehicles: Car, graph: Network,
  alerts: ShieldAlert, series: Workflow, taskforces: Users, memory: Brain,
  appeals: Megaphone, tips: MessageSquareText,
  stations: Boxes, sources: Database, system: Server, admin: UserCog, doc: FileText,
};

/** The item the path belongs to: the longest href that is the path or a parent of it ("/console" only exactly). */
export function activeHref(items: Pick<NavItem, "href">[], path: string): string | null {
  const hits = items.filter((n) => (n.href === "/console" ? path === "/console" : path === n.href || path.startsWith(n.href + "/")));
  return hits.sort((a, b) => b.href.length - a.href.length)[0]?.href ?? null;
}

function Groups({ items, path, onNavigate, wide }: { items: NavItem[]; path: string; onNavigate?: () => void; wide: boolean }) {
  const shown = wide ? items.filter((n) => n.desktop !== "bell") : items;
  const active = activeHref(shown, path);
  return (
    <div className="space-y-5">
      {NAV_GROUPS.map((g) => {
        const list = shown.filter((n) => n.group === g.key);
        if (!list.length) return null;
        return (
          <div key={g.key} role="group" aria-labelledby={g.label ? `nav-${g.key}` : undefined}>
            {g.label && (
              <div id={`nav-${g.key}`} className="mb-1 px-3 text-xs font-semibold text-brand-muted">{g.label}</div>
            )}
            <ul className="space-y-0.5">
              {list.map((n) => {
                const Icon = NAV_ICONS[n.icon] ?? LayoutDashboard;
                const on = n.href === active;
                return (
                  <li key={n.href}>
                    <Link href={n.href} onClick={onNavigate} aria-current={on ? "page" : undefined}
                      className={cx(
                        "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150",
                        on ? "bg-white/10 font-semibold text-brand-ink shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]"
                          : "text-brand-muted hover:bg-brand-hover hover:text-brand-ink",
                      )}>
                      <Icon className={cx("size-[18px] shrink-0", on ? "text-accent-bright" : "text-brand-muted group-hover:text-brand-ink")} aria-hidden />
                      <span className="truncate">{n.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

/** Wide screens: the sticky grouped sidebar. */
export function ConsoleSidebar({ items }: { items: NavItem[] }) {
  const path = usePathname() ?? "/console";
  return (
    <nav aria-label="Console" className="on-brand sticky top-14 hidden h-[calc(100vh-3.5rem)] w-60 shrink-0 overflow-y-auto border-r border-brand-line bg-brand px-3 py-5 [scrollbar-width:thin] lg:block">
      <Groups items={items} path={path} wide />
    </nav>
  );
}

/** Narrow screens: a Menu button that opens the same groups as a drawer; it closes on navigation and on Escape. */
export function ConsoleMenuButton({ items, footer }: { items: NavItem[]; footer?: React.ReactNode }) {
  const path = usePathname() ?? "/console";
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <div className="lg:hidden">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="console-drawer"
        className="inline-flex items-center gap-2 rounded-lg border border-brand-line px-3 py-1.5 text-sm text-brand-ink hover:bg-brand-hover">
        {open ? <X className="size-4" aria-hidden /> : <Menu className="size-4" aria-hidden />} Menu
      </button>
      {open && (
        <div id="console-drawer" className="on-brand absolute inset-x-0 top-14 z-drawer max-h-[calc(100vh-3.5rem)] overflow-y-auto border-b border-brand-line bg-brand px-4 pb-5 pt-4 shadow-raised">
          <nav aria-label="Console"><Groups items={items} path={path} wide={false} onNavigate={() => setOpen(false)} /></nav>
          {footer && <div className="mt-5 border-t border-brand-line pt-4">{footer}</div>}
        </div>
      )}
    </div>
  );
}

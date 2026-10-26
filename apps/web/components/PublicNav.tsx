"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { BookOpen, LogIn, Map as MapIcon, Megaphone, Menu, MessageSquarePlus, X } from "lucide-react";
import { cx } from "@/components/ui";

const LINKS = [
  { href: "/appeals", label: "Appeals", icon: Megaphone },
  { href: "/map", label: "Crime map", icon: MapIcon },
  { href: "/tip", label: "Send a tip", icon: MessageSquarePlus },
  { href: "/docs/progress", label: "Engg Docs", icon: BookOpen },
];

const isOn = (path: string, href: string) => {
  const root = href === "/docs/progress" ? "/docs" : href;
  return path === root || path.startsWith(root + "/");
};

/** Public portal nav on the navy bar: icon links with an active underline; "Police login" as a button; a menu on phones. */
export function PublicNav() {
  const path = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);

  const items = (stacked: boolean) => LINKS.map(({ href, label, icon: Icon }) => {
    const on = isOn(path, href);
    return (
      <Link key={href} href={href} aria-current={on ? "page" : undefined}
        className={cx(
          "inline-flex items-center gap-2 text-sm transition-colors duration-150",
          stacked ? "rounded-lg px-3 py-2" : "relative h-14 px-1",
          on ? "font-semibold text-brand-ink" : "text-brand-muted hover:text-brand-ink",
          stacked && (on ? "bg-white/10" : "hover:bg-brand-hover"),
        )}>
        <Icon className={cx("size-4", on && "text-accent-bright")} aria-hidden />
        {label}
        {!stacked && on && <span aria-hidden className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-accent-bright" />}
      </Link>
    );
  });

  const login = (
    <Link href="/console"
      className="inline-flex h-9 items-center gap-2 rounded-lg bg-accent-bright px-3.5 text-sm font-semibold text-brand transition-colors hover:bg-[#f6c96e]">
      <LogIn className="size-4" aria-hidden />Police login
    </Link>
  );

  return (
    <>
      <nav aria-label="Main" className="hidden flex-1 items-center gap-6 md:flex">{items(false)}</nav>
      <div className="ml-auto hidden md:block">{login}</div>
      <div className="ml-auto md:hidden">
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="public-menu"
          className="inline-flex items-center gap-2 rounded-lg border border-brand-line px-3 py-1.5 text-sm text-brand-ink hover:bg-brand-hover">
          {open ? <X className="size-4" aria-hidden /> : <Menu className="size-4" aria-hidden />} Menu
        </button>
        {open && (
          <div id="public-menu" className="on-brand absolute inset-x-0 top-14 z-drawer border-b border-brand-line bg-brand px-4 pb-4 pt-3 shadow-raised">
            <nav aria-label="Main" className="grid gap-1">{items(true)}</nav>
            <div className="mt-3 border-t border-brand-line pt-3">{login}</div>
          </div>
        )}
      </div>
    </>
  );
}

export default PublicNav;

import Link from "next/link";
import type { Metadata } from "next";
import { DocsNav } from "@/components/DocsNav";
import { getNav } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Nexus · Engg Docs",
  description: "Nexus Chennai engineering spec, progress and project notes.",
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const groups = getNav();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 h-14 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-[1400px] items-center gap-3 px-4">
          <Link href="/docs/progress" className="flex items-baseline gap-2">
            <span className="text-lg font-bold uppercase tracking-wide">Nexus</span>
            <span className="font-mono text-xs uppercase tracking-widest text-accent">Engg Docs</span>
          </Link>
          <span className="hidden truncate font-mono text-xs text-muted md:inline">
            Crime-linking spec · Open Agent Hackathon 2026 · Track 1
          </span>
          <Link href="/" className="ml-auto rounded-md border border-line px-3 py-1 text-sm text-muted hover:text-ink">
            Open app
          </Link>
        </div>
      </header>
      <div className="mx-auto max-w-[1400px] lg:grid lg:grid-cols-[250px_minmax(0,1fr)] lg:gap-8 lg:px-4">
        <DocsNav groups={groups} />
        <main className="min-w-0 px-4 py-8 lg:px-0">{children}</main>
      </div>
    </div>
  );
}

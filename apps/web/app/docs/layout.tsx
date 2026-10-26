import Link from "next/link";
import type { Metadata } from "next";
import { DocsNav } from "@/components/DocsNav";
import { getIndex } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Nexus · Engg Docs",
  description: "Nexus Chennai engineering spec, progress and project notes.",
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const { tabs, notes } = getIndex();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-line bg-surface">
        <div className="mx-auto max-w-6xl px-4 pt-3">
          <div className="flex flex-wrap items-baseline gap-x-4">
            <Link href="/docs/progress" className="text-xl font-bold uppercase tracking-wide">
              Nexus · Engg Docs
            </Link>
            <span className="font-mono text-xs text-muted">Crime-linking spec · Open Agent Hackathon 2026 · Track 1</span>
            <Link href="/" className="ml-auto text-sm text-muted hover:text-ink">
              Back to app
            </Link>
          </div>
          <DocsNav tabs={tabs} notes={notes} />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}

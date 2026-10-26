import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import { DocsNav } from "@/components/DocsNav";
import { BrandLockup } from "@/components/ui";
import { getNav } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Nexus · Engg Docs",
  description: "Nexus Chennai engineering spec, progress and project notes.",
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const groups = getNav();
  return (
    <div className="min-h-screen">
      <header className="on-brand sticky top-0 z-sticky h-14 border-b border-brand-line bg-brand-bar text-brand-ink">
        <div className="mx-auto flex h-full max-w-[1400px] items-center gap-4 px-4">
          <Link href="/docs/progress" className="rounded-md"><BrandLockup sub="Engg Docs" /></Link>
          <span className="hidden truncate text-xs text-brand-muted md:inline">
            Crime-linking spec · Open Agent Hackathon 2026 · Track 1
          </span>
          <Link
            href="/"
            className="ml-auto inline-flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-accent-bright px-3 text-sm sm:px-4 font-semibold text-brand transition-colors hover:bg-[#f6c96e]"
          >
            Open app <ArrowRight className="size-4" aria-hidden />
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

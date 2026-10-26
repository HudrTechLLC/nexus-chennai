import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { Markdown } from "@/components/Markdown";
import { getIndex, getSpecTab } from "@/lib/docs";

export const dynamicParams = false;

export function generateStaticParams() {
  return getIndex().tabs.map((t) => ({ tab: t.id }));
}

export function generateMetadata({ params }: { params: { tab: string } }): Metadata {
  const tab = getIndex().tabs.find((t) => t.id === params.tab);
  return { title: tab ? `${tab.label} · Nexus Engg Docs` : "Nexus Engg Docs" };
}

export default function SpecTabPage({ params }: { params: { tab: string } }) {
  const tab = getIndex().tabs.find((t) => t.id === params.tab);
  if (!tab) notFound();
  return (
    <article>
      <p className="mb-2 font-mono text-xs uppercase tracking-widest text-accent">Spec · #{tab.id}</p>
      <Markdown source={getSpecTab(tab.id)} />
    </article>
  );
}

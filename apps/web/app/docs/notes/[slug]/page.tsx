import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { Markdown } from "@/components/Markdown";
import { getIndex, getNote } from "@/lib/docs";

export const dynamicParams = false;

export function generateStaticParams() {
  return getIndex().notes.map((n) => ({ slug: n.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const note = getIndex().notes.find((n) => n.slug === params.slug);
  return { title: note ? `${note.label} · Nexus Engg Docs` : "Nexus Engg Docs" };
}

export default function NotePage({ params }: { params: { slug: string } }) {
  const note = getIndex().notes.find((n) => n.slug === params.slug);
  if (!note) notFound();
  return (
    <article>
      <p className="mb-2 font-mono text-xs uppercase tracking-widest text-accent">Project note · engg/docs/{note.file}</p>
      <Markdown source={getNote(note.slug)} />
    </article>
  );
}

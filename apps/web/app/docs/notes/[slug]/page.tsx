import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { DocPage } from "@/components/DocPage";
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
  return <DocPage href={`/docs/notes/${note.slug}`} eyebrow={`Project note · engg/docs/${note.file}`} source={getNote(note.slug)} file={note.file} />;
}

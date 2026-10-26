import Link from "next/link";
import { notFound } from "next/navigation";
import { getAppeal } from "@/lib/publicData";

export const revalidate = 60;

export default async function AppealDetail({ params }: { params: { publicId: string } }) {
  const a = await getAppeal(decodeURIComponent(params.publicId));
  if (!a) notFound();
  return (
    <article className="mx-auto max-w-2xl space-y-5">
      <Link href="/appeals" className="text-sm text-muted hover:text-ink">← All appeals</Link>
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-accent">{a.area} · week {a.week} · {a.time_window}</p>
        <h1 className="mt-1 text-3xl font-bold">{a.title}</h1>
      </header>
      <p className="text-lg">{a.summary}</p>
      {a.looking_for.length > 0 && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="font-semibold">What police are looking for</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">{a.looking_for.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </section>
      )}
      {a.images.length > 0 && (
        <p className="text-sm text-muted">{a.images.length} blurred still{a.images.length === 1 ? "" : "s"} attached to this appeal.</p>
      )}
      <section className="rounded-xl border border-line bg-surface p-5 text-sm">
        <h2 className="font-semibold">Timeline</h2>
        <p className="mt-1 text-muted">Happened in week {a.week} ({a.time_window.toLowerCase()}). Published {a.published_at ? new Date(a.published_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "recently"}. {a.tip_count} tip{a.tip_count === 1 ? "" : "s"} received.</p>
      </section>
      <div className="flex flex-wrap gap-3">
        <Link href={`/tip/new?appeal=${encodeURIComponent(a.id)}`} className="rounded-md bg-signal px-4 py-2 font-medium text-white">Share a tip</Link>
        <Link href={`/tip/new?appeal=${encodeURIComponent(a.id)}&kind=cctv`} className="rounded-md border border-line px-4 py-2">I have CCTV</Link>
      </div>
      <p className="text-xs text-muted">In an emergency, call 112.</p>
    </article>
  );
}

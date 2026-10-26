import Link from "next/link";
import type { Appeal } from "@/lib/publicData";

/** Appeal card (spec G1 /appeals): title, area, week, time window, what police are looking for, tip count. */
export function AppealCard({ a }: { a: Appeal }) {
  return (
    <article className="flex flex-col rounded-xl border border-line bg-surface p-5">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">{a.area} · {a.week} · {a.time_window}</p>
      <h2 className="mt-1 text-lg font-bold">
        <Link href={`/appeals/${encodeURIComponent(a.id)}`} className="hover:underline">{a.title}</Link>
      </h2>
      {a.looking_for.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-muted">
          {a.looking_for.slice(0, 3).map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      )}
      <div className="mt-auto flex items-center justify-between pt-4 text-sm">
        <span className="rounded-full bg-bg px-2 py-0.5 text-xs">{a.tip_count} tip{a.tip_count === 1 ? "" : "s"} so far</span>
        <Link href={`/tip/new?appeal=${encodeURIComponent(a.id)}`} className="rounded-md bg-signal px-3 py-1.5 text-white">Share a tip</Link>
      </div>
    </article>
  );
}

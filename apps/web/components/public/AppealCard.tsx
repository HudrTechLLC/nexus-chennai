import Link from "next/link";
import type { Appeal } from "@/lib/publicData";
import { appealTipHref, crimeMapHref } from "@/lib/publicArea";

/** Appeal card (spec G1 /appeals): title, area, week, time window, what police are looking for, tip count. */
export function AppealCard({ a }: { a: Appeal }) {
  const where = crimeMapHref(a.cell); // public r8 hexagon only, never a point
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
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4 text-sm">
        <span className="rounded-full bg-bg px-2 py-0.5 text-xs">{a.tip_count} tip{a.tip_count === 1 ? "" : "s"} so far</span>
        <div className="flex shrink-0 gap-2 whitespace-nowrap">
          {where && (
            <Link href={where} aria-label={`View location of this appeal on the crime map: ${a.title}`}
              className="rounded-md border border-line px-3 py-1.5 hover:border-signal">View location</Link>
          )}
          <Link href={appealTipHref(a.id)} aria-label={`Add a tip about this appeal: ${a.title}`} className="rounded-md bg-signal px-3 py-1.5 text-white">Add a tip</Link>
        </div>
      </div>
    </article>
  );
}

"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { PublicMap } from "@/lib/publicData";

const PublicHexMap = dynamic(() => import("./PublicHexMap"), {
  ssr: false, loading: () => <div className="h-[65vh] min-h-[420px] rounded-xl border border-line bg-surface" />,
});

const label = (c: string) => c.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase());

/** Filters (crime type, last 7 / 30 / 90 days) around the public hex map. */
export function PublicMapView({ map, days }: { map: PublicMap; days: number }) {
  const [category, setCategory] = useState<string | null>(null);
  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const c of map.cells) for (const k of Object.keys(c.by_category)) s.add(k);
    return Array.from(s).sort();
  }, [map.cells]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {[7, 30, 90].map((d) => (
          <Link key={d} href={`/map?days=${d}`} className={`rounded-full border px-3 py-1 ${d === days ? "border-signal bg-signal-soft" : "border-line"}`}>Last {d} days</Link>
        ))}
        <span className="mx-1 text-muted">·</span>
        <button onClick={() => setCategory(null)} className={`rounded-full border px-3 py-1 ${!category ? "border-signal bg-signal-soft" : "border-line"}`}>All types</button>
        {categories.map((c) => (
          <button key={c} onClick={() => setCategory(c)} className={`rounded-full border px-3 py-1 ${category === c ? "border-signal bg-signal-soft" : "border-line"}`}>{label(c)}</button>
        ))}
      </div>
      <PublicHexMap cells={map.cells} category={category} />
      <p className="text-xs text-muted">
        Each hexagon is about 0.7 km². Areas with fewer than {map.min_count} reported crimes are hidden, and there are no exact locations or victim details.
        Outlined hexagons have an open police appeal.
      </p>
    </div>
  );
}

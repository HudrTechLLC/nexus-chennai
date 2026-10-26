"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useTransition, type ReactNode } from "react";
import type { PublicMap } from "@/lib/publicData";
import { MAP_DAYS, labelOf, mapHref, type MapAt, type MapState } from "@/lib/publicCards";

const PublicHexMap = dynamic(() => import("./PublicHexMap"), {
  ssr: false, loading: () => <div className="h-[65vh] min-h-[420px] rounded-xl border border-line bg-surface" />,
});

/**
 * Filters (crime type, last 7 / 30 / 90 days) around the public hex map. Every choice lives in the URL
 * (days, type, hex, at), so the crime detail view's "Back to map" restores exactly this view.
 * Clicking a hexagon selects it; the server renders that hexagon's cards into `panel`.
 */
export function PublicMapView({ map, state, panel }: { map: PublicMap; state: MapState; panel?: ReactNode }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const c of map.cells) for (const k of Object.keys(c.by_category)) s.add(k);
    return Array.from(s).sort();
  }, [map.cells]);

  const go = (next: MapState) => startTransition(() => router.replace(mapHref(next), { scroll: false }));
  const chip = (on: boolean) => `rounded-full border px-3 py-1 ${on ? "border-signal bg-signal-soft" : "border-line"}`;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {MAP_DAYS.map((d) => (
          <Link key={d} href={mapHref({ ...state, days: d })} scroll={false} className={chip(d === state.days)}>Last {d} days</Link>
        ))}
        <span className="mx-1 text-muted">·</span>
        <button onClick={() => go({ ...state, type: null })} className={chip(!state.type)}>All types</button>
        {categories.map((c) => (
          <button key={c} onClick={() => go({ ...state, type: c })} className={chip(state.type === c)}>{labelOf(c)}</button>
        ))}
      </div>
      <div className="relative">
        <PublicHexMap
          cells={map.cells}
          category={state.type}
          selected={state.hex}
          initialAt={state.at}
          onSelect={(cell: string | null, at: MapAt) => go({ ...state, hex: cell, at })}
        />
        {pending && (
          <div className="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full border border-line bg-surface px-3 py-1 text-xs shadow">
            Loading…
          </div>
        )}
        {panel}
      </div>
      <p className="text-xs text-muted">
        Each hexagon is about 0.7 km². Tap one to see the crimes reported there. Areas with fewer than {map.min_count} reported
        crimes are hidden, and there are no exact locations or victim details. Outlined hexagons have an open police appeal.
      </p>
    </div>
  );
}

"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useTransition, type ReactNode } from "react";
import type { PublicMap } from "@/lib/publicData";
import { MAP_DAYS, labelOf, mapHref, type MapAt, type MapState } from "@/lib/publicCards";
import { areaRows, escapeClosesPanel, focusAfterNavigation } from "@/lib/publicArea";
import { AreaList } from "./AreaList";
import { categoryIcon } from "./CategoryIcon";
import { MapLegend } from "./MapLegend";


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

  // Keyboard path to the cards: the "Areas with crimes" list opens the same panel (?hex=), focus moves into
  // the panel, and Esc closes it and returns focus to the row it came from.
  const rows = useMemo(() => areaRows(map.cells, state.type), [map.cells, state.type]);
  const openedFrom = useRef<string | null>(null);
  const returnTo = useRef<string | null>(null);
  const openFromList = (cell: string) => {
    openedFrom.current = cell;
    returnTo.current = null;
    go({ ...state, hex: cell });
  };
  useEffect(() => {
    const t = focusAfterNavigation({ pending, hex: state.hex, openedFrom: openedFrom.current, returnTo: returnTo.current });
    if (!t) return;
    if (t.kind === "panel") {
      document.getElementById("hex-panel")?.focus();
      openedFrom.current = null;
      returnTo.current = state.hex; // Esc goes back to this row
    } else {
      document.querySelector<HTMLButtonElement>(`button[data-cell="${t.cell}"]`)?.focus();
      returnTo.current = null;
    }
  }, [pending, state.hex]);
  useEffect(() => {
    if (!state.hex) return;
    const onKey = (e: KeyboardEvent) => {
      if (!escapeClosesPanel({ key: e.key, defaultPrevented: e.defaultPrevented, target: e.target as HTMLElement | null }, true)) return;
      e.preventDefault();
      returnTo.current = returnTo.current ?? state.hex;
      go({ ...state, hex: null });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // go/state are rebuilt each render; the listener only needs the current hex
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.hex, state.days, state.type]);
  const chip = (on: boolean) => `rounded-full border px-3 py-1 ${on ? "border-signal bg-signal-soft" : "border-line"}`;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {MAP_DAYS.map((d) => (
          <Link key={d} href={mapHref({ ...state, days: d })} scroll={false} className={chip(d === state.days)}>Last {d} days</Link>
        ))}
        <span className="mx-1 text-muted">·</span>
        <button onClick={() => go({ ...state, type: null })} className={chip(!state.type)}>All types</button>
        {categories.map((c) => {
          const CatIcon = categoryIcon(c);
          return (
            <button key={c} onClick={() => go({ ...state, type: c })} className={`${chip(state.type === c)} inline-flex items-center gap-1.5`}>
              <CatIcon className="size-3.5" aria-hidden />{labelOf(c)}
            </button>
          );
        })}
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
      <MapLegend minCount={map.min_count} />
      <AreaList rows={rows} selected={state.hex} onOpen={openFromList} />
      <p className="text-xs text-muted">
        Each hexagon is about 0.7 km². Tap one, or pick it from the list, to see the crimes reported there. Areas with fewer than {map.min_count} reported
        crimes are hidden, and there are no exact locations or victim details. Outlined hexagons have an open police appeal.
      </p>
    </div>
  );
}

"use client";
import dynamic from "next/dynamic";
import type { LonLat } from "@/lib/pulse";
import type { SeriesMapPoint } from "./SeriesMap";

/** deck.gl and MapLibre need WebGL, so the series map renders only in the browser. */
const SeriesMap = dynamic(() => import("./SeriesMap"), {
  ssr: false,
  loading: () => <div className="grid h-80 place-items-center rounded-xl border border-line bg-surface text-sm text-muted">Loading the map…</div>,
});

export function SeriesMapLoader(props: { points: SeriesMapPoint[]; hull: LonLat[] | null }) {
  return <SeriesMap {...props} />;
}

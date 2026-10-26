"use client";
import { useEffect, useMemo, useState } from "react";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { CITY } from "@/lib/city";
import { bbox } from "@/lib/series";
import type { LonLat } from "@/lib/pulse";
import { MapCanvas } from "@/components/console/map/MapCanvas";

export type SeriesMapPoint = { id: string; p: LonLat; exact: boolean; label: string; order: number };

/**
 * Series map: member scenes in time order, joined by a path, inside the series hull.
 * Exact points where the officer may read the crime; otherwise the centre of its H3 cell (hollow).
 */
export function SeriesMap({ points, hull }: { points: SeriesMapPoint[]; hull: LonLat[] | null }) {
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const [hover, setHover] = useState<SeriesMapPoint | null>(null);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setTheme(mq.matches ? "dark" : "light");
  }, []);

  const view = useMemo(() => {
    const b = bbox(points.map((x) => x.p));
    if (!b) return { center: CITY.map.center, zoom: CITY.map.zoom, bounds: CITY.map.bounds };
    const span = Math.max(b[2] - b[0], b[3] - b[1], 0.005);
    const zoom = Math.max(10, Math.min(15, Math.log2(360 / span) - 1.2));
    return { center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] as [number, number], zoom, bounds: CITY.map.bounds };
  }, [points]);

  const layers = useMemo(() => {
    const ordered = points.slice().sort((a, b) => a.order - b.order);
    return [
      hull && new PolygonLayer<{ ring: LonLat[] }>({
        id: "hull", data: [{ ring: hull }], getPolygon: (d) => d.ring, stroked: true, filled: true,
        getFillColor: [14, 124, 134, 40], getLineColor: [14, 124, 134, 200], lineWidthMinPixels: 1.5,
      }),
      ordered.length > 1 && new PathLayer<{ path: LonLat[] }>({
        id: "order", data: [{ path: ordered.map((x) => x.p) }], getPath: (d) => d.path,
        getColor: theme === "dark" ? [210, 174, 106, 160] : [138, 106, 47, 160], widthMinPixels: 1.5,
      }),
      new ScatterplotLayer<SeriesMapPoint>({
        id: "members", data: points, getPosition: (d) => d.p, pickable: true,
        radiusUnits: "pixels", getRadius: (d) => (d.exact ? 6 : 9), stroked: true, filled: true,
        getFillColor: (d) => (d.exact ? [14, 124, 134, 230] : [14, 124, 134, 40]),
        getLineColor: theme === "dark" ? [255, 255, 255, 220] : [19, 33, 48, 220], lineWidthMinPixels: 1.5,
        updateTriggers: { getLineColor: theme },
      }),
    ].filter(Boolean) as Layer[];
  }, [points, hull, theme]);

  if (points.length === 0) {
    return <div className="grid h-80 place-items-center rounded-xl border border-dashed border-line text-sm text-muted">No member scene can be placed on the map.</div>;
  }
  return (
    <div className="relative h-80 overflow-hidden rounded-xl border border-line">
      <MapCanvas view={view} layers={layers} theme={theme} onHover={(i: PickingInfo) => setHover((i.object as SeriesMapPoint) ?? null)} />
      <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] px-2 py-1 text-xs text-muted">
        {hover ? `#${hover.order + 1} · ${hover.label}${hover.exact ? "" : " (cell centre)"}` : "Filled: exact scene · hollow: H3 cell only · line: time order"}
      </div>
    </div>
  );
}

export default SeriesMap;


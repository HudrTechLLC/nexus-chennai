"use client";
import { useEffect, useMemo, useState } from "react";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { CITY } from "@/lib/city";
import { bbox } from "@/lib/series";
import type { LonLat } from "@/lib/pulse";
import type { Scene, TrailRead } from "@/lib/alertMap";
import { MapCanvas } from "@/components/console/map/MapCanvas";

export type AlertMapProps = { scenes: (Scene & { label: string })[]; trail: { plate: string; reads: TrailRead[] }[] };

type Hover = { kind: "scene"; label: string; exact: boolean } | { kind: "read"; r: TrailRead } | null;

const istTime = (at: string) =>
  new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/**
 * Both scenes of a link alert, plus the ANPR trail of the plates read near them (camera points joined in time
 * order). Exact scene points where the officer may read the crime; otherwise the H3 cell centre (hollow).
 */
export function AlertMap({ scenes, trail }: AlertMapProps) {
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const [hover, setHover] = useState<Hover>(null);
  useEffect(() => {
    setTheme(window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }, []);

  const reads = useMemo(() => trail.flatMap((t) => t.reads), [trail]);
  const view = useMemo(() => {
    const b = bbox([...scenes.map((s) => s.p), ...reads.map((r) => r.p)]);
    if (!b) return { center: CITY.map.center, zoom: CITY.map.zoom, bounds: CITY.map.bounds };
    const span = Math.max(b[2] - b[0], b[3] - b[1], 0.005);
    const zoom = Math.max(10, Math.min(15, Math.log2(360 / span) - 1.2));
    return { center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] as [number, number], zoom, bounds: CITY.map.bounds };
  }, [scenes, reads]);

  const layers = useMemo(() => {
    const ink: [number, number, number, number] = theme === "dark" ? [255, 255, 255, 220] : [19, 33, 48, 220];
    return [
      scenes.length === 2 && new PathLayer<{ path: LonLat[] }>({
        id: "between", data: [{ path: scenes.map((s) => s.p) }], getPath: (d) => d.path,
        getColor: [120, 120, 120, 120], widthMinPixels: 1,
      }),
      ...trail.map((t) => t.reads.length > 1 && new PathLayer<{ path: LonLat[] }>({
        id: `trail-${t.plate}`, data: [{ path: t.reads.map((r) => r.p) }], getPath: (d) => d.path,
        getColor: theme === "dark" ? [210, 174, 106, 210] : [138, 106, 47, 210], widthMinPixels: 2.5,
      })),
      new ScatterplotLayer<TrailRead>({
        id: "reads", data: reads, getPosition: (d) => d.p, pickable: true, radiusUnits: "pixels", getRadius: 4,
        getFillColor: theme === "dark" ? [210, 174, 106, 240] : [138, 106, 47, 240], stroked: true, getLineColor: ink, lineWidthMinPixels: 1,
        updateTriggers: { getLineColor: theme, getFillColor: theme },
      }),
      new ScatterplotLayer<Scene & { label: string }>({
        id: "scenes", data: scenes, getPosition: (d) => d.p, pickable: true, radiusUnits: "pixels",
        getRadius: (d) => (d.exact ? 8 : 11), stroked: true, filled: true,
        getFillColor: (d) => (d.exact ? [196, 64, 52, 230] : [196, 64, 52, 50]), getLineColor: ink, lineWidthMinPixels: 1.5,
        updateTriggers: { getLineColor: theme },
      }),
    ].filter(Boolean) as Layer[];
  }, [scenes, trail, reads, theme]);

  if (scenes.length === 0) {
    return <div className="grid h-72 place-items-center rounded-xl border border-dashed border-line text-sm text-muted">Neither scene can be placed on the map.</div>;
  }
  const caption = !hover
    ? "Red: scenes (hollow = area cell only) · gold: ANPR camera reads of the matched plate, joined in time order"
    : hover.kind === "scene"
      ? `${hover.label}${hover.exact ? "" : " (area cell centre)"}`
      : `${hover.r.plate_text} · camera ${hover.r.camera_id} · ${istTime(hover.r.read_at)}`;
  return (
    <div>
      <div className="relative h-72 overflow-hidden rounded-xl border border-line">
        <MapCanvas
          view={view}
          layers={layers}
          theme={theme}
          onHover={(i: PickingInfo) => {
            const o = i.object as (Scene & { label: string }) | TrailRead | undefined;
            setHover(!o ? null : "read_id" in o ? { kind: "read", r: o } : { kind: "scene", label: o.label, exact: o.exact });
          }}
        />
      </div>
      {/* Caption sits under the map, not over it, so it can never hide a scene or camera point. */}
      <p className="mt-2 min-h-[2.5rem] text-xs leading-snug text-muted">{caption}</p>
    </div>
  );
}

export default AlertMap;

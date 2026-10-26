"use client";
import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import { cellToBoundary } from "h3-js";
import { CITY } from "@/lib/city";
import type { PublicCell } from "@/lib/publicData";
import { framePadding, type MapAt } from "@/lib/publicCards";
import { cellBounds } from "@/lib/publicArea";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * Public crime map (spec G1 /map): H3 r8 cells coloured by count, gentle pulse on cells with an
 * open appeal. Data arrives already aggregated with the minimum-count cutoff; there are no points.
 * Clicking a cell selects it (outlined) and reports the current view, so the URL can restore it.
 */
export function PublicHexMap({ cells, category, selected = null, initialAt = null, onSelect }: {
  cells: PublicCell[];
  category: string | null;
  selected?: string | null;
  initialAt?: MapAt | null;
  onSelect?: (cell: string | null, at: MapAt) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const handlers = useRef({ onSelect });
  handlers.current = { onSelect };
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const data = useMemo(() => {
    const rows = cells
      .map((c) => ({ ...c, v: category ? c.by_category[category] ?? 0 : c.n }))
      .filter((c) => c.v > 0);
    const max = Math.max(1, ...rows.map((r) => r.v));
    return {
      type: "FeatureCollection" as const,
      features: rows.map((c) => ({
        type: "Feature" as const,
        properties: { cell: c.cell, n: c.v, k: c.v / max, appeal: c.appeal ? 1 : 0 },
        geometry: { type: "Polygon" as const, coordinates: [cellToBoundary(c.cell, true)] },
      })),
    };
  }, [cells, category]);

  useEffect(() => {
    if (!el.current) return;
    const fb = selected ? cellBounds(selected) : null;
    const m = new maplibregl.Map({
      container: el.current, style: "/map/light.json",
      center: initialAt ? [initialAt[0], initialAt[1]] : CITY.map.center, zoom: initialAt ? initialAt[2] : CITY.map.zoom,
      // opened on one hex with no saved view (/map?cell= from an appeal): start framed on it, neighbourhood around
      ...(!initialAt && fb ? { bounds: [[fb[0], fb[1]], [fb[2], fb[3]]] as [[number, number], [number, number]], fitBoundsOptions: { padding: framePadding(el.current.clientWidth, el.current.clientHeight), maxZoom: 14 } } : {}),
      attributionControl: { compact: true, customAttribution: "© OpenStreetMap contributors · OpenFreeMap" },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("hex", { type: "geojson", data });
      m.addLayer({
        id: "hex-fill", type: "fill", source: "hex",
        paint: {
          "fill-color": ["interpolate", ["linear"], ["get", "k"], 0, "#fde68a", 0.5, "#f97316", 1, "#b91c1c"],
          "fill-opacity": 0.55,
        },
      });
      m.addLayer({ id: "hex-line", type: "line", source: "hex", paint: { "line-color": "#ffffff", "line-width": 0.6, "line-opacity": 0.7 } });
      m.addLayer({
        id: "hex-appeal", type: "line", source: "hex", filter: ["==", ["get", "appeal"], 1],
        paint: { "line-color": "#0e7c86", "line-width": 3, "line-opacity": 0.9 },
      });
      m.addLayer({
        id: "hex-selected", type: "line", source: "hex", filter: ["==", ["get", "cell"], selectedRef.current ?? ""],
        paint: { "line-color": "#111827", "line-width": 3.5 },
      });
      m.on("click", "hex-fill", (e) => {
        const cell = e.features?.[0]?.properties?.cell as string | undefined;
        const c = m.getCenter();
        if (cell) handlers.current.onSelect?.(cell, [c.lng, c.lat, m.getZoom()]);
      });
      m.on("mouseenter", "hex-fill", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "hex-fill", () => { m.getCanvas().style.cursor = ""; });
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
      m.on("mousemove", "hex-fill", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        popup.setLngLat(e.lngLat).setText(`${f.properties.n} reported crimes${f.properties.appeal ? " · open appeal here" : ""}`).addTo(m);
      });
      m.on("mouseleave", "hex-fill", () => popup.remove());
    });
    // gentle pulse on appeal cells
    let t = 0;
    const timer = setInterval(() => {
      t += 0.1;
      if (m.getLayer("hex-appeal")) m.setPaintProperty("hex-appeal", "line-opacity", 0.45 + 0.45 * Math.abs(Math.sin(t)));
    }, 100);
    map.current = m;
    return () => { clearInterval(timer); m.remove(); };
    // created once; data updates below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    (map.current?.getSource("hex") as maplibregl.GeoJSONSource | undefined)?.setData(data);
  }, [data]);

  useEffect(() => {
    if (map.current?.getLayer("hex-selected")) map.current.setFilter("hex-selected", ["==", ["get", "cell"], selected ?? ""]);
  }, [selected]);

  return <div ref={el} className="h-[65vh] min-h-[420px] w-full overflow-hidden rounded-xl border border-line" />;
}

export default PublicHexMap;

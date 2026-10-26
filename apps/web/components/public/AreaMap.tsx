"use client";
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { cellToBoundary } from "h3-js";
import { cellBounds } from "@/lib/publicArea";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * Small, fixed map of one public area (an appeal's H3 r8 hexagon). It shows the outline only,
 * never a point, framed with a little of the neighbourhood around it for context.
 */
export function AreaMap({ cell }: { cell: string }) {
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!el.current) return;
    const b = cellBounds(cell);
    const m = new maplibregl.Map({
      container: el.current, style: "/map/light.json",
      bounds: [[b[0], b[1]], [b[2], b[3]]], fitBoundsOptions: { padding: 48, maxZoom: 14 },
      interactive: false,
      attributionControl: { compact: true, customAttribution: "© OpenStreetMap contributors · OpenFreeMap" },
    });
    m.on("load", () => {
      m.addSource("area", {
        type: "geojson",
        data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [cellToBoundary(cell, true)] } },
      });
      m.addLayer({ id: "area-fill", type: "fill", source: "area", paint: { "fill-color": "#0e7c86", "fill-opacity": 0.25 } });
      m.addLayer({ id: "area-line", type: "line", source: "area", paint: { "line-color": "#0e7c86", "line-width": 2.5 } });
    });
    return () => m.remove();
  }, [cell]);

  return <div ref={el} role="img" aria-label="Map of the area where it happened, shown as a hexagon of about 0.7 km²" className="h-56 w-full overflow-hidden rounded-lg border border-line" />;
}

export default AreaMap;

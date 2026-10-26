"use client";
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { cellToBoundary, cellToLatLng, latLngToCell } from "h3-js";
import { CITY } from "@/lib/city";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * "Roughly where?" picker (spec G1): tap the map and the whole H3 resolution-8 hexagon
 * (about 0.7 km²) is chosen. Only the cell id is sent; the tapped point never leaves the browser.
 */
export function HexPicker({ cell, onChange }: { cell: string | null; onChange: (cell: string | null) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const cb = useRef(onChange);
  cb.current = onChange;

  const geo = (c: string | null) => ({
    type: "FeatureCollection" as const,
    features: c ? [{
      type: "Feature" as const, properties: {},
      geometry: { type: "Polygon" as const, coordinates: [cellToBoundary(c, true)] },
    }] : [],
  });

  useEffect(() => {
    if (!el.current) return;
    // A prefilled area (WS4-12) opens centred on its hexagon, close enough to see it.
    const [lat, lng] = cell ? cellToLatLng(cell) : [0, 0];
    const m = new maplibregl.Map({
      container: el.current, style: "/map/light.json",
      center: cell ? [lng, lat] : CITY.map.center, zoom: cell ? Math.max(CITY.map.zoom, 13) : CITY.map.zoom,
      attributionControl: { compact: true, customAttribution: "© OpenStreetMap contributors · OpenFreeMap" },
    });
    m.on("load", () => {
      m.addSource("pick", { type: "geojson", data: geo(cell) });
      m.addLayer({ id: "pick-fill", type: "fill", source: "pick", paint: { "fill-color": "#0e7c86", "fill-opacity": 0.3 } });
      m.addLayer({ id: "pick-line", type: "line", source: "pick", paint: { "line-color": "#0e7c86", "line-width": 2 } });
    });
    m.on("click", (e) => cb.current(latLngToCell(e.lngLat.lat, e.lngLat.lng, CITY.h3.public)));
    map.current = m;
    return () => m.remove();
    // created once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const src = map.current?.getSource("pick") as maplibregl.GeoJSONSource | undefined;
    src?.setData(geo(cell));
  }, [cell]);

  return (
    <div>
      <div ref={el} className="h-64 w-full overflow-hidden rounded-lg border border-line" />
      <p className="mt-1 text-xs text-muted">
        {cell ? "Area chosen. We keep only this hexagon, not a point." : "Tap the map near where it happened. Optional."}
        {cell && <button type="button" className="ml-2 underline" onClick={() => onChange(null)}>clear</button>}
      </p>
    </div>
  );
}

"use client";
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer, PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";

export type MapView = { center: [number, number]; zoom: number; bounds?: [number, number, number, number] };

/**
 * MapLibre basemap (self-hosted style JSON, OSM-derived OpenFreeMap tiles) with a deck.gl overlay.
 * Layers are passed in; the canvas only owns the map and the overlay.
 */
export function MapCanvas({ view, layers, theme, onClick, onHover }: {
  view: MapView;
  layers: Layer[];
  theme: "dark" | "light";
  onClick?: (info: PickingInfo) => void;
  onHover?: (info: PickingInfo) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const handlers = useRef({ onClick, onHover });
  handlers.current = { onClick, onHover };

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      style: `/map/${theme}.json`,
      center: view.center,
      zoom: view.zoom,
      maxBounds: view.bounds
        ? [[view.bounds[0] - 0.3, view.bounds[1] - 0.3], [view.bounds[2] + 0.3, view.bounds[3] + 0.3]]
        : undefined,
      attributionControl: { compact: true, customAttribution: "© OpenStreetMap contributors · OpenFreeMap" },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const o = new MapboxOverlay({
      interleaved: false,
      layers: [],
      onClick: (info) => handlers.current.onClick?.(info),
      onHover: (info) => handlers.current.onHover?.(info),
      getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
    });
    m.addControl(o);
    map.current = m;
    overlay.current = o;
    return () => {
      m.remove();
      map.current = null;
      overlay.current = null;
    };
    // The map is created once; view changes after mount are handled by the user panning.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    map.current?.setStyle(`/map/${theme}.json`);
  }, [theme]);

  useEffect(() => {
    overlay.current?.setProps({ layers });
  }, [layers]);

  return <div ref={el} className="h-full w-full" />;
}

export default MapCanvas;

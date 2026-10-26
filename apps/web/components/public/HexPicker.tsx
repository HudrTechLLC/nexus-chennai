"use client";
import { useEffect, useId, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { cellToBoundary, cellToLatLng, latLngToCell } from "h3-js";
import { CITY } from "@/lib/city";
import { MAP_INK, currentMapTheme, mapStyleUrl } from "@/lib/publicMapTheme";
import { fetchPlaces, GEOCODE_DEBOUNCE_MS, GEOCODE_MIN_CHARS, type PlaceSuggestion } from "@/lib/geocodeClient";
import { AREA_SIZES, cellRes, suggestedRes, DEFAULT_AREA_RES, resizeCell, zoomFor, type AreaRes, type Point } from "@/lib/tipArea";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * "Roughly where?" picker (spec G1, J1; WS4-15). Tap the map, or search a place, and the whole H3 hexagon
 * around it is chosen at the size picked below the map (Large r8 / Medium r9 / Small r10). Only the cell id
 * is sent; the tapped or searched point never leaves the browser. Place search goes through our own
 * /api/geocode route, never straight to a third party.
 */
export function HexPicker({ cell, onChange }: { cell: string | null; onChange: (cell: string | null) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const cb = useRef(onChange);
  cb.current = onChange;
  const [res, setResState] = useState<AreaRes>(() => (cell ? cellRes(cell) : DEFAULT_AREA_RES));
  const resRef = useRef(res);
  const cellRef = useRef(cell);
  cellRef.current = cell;
  const point = useRef<Point | null>(null); // browser only, never sent
  const [hint, setHint] = useState<AreaRes | null>(null);

  // The size changes ONLY when the tipster taps Large/Medium/Small (J1): zooming is not consent to a
  // more precise area. Zooming in close shows a non-binding hint instead (nexus-6 review of #308).
  const setRes = (r: AreaRes) => {
    resRef.current = r;
    setResState(r);
    setHint(null);
    if (cellRef.current) cb.current(resizeCell(cellRef.current, r, point.current));
  };

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
    const theme = currentMapTheme();
    const m = new maplibregl.Map({
      container: el.current, style: mapStyleUrl(theme),
      center: cell ? [lng, lat] : CITY.map.center,
      zoom: cell ? Math.max(CITY.map.zoom, zoomFor(cellRes(cell))) : CITY.map.zoom,
      attributionControl: { compact: true, customAttribution: "© OpenStreetMap contributors · OpenFreeMap" },
    });
    m.on("load", () => {
      // Start the compact attribution collapsed (the ⓘ still opens it): expanded it covers the hexagon on phones.
      el.current?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      m.addSource("pick", { type: "geojson", data: geo(cellRef.current) });
      m.addLayer({ id: "pick-fill", type: "fill", source: "pick", paint: { "fill-color": MAP_INK[theme].signal, "fill-opacity": 0.3 } });
      m.addLayer({ id: "pick-line", type: "line", source: "pick", paint: { "line-color": MAP_INK[theme].signal, "line-width": 2 } });
    });
    m.on("click", (e) => {
      point.current = { lat: e.lngLat.lat, lng: e.lngLat.lng };
      cb.current(latLngToCell(e.lngLat.lat, e.lngLat.lng, resRef.current));
      // From the city view a small hexagon is a dot: zoom in so the tipster can see and nudge it.
      const z = zoomFor(resRef.current);
      if (m.getZoom() < z - 1) m.easeTo({ center: e.lngLat, zoom: z });
    });
    // Zooming in close only suggests a smaller size; it never changes it.
    m.on("zoomend", () => {
      const next = suggestedRes(m.getZoom(), resRef.current);
      setHint(next !== resRef.current ? next : null);
    });
    map.current = m;
    return () => m.remove();
    // created once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const src = map.current?.getSource("pick") as maplibregl.GeoJSONSource | undefined;
    src?.setData(geo(cell));
  }, [cell]);

  function pickPlace(s: PlaceSuggestion) {
    point.current = { lat: s.lat, lng: s.lng };
    cb.current(latLngToCell(s.lat, s.lng, resRef.current));
    map.current?.flyTo({ center: [s.lng, s.lat], zoom: zoomFor(resRef.current) });
  }

  return (
    <div className="space-y-2">
      <PlaceSearch onPick={pickPlace} />
      <div ref={el} className="h-64 w-full overflow-hidden rounded-lg border border-line" />
      {/* Toggle buttons (aria-pressed), not a radiogroup: native Tab + Enter/Space work with no custom key handling. */}
      <div role="group" aria-label="Area size" className="flex flex-wrap gap-2">
        {AREA_SIZES.map((s) => (
          <button key={s.res} type="button" aria-pressed={res === s.res} onClick={() => setRes(s.res)}
            className={`rounded-full border px-3 py-1 text-xs ${res === s.res ? "border-signal bg-signal-soft" : "border-line"}`}>
            {s.label} <span className="text-muted">{s.km2}</span>
          </button>
        ))}
      </div>
      {/* Always mounted, so screen readers announce the hint when it appears (a live region added later is often missed). */}
      <div aria-live="polite" data-testid="area-hint">
        {hint && (
          <p className="text-xs">
            Zoomed in. Choose {AREA_SIZES.find((s) => s.res === hint)?.label} for a tighter area?{" "}
            <button type="button" className="underline" onClick={() => setRes(hint)}>Use {AREA_SIZES.find((s) => s.res === hint)?.label.toLowerCase()}</button>
            <button type="button" className="ml-2 text-muted underline" onClick={() => setHint(null)}>No thanks</button>
          </p>
        )}
      </div>
      <p className="text-xs text-muted" aria-live="polite">
        {cell ? "Area chosen. We keep only this small area, not an exact point." : "Search a place or tap the map near where it happened. Optional."}
        {cell && <button type="button" className="ml-2 underline" onClick={() => { point.current = null; onChange(null); }}>clear</button>}
      </p>
    </div>
  );
}

/** Type-ahead place search (WS4-15): debounced, through POST /api/geocode; the text is never stored. */
function PlaceSearch({ onPick }: { onPick: (s: PlaceSuggestion) => void }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<PlaceSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [searching, setSearching] = useState(false);
  const picked = useRef(false);
  const listId = useId();

  useEffect(() => {
    if (picked.current) { picked.current = false; return; }
    if (q.trim().length < GEOCODE_MIN_CHARS) { setItems([]); setOpen(false); return; }
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setSearching(true);
      const found = await fetchPlaces(q, { signal: ctrl.signal });
      if (ctrl.signal.aborted) return;
      setSearching(false);
      setItems(found);
      setActive(-1);
      setOpen(true);
    }, GEOCODE_DEBOUNCE_MS);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q]);

  const choose = (s: PlaceSuggestion) => {
    picked.current = true;
    setQ(s.label);
    setOpen(false);
    onPick(s);
  };

  return (
    <div className="relative">
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a street, landmark or area"
        aria-label="Search for a place near where it happened"
        role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list" autoComplete="off" maxLength={100}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        onKeyDown={(e) => {
          if (!open || !items.length) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a + 1) % items.length); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a <= 0 ? items.length - 1 : a - 1)); }
          else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(items[active]); }
          else if (e.key === "Escape") setOpen(false);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="w-full rounded-md border border-line bg-bg px-3 py-2 text-sm" />
      {searching && <span className="absolute right-3 top-2 text-xs text-muted">…</span>}
      {open && (
        <div className="absolute z-10 mt-1 w-full rounded-md border border-line bg-surface shadow-lg">
          {items.length ? (
            <ul id={listId} role="listbox">
              {items.map((s, i) => (
                <li key={`${s.label}-${i}`} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(s)}
                    className={`block w-full px-3 py-2 text-left text-sm ${i === active ? "bg-signal-soft" : ""}`}>{s.label}</button>
                </li>
              ))}
            </ul>
          ) : (
            <p id={listId} className="px-3 py-2 text-sm text-muted">No matching place. Try another name, or tap the map.</p>
          )}
          <p className="border-t border-line px-3 py-1 text-[10px] text-muted">© OpenStreetMap contributors</p>
        </div>
      )}
    </div>
  );
}

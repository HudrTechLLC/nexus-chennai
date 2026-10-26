"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer, PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { H3HexagonLayer, TripsLayer } from "@deck.gl/geo-layers";
import { PathStyleExtension } from "@deck.gl/extensions";
import { cellToLatLng } from "h3-js";
import { CITY } from "@/lib/city";
import type { Role } from "@/lib/roles";
import {
  arcPath, binDaily, binHours, CAT_COLOUR, CAT_GLYPH, CAT_KEYS, CAT_LABEL, catKey, convexHull, DAY_MS, localDay,
  padRing, passes, pulsePhase, pulseTier, tzOffsetMinutes, type CatKey, type CrimeFilter, type LonLat, type MapCrime,
} from "@/lib/pulse";
import { MapCanvas } from "./MapCanvas";
import { ClockDial } from "./ClockDial";
import { TimeScrubber } from "./TimeScrubber";
import { CrimeDrawer } from "./CrimeDrawer";
import { usePulseData, type LinkPoint } from "./usePulseData";

type Toggles = {
  arcs: boolean; hulls: boolean; hex: boolean; stations: boolean; wards: boolean; rejected: boolean; glyphs: boolean;
};

const SPEED_MS_PER_DAY = 100; // G3: 1 day per 100 ms
const OFFSET = tzOffsetMinutes(CITY.timezone);

/** Exact point when the caller may read the crime, else the centre of its H3 cell (RLS: other stations). */
function pointOf(p: LinkPoint | undefined, byId: Map<string, MapCrime>, id: string): LonLat | null {
  const c = byId.get(id);
  if (c) return c.pos;
  if (p?.lon != null && p?.lat != null) return [p.lon, p.lat];
  if (p?.cell) {
    const [lat, lon] = cellToLatLng(p.cell);
    return [lon, lat];
  }
  return null;
}

export default function PulseMap({ stationId, role }: { stationId: string | null; role: Role }) {
  const data = usePulseData();
  const [cats, setCats] = useState<Set<CatKey>>(new Set(CAT_KEYS));
  const [win, setWin] = useState<[number, number] | null>(null);
  const [playing, setPlaying] = useState(false);
  const [clock, setClock] = useState<[number, number] | null>(null);
  const [linkedOnly, setLinkedOnly] = useState(false);
  const [seriesOnly, setSeriesOnly] = useState(false);
  const [minScore, setMinScore] = useState(0.55);
  const [constellation, setConstellation] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [toggles, setToggles] = useState<Toggles>({ arcs: true, hulls: true, hex: false, stations: false, wards: false, rejected: false, glyphs: false });
  const [selected, setSelected] = useState<MapCrime | null>(null);
  const [now, setNow] = useState(0);
  const playRef = useRef<number | null>(null);

  // Initial window: the last 30 days of the visible data.
  useEffect(() => {
    if (data.extent && !win) setWin([Math.max(data.extent.min, data.extent.max - 30 * DAY_MS), data.extent.max]);
  }, [data.extent, win]);

  // Animation clock for pulses and travelling arcs.
  useEffect(() => {
    let raf = 0;
    const tick = (t: number) => { setNow(t); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Play: advance the window by one day per SPEED_MS_PER_DAY, crimes ignite as the playhead passes them.
  useEffect(() => {
    if (!playing || !data.extent) return;
    const ext = data.extent;
    let last = performance.now();
    const step = (t: number) => {
      const days = (t - last) / SPEED_MS_PER_DAY;
      last = t;
      setWin((w) => {
        if (!w) return w;
        const len = w[1] - w[0];
        const to = w[1] + days * DAY_MS;
        if (to >= ext.max) { setPlaying(false); return [ext.max - len, ext.max]; }
        return [to - len, to];
      });
      playRef.current = requestAnimationFrame(step);
    };
    playRef.current = requestAnimationFrame(step);
    return () => { if (playRef.current) cancelAnimationFrame(playRef.current); };
  }, [playing, data.extent]);

  const togglePlay = () => {
    if (!playing && data.extent && win && win[1] >= data.extent.max - DAY_MS) {
      const len = win[1] - win[0];
      setWin([data.extent.min, data.extent.min + len]); // rewind to the start, keep the window length
    }
    setPlaying((p) => !p);
  };

  const byId = useMemo(() => new Map(data.crimes.map((c) => [c.id, c])), [data.crimes]);

  const filter: CrimeFilter | null = win
    ? { cats, from: win[0], to: win[1], clock, linkedOnly, seriesOnly, stations: new Set(), statuses: new Set() }
    : null;

  // Everything that passes the filters except the time window (feeds the histograms).
  const catFiltered = useMemo(
    () => data.crimes.filter((c) => passes(c, { cats, from: -Infinity, to: Infinity, clock, linkedOnly, seriesOnly, stations: new Set(), statuses: new Set() })),
    [data.crimes, cats, clock, linkedOnly, seriesOnly],
  );
  const visible = useMemo(() => (filter ? data.crimes.filter((c) => passes(c, filter)) : []),
    // filter is rebuilt each render from these values
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data.crimes, cats, win, clock, linkedOnly, seriesOnly]);

  const playhead = win?.[1] ?? 0;
  const recent = useMemo(() => visible.filter((c) => {
    const tier = pulseTier(c.t, playhead);
    return tier === "fast" || tier === "medium";
  }), [visible, playhead]);

  const dayBins = useMemo(() => {
    if (!data.extent) return [];
    const d0 = localDay(data.extent.min, OFFSET), d1 = localDay(data.extent.max, OFFSET);
    const raw = binDaily(catFiltered.map((c) => c.t), d0, d1, OFFSET);
    const target = 180; // keep the bar count readable
    if (raw.length <= target) return raw;
    const k = Math.ceil(raw.length / target);
    return Array.from({ length: Math.ceil(raw.length / k) }, (_, i) => raw.slice(i * k, i * k + k).reduce((a, b) => a + b, 0));
  }, [catFiltered, data.extent]);

  const hourBins = useMemo(() => binHours(
    data.crimes.filter((c) => win && passes(c, { cats, from: win[0], to: win[1], clock: null, linkedOnly, seriesOnly, stations: new Set(), statuses: new Set() })).map((c) => c.mod),
  ), [data.crimes, cats, win, linkedOnly, seriesOnly]);

  const visibleIds = useMemo(() => new Set(visible.map((c) => c.id)), [visible]);

  // ---------- arcs ----------
  const arcs = useMemo(() => {
    const out: { id: string; path: LonLat[]; ts: number[]; score: number; status: string }[] = [];
    for (const a of data.links.alerts) {
      if (a.score < minScore) continue;
      if (a.status === "rejected" && !toggles.rejected) continue;
      // pair alerts link two crimes; series alerts are drawn as consecutive pairs in time order
      const ids = [...a.crimes].sort((x, y) => (data.links.points[x]?.t ?? 0) - (data.links.points[y]?.t ?? 0));
      for (let i = 0; i + 1 < ids.length; i++) {
        if (!visibleIds.has(ids[i]) && !visibleIds.has(ids[i + 1])) continue;
        const p = pointOf(data.links.points[ids[i]], byId, ids[i]);
        const q = pointOf(data.links.points[ids[i + 1]], byId, ids[i + 1]);
        if (!p || !q) continue;
        const { path, t } = arcPath(p, q);
        out.push({ id: `${a.id}:${i}`, path, ts: t, score: a.score, status: a.status });
      }
    }
    return out;
  }, [data.links, byId, visibleIds, minScore, toggles.rejected]);

  // ---------- series ----------
  const series = useMemo(() => data.links.series.map((s) => {
    const pts = s.members
      .map((id) => ({ id, p: pointOf(data.links.points[id], byId, id), t: data.links.points[id]?.t ?? byId.get(id)?.t ?? 0 }))
      .filter((x): x is { id: string; p: LonLat; t: number } => !!x.p)
      .sort((a, b) => a.t - b.t);
    const stations = new Set(s.members.map((id) => data.links.points[id]?.st).filter(Boolean));
    const hull = padRing(convexHull(pts.map((x) => x.p)), 0.004);
    const centre: LonLat | null = pts.length ? [pts.reduce((a, x) => a + x.p[0], 0) / pts.length, Math.max(...pts.map((x) => x.p[1])) + 0.006] : null;
    return { ...s, pts, hull, centre, label: `${s.name} · ${s.members.length} cases · ${stations.size} station${stations.size === 1 ? "" : "s"}` };
  }).filter((s) => s.pts.length > 0), [data.links, byId]);

  // ---------- hex heat (city-wide summary, H3 r8) ----------
  const hexCells = useMemo(() => {
    const m = new Map<string, number>();
    for (const [cell, cat, sub, , n] of data.hexes) if (cats.has(catKey(cat, sub))) m.set(cell, (m.get(cell) ?? 0) + n);
    return Array.from(m, ([cell, n]) => ({ cell, n }));
  }, [data.hexes, cats]);
  const hexMax = Math.max(1, ...hexCells.map((h) => h.n));

  const dim = constellation ? 0.25 : 1;
  const loopT = (now % 2400) / 2400; // travelling dash: one pass every 2.4 s

  const layers: Layer[] = [
    toggles.wards && data.boundaries && new GeoJsonLayer({
      id: "wards", data: data.boundaries.wards as never, stroked: true, filled: false,
      getLineColor: [150, 160, 175, 90], lineWidthMinPixels: 0.5,
    }),
    toggles.stations && data.boundaries && new GeoJsonLayer({
      id: "stations", data: data.boundaries.stations as never, stroked: true, filled: true,
      getFillColor: (f: { properties: { id?: string } }) => (f.properties.id === stationId ? [69, 194, 204, 25] : [0, 0, 0, 0]),
      getLineColor: [69, 194, 204, 140], lineWidthMinPixels: 1, pickable: false,
      updateTriggers: { getFillColor: [stationId] },
    }),
    toggles.hex && new H3HexagonLayer<{ cell: string; n: number }>({
      id: "hex", data: hexCells, getHexagon: (d) => d.cell, extruded: false, stroked: false, opacity: 0.55 * dim,
      getFillColor: (d) => { const k = d.n / hexMax; return [255, Math.round(200 - 150 * k), 60, Math.round(40 + 180 * k)]; },
      updateTriggers: { getFillColor: [hexMax] },
    }),
    toggles.hulls && new PolygonLayer<(typeof series)[number]>({
      id: "hull-glow", data: series.filter((s) => s.hull.length), getPolygon: (s) => s.hull, filled: true, stroked: true,
      getFillColor: [255, 214, 120, constellation ? 18 : 28], getLineColor: [255, 214, 120, 120], lineWidthMinPixels: 1.5,
    }),
    constellation && new PathLayer<(typeof series)[number]>({
      id: "constellation-lines", data: series, getPath: (s) => s.pts.map((x) => x.p), getColor: [255, 236, 190, 200],
      widthMinPixels: 1, capRounded: true, jointRounded: true,
    }),
    constellation && new ScatterplotLayer<{ p: LonLat }>({
      id: "constellation-stars", data: series.flatMap((s) => s.pts), getPosition: (x) => x.p, getRadius: 4, radiusUnits: "pixels",
      getFillColor: [255, 245, 220, 255],
    }),
    (toggles.hulls || constellation) && new TextLayer<(typeof series)[number]>({
      id: "series-labels", data: series.filter((s) => s.centre), getPosition: (s) => s.centre!, getText: (s) => s.label.toUpperCase(),
      getSize: 11, getColor: theme === "dark" ? [255, 236, 190, 230] : [90, 70, 20, 230], fontFamily: "ui-sans-serif, system-ui",
      characterSet: "auto", fontSettings: { sdf: true }, outlineWidth: 2, outlineColor: theme === "dark" ? [0, 0, 0, 200] : [255, 255, 255, 220],
    }),
    toggles.arcs && toggles.rejected && new PathLayer<(typeof arcs)[number]>({
      id: "arcs-rejected", data: arcs.filter((a) => a.status === "rejected"), getPath: (a: { path: LonLat[] }) => a.path, getColor: [150, 150, 150, 160],
      getWidth: 1.5, widthUnits: "pixels", getDashArray: [4, 4], dashJustified: true, extensions: [new PathStyleExtension({ dash: true })],
    } as never),
    toggles.arcs && new PathLayer<(typeof arcs)[number]>({
      id: "arcs-base", data: arcs.filter((a) => a.status !== "rejected"), getPath: (a) => a.path,
      getColor: (a) => (a.status === "approved" ? [255, 255, 255, 120] : [255, 214, 120, 110]),
      getWidth: (a) => 1 + a.score * 3, widthUnits: "pixels",
    }),
    toggles.arcs && new TripsLayer<(typeof arcs)[number]>({
      id: "arcs-dash", data: arcs.filter((a) => a.status !== "rejected"), getPath: (a) => a.path, getTimestamps: (a) => a.ts,
      getColor: [255, 255, 255, 240], getWidth: (a) => 1.5 + a.score * 3, widthUnits: "pixels", trailLength: 0.25,
      currentTime: loopT * 1.25, capRounded: true, jointRounded: true,
    }),
    new ScatterplotLayer<MapCrime>({
      id: "crimes", data: visible, pickable: true, getPosition: (c) => c.pos,
      getRadius: (c) => 2.5 + c.sev * 1.3, radiusUnits: "pixels",
      getFillColor: (c) => [...CAT_COLOUR[c.cat], Math.round(220 * dim)] as [number, number, number, number],
      stroked: true, lineWidthUnits: "pixels",
      getLineWidth: (c) => (c.linked ? 1.5 : 0), getLineColor: [255, 255, 255, 230],
      updateTriggers: { getFillColor: [dim] },
    }),
    new ScatterplotLayer<MapCrime>({
      id: "pulses", data: recent, getPosition: (c) => c.pos, radiusUnits: "pixels", filled: false, stroked: true, lineWidthUnits: "pixels",
      getRadius: (c) => {
        const tier = pulseTier(c.t, playhead) as "fast" | "medium";
        return 4 + c.sev * 1.3 + pulsePhase(now, tier, c.t % 1000) * (tier === "fast" ? 16 : 10);
      },
      getLineWidth: 2,
      getLineColor: (c) => {
        const tier = pulseTier(c.t, playhead) as "fast" | "medium";
        return [...CAT_COLOUR[c.cat], Math.round(230 * (1 - pulsePhase(now, tier, c.t % 1000)) * dim)] as [number, number, number, number];
      },
      updateTriggers: { getRadius: [now, playhead], getLineColor: [now, playhead, dim] },
    }),
    toggles.glyphs && new TextLayer<MapCrime>({
      id: "glyphs", data: visible, getPosition: (c) => c.pos, getText: (c) => CAT_GLYPH[c.cat], getSize: 10,
      getColor: [255, 255, 255, 230], characterSet: Object.values(CAT_GLYPH),
    }),
  ].filter(Boolean) as Layer[];

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id === "crimes" && info.object) setSelected(info.object as MapCrime);
  };

  const flip = (k: keyof Toggles) => setToggles((t) => ({ ...t, [k]: !t[k] }));
  const loading = data.totalMonths > 0 && data.loadedMonths < data.totalMonths;

  return (
    <div className="relative h-[calc(100vh-9rem)] min-h-[560px] overflow-hidden rounded-xl border border-line bg-black">
      <MapCanvas view={{ center: CITY.map.center, zoom: CITY.map.zoom, bounds: CITY.map.bounds }} layers={layers} theme={theme} onClick={onClick} />

      {/* category chips */}
      <div className="absolute left-3 top-3 z-10 flex max-w-[60%] flex-wrap gap-1.5">
        {CAT_KEYS.map((k) => (
          <button
            key={k} aria-pressed={cats.has(k)}
            onClick={() => setCats((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; })}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium shadow ${cats.has(k) ? "bg-surface text-ink" : "bg-[color-mix(in_srgb,var(--surface)_50%,transparent)] text-muted line-through"}`}
          >
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: `rgb(${CAT_COLOUR[k].join(",")})` }} />
            <span aria-hidden>{CAT_GLYPH[k]}</span> {CAT_LABEL[k]}
          </button>
        ))}
      </div>

      {/* layers + filters */}
      <div className="absolute right-12 top-3 z-10 w-56 space-y-3 rounded-xl bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] p-3 text-xs shadow-lg backdrop-blur">
        <div>
          <p className="mb-1 font-semibold uppercase tracking-wider text-muted">Layers</p>
          {([
            ["arcs", "Link arcs"], ["hulls", "Series hulls"], ["hex", "Hex heat (city-wide)"], ["stations", "Station boundaries"],
            ["wards", "Wards"], ["rejected", "Show rejected links"], ["glyphs", "Shape glyphs"],
          ] as [keyof Toggles, string][]).map(([k, label]) => (
            <label key={k} className="flex cursor-pointer items-center gap-2 py-0.5">
              <input type="checkbox" checked={toggles[k]} onChange={() => flip(k)} /> {label}
            </label>
          ))}
          <p className="mt-1 text-[11px] leading-snug text-muted">CCTV cones, ANPR, tips, 112 calls and release density arrive with the next data slice.</p>
        </div>
        <div>
          <p className="mb-1 font-semibold uppercase tracking-wider text-muted">Filters</p>
          <label className="flex items-center gap-2 py-0.5"><input type="checkbox" checked={linkedOnly} onChange={() => setLinkedOnly((v) => !v)} /> Linked only</label>
          <label className="flex items-center gap-2 py-0.5"><input type="checkbox" checked={seriesOnly} onChange={() => setSeriesOnly((v) => !v)} /> In a series</label>
          <label className="block py-0.5">
            Arc score ≥ <span className="font-mono">{minScore.toFixed(2)}</span>
            <input type="range" min={0.55} max={1} step={0.01} value={minScore} onChange={(e) => setMinScore(+e.target.value)} className="w-full" />
          </label>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setConstellation((v) => !v)} aria-pressed={constellation}
            className={`flex-1 rounded-md px-2 py-1 ${constellation ? "bg-accent text-white" : "border border-line"}`}>Constellation</button>
          <button onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} className="rounded-md border border-line px-2 py-1">
            {theme === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </div>

      {/* status line */}
      <div className="absolute left-3 top-14 z-10 rounded-md bg-[color-mix(in_srgb,var(--surface)_85%,transparent)] px-2 py-1 text-xs shadow backdrop-blur">
        {data.error ? <span className="text-red-600">Map data error: {data.error}</span>
          : !data.extent && data.totalMonths === 0 && data.loadedMonths === 0 && data.crimes.length === 0
            ? <span className="text-muted">No crimes visible to your role yet.</span>
            : <span>
                <strong>{visible.length.toLocaleString()}</strong> of {data.crimes.length.toLocaleString()} crimes · {arcs.length} arcs · {series.length} series
                {loading && <span className="text-muted"> · loading month {data.loadedMonths + 1}/{data.totalMonths}</span>}
                {role === "station_officer" && <span className="text-muted"> · other stations shown by area cell</span>}
              </span>}
      </div>

      {/* clock dial */}
      <div className="absolute bottom-28 right-3 z-10">
        <ClockDial arc={clock} onChange={setClock} hours={hourBins} />
      </div>

      {/* scrubber */}
      {data.extent && win && (
        <div className="absolute inset-x-3 bottom-3 z-10">
          <TimeScrubber
            min={data.extent.min} max={data.extent.max} from={win[0]} to={win[1]} bins={dayBins} playing={playing}
            onWindow={(f, t) => { setPlaying(false); setWin([f, t]); }} onPlay={togglePlay} speedMsPerDay={SPEED_MS_PER_DAY}
          />
        </div>
      )}

      {selected && <CrimeDrawer crime={selected} links={data.links} byId={byId} onClose={() => setSelected(null)} />}
    </div>
  );
}

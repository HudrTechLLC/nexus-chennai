"use client";
import { useEffect, useState } from "react";
import { consoleBrowserClient } from "@/lib/supabase/browser";
import { CITY } from "@/lib/city";
import { decodeCrimes, monthWindows, type MapCrime, type MapCrimeCols } from "@/lib/pulse";

export type LinkAlertLite = { id: string; kind: string; crimes: string[]; score: number; band: string; status: string };
export type SeriesLite = { id: string; name: string; status: string; members: string[] };
export type LinkPoint = { lon: number | null; lat: number | null; t: number | null; cell: string | null; week: string | null; st: string | null; cat: string | null };
export type Links = { alerts: LinkAlertLite[]; series: SeriesLite[]; points: Record<string, LinkPoint> };
export type HexRow = [string, string, string | null, string, number]; // cell, category, sub_type, week, n
export type FeatureCollection = { type: "FeatureCollection"; features: { type: "Feature"; properties: Record<string, unknown>; geometry: unknown }[] };

export type PulseData = {
  crimes: MapCrime[];
  extent: { min: number; max: number; n: number } | null;
  loadedMonths: number;
  totalMonths: number;
  links: Links;
  hexes: HexRow[];
  boundaries: { stations: FeatureCollection; wards: FeatureCollection } | null;
  error: string | null;
};

const EMPTY_LINKS: Links = { alerts: [], series: [], points: {} };

/**
 * Loads the Pulse Map data through the 0004_02 RPCs as the signed-in officer (RLS applies).
 * Crimes arrive month by month, newest first, so the map paints quickly.
 */
export function usePulseData(): PulseData {
  const [state, setState] = useState<PulseData>({
    crimes: [], extent: null, loadedMonths: 0, totalMonths: 0, links: EMPTY_LINKS, hexes: [], boundaries: null, error: null,
  });

  useEffect(() => {
    let cancelled = false;
    const sb = consoleBrowserClient();
    const fail = (e: { message: string } | null) => {
      if (e && !cancelled) setState((s) => ({ ...s, error: e.message }));
    };

    (async () => {
      const [ext, links, hexes, bounds] = await Promise.all([
        sb.rpc("map_extent"), sb.rpc("map_links"), sb.rpc("map_hexes", {}), sb.rpc("map_boundaries"),
      ]);
      if (cancelled) return;
      fail(ext.error ?? links.error ?? hexes.error ?? bounds.error);
      const extent = ext.data && ext.data.n > 0 ? (ext.data as PulseData["extent"]) : null;
      const windows = extent ? monthWindows(extent.min, extent.max) : [];
      setState((s) => ({
        ...s, extent, totalMonths: windows.length,
        links: (links.data as Links) ?? EMPTY_LINKS,
        hexes: (hexes.data as HexRow[]) ?? [],
        boundaries: (bounds.data as PulseData["boundaries"]) ?? null,
      }));
      for (const [from, to] of windows) {
        const { data, error } = await sb.rpc("map_crimes", {
          p_from: new Date(from).toISOString(), p_to: new Date(to).toISOString(), p_tz: CITY.timezone,
        });
        if (cancelled) return;
        if (error) return fail(error);
        const batch = decodeCrimes(data as MapCrimeCols);
        setState((s) => ({ ...s, crimes: s.crimes.concat(batch), loadedMonths: s.loadedMonths + 1 }));
      }
    })().catch((e) => fail(e instanceof Error ? e : { message: String(e) }));

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

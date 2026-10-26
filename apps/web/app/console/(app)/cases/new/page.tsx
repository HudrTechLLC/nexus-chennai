import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { stationOptions } from "@/lib/casesData";
import { FirFormView, type SectionOption } from "../_components/FirForm";

export const dynamic = "force-dynamic";

/** Spec G4 FIR capture form. Station officers file for their own station; admin picks a station. */
export default async function NewFirPage() {
  const officer = await requireOfficer(["station_officer", "admin"]);
  const sb = consoleServerClient();
  const [{ data: sections }, stations] = await Promise.all([
    sb.from("section_map").select("ipc_code, bns_code, title, category_group").order("bns_code"),
    officer.role === "admin" ? stationOptions(sb) : Promise.resolve([]),
  ]);
  const own = officer.stationId ? (await stationOptions(sb)).find((s) => s.station_id === officer.stationId) : undefined;
  // Open the map on the officer's own station (centroid is GeoJSON from PostGIS).
  const { data: st } = officer.stationId
    ? await sb.from("stations").select("centroid").eq("station_id", officer.stationId).maybeSingle()
    : { data: null };
  const c = (st?.centroid as { coordinates?: [number, number] } | null)?.coordinates;
  const home: [number, number] | null = c && Number.isFinite(c[0]) && Number.isFinite(c[1]) ? [c[0], c[1]] : null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">File a new FIR</h1>
        <p className="text-sm text-muted">
          {own ? `Filing for ${own.name}. ` : ""}Saving registers the case at once. The local pipeline then extracts the MO from the narrative and
          statements, and checks for links to other cases; the case file shows the result and the run trace.
        </p>
      </div>
      <FirFormView sections={(sections ?? []) as SectionOption[]} stations={stations} ownStationId={officer.stationId} isAdmin={officer.role === "admin"} home={home} />
    </div>
  );
}

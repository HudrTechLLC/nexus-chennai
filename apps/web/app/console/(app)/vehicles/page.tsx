import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { humanise, plateIlike, plateMatches } from "@/lib/cases";
import { VEHICLE_TYPES, groupVehicles, hasVehicleFilter, parseVehicleFilters, readsPerPlate, type VehicleRow } from "@/lib/vehicles";

export const dynamic = "force-dynamic";

/** PostgREST returns at most this many rows per request; the page says so when a list reaches it. */
const ROW_CAP = 1000;
const SHOW = 100;
const input = "rounded-md border border-line bg-bg px-2 py-1.5 text-sm";

/**
 * Vehicles register (CAP-06): every vehicle recorded on a case you may open, grouped by plate, with its
 * cases and ANPR sightings. Read-only; vehicles are added on the FIR form.
 */
export default async function VehiclesPage({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  const officer = await requireOfficer();
  const sb = consoleServerClient();
  const f = parseVehicleFilters(searchParams);

  let q = sb.from("crime_vehicles").select("crime_id, plate_pattern, vehicle_type, make_model, colour, role");
  if (f.plate) q = q.ilike("plate_pattern", plateIlike(f.plate));
  else if (!hasVehicleFilter(f)) q = q.not("plate_pattern", "is", null); // the unfiltered view lists plated vehicles
  if (f.type) q = q.eq("vehicle_type", f.type);
  if (f.make) q = q.ilike("make_model", `%${f.make}%`);
  if (f.colour) q = q.ilike("colour", `%${f.colour}%`);
  const { data, error } = await q.limit(ROW_CAP);
  const rows = ((data ?? []) as VehicleRow[]).filter((r) => !f.plate || plateMatches(r.plate_pattern, f.plate));
  const groups = groupVehicles(rows);
  const shown = groups.slice(0, SHOW);

  const fullPlates = shown.map((g) => g.plate).filter((p): p is string => !!p && !p.includes("?"));
  const reads = fullPlates.length
    ? await sb.from("map_anpr_reads").select("plate_text").in("plate_text", fullPlates).limit(ROW_CAP)
    : { data: [], error: null };
  const sightings = readsPerPlate((reads.data ?? []) as { plate_text: string }[]);
  const scope = officer.role === "station_officer" ? "cases your station may open" : "all cases";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Vehicles</h1>
        <p className="text-sm text-muted">
          Vehicles recorded on {scope}, grouped by plate. A plate on several cases is one entry with all its cases. A
          partial plate (<span className="font-mono">?</span> = unread character) shared by several cases is a lead, not proof
          that it is the same vehicle. Vehicles are added on the FIR form.
        </p>
      </div>

      <form className="flex flex-wrap items-end gap-2 rounded-xl border border-line bg-surface p-4" method="get">
        <label className="text-sm"><span className="mb-1 block text-muted">Plate (use ? for unknown)</span>
          <input name="plate" defaultValue={f.plate ?? ""} placeholder="TN 09 ?? 4471" className={`${input} w-40 font-mono`} /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">Type</span>
          <select name="type" defaultValue={f.type ?? ""} className={input}>
            <option value="">Any</option>
            {VEHICLE_TYPES.map((t) => <option key={t} value={t}>{humanise(t)}</option>)}
          </select></label>
        <label className="text-sm"><span className="mb-1 block text-muted">Make / model</span>
          <input name="make" defaultValue={f.make ?? ""} placeholder="pulsar" className={`${input} w-32`} /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">Colour</span>
          <input name="colour" defaultValue={f.colour ?? ""} placeholder="red" className={`${input} w-28`} /></label>
        <button className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white">Filter</button>
        {hasVehicleFilter(f) && <Link href="/console/vehicles" className="text-sm text-muted hover:underline">Clear</Link>}
      </form>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">
          {groups.length.toLocaleString("en-IN")} vehicle{groups.length === 1 ? "" : "s"}
          {groups.length > SHOW && <span className="text-sm font-normal text-muted"> · showing the {SHOW} on most cases</span>}
        </h2>
        {error && <p role="alert" className="text-sm text-red-600">Could not load vehicles: {error.message}</p>}
        {!error && groups.length === 0 && <p className="text-sm text-muted">No vehicles match.</p>}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1">Plate</th><th>Vehicle</th><th>Role</th><th>Cases</th><th>ANPR</th></tr>
            </thead>
            <tbody>
              {shown.map((g, i) => (
                <tr key={`${g.plate ?? "unread"}-${i}`} className="border-t border-line align-top">
                  <td className="py-1.5 font-mono">{g.plate ?? <span className="text-muted">unread</span>}</td>
                  <td>{[g.colour, g.make_model, humanise(g.vehicle_type)].filter(Boolean).join(" ")}</td>
                  <td className="text-xs">{g.roles.map(humanise).join(", ")}</td>
                  <td className="text-xs">
                    {g.crimes.slice(0, 6).map((c) => (
                      <Link key={c} href={`/console/cases/${encodeURIComponent(c)}`} className="mr-2 font-mono text-signal hover:underline">{c}</Link>
                    ))}
                    {g.crimes.length > 6 && <span className="text-muted">+{g.crimes.length - 6} more</span>}
                  </td>
                  <td className="text-xs">
                    {g.plate && !g.plate.includes("?") && sightings.get(g.plate)
                      ? <Link href={`/console/search?q=${encodeURIComponent(g.plate)}`} className="text-signal hover:underline">{sightings.get(g.plate)} read{sightings.get(g.plate) === 1 ? "" : "s"}</Link>
                      : <span className="text-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(data?.length ?? 0) >= ROW_CAP && <p className="mt-2 text-xs text-muted">The first 1,000 vehicle records were read; add a filter to narrow it.</p>}
        <p className="mt-2 text-xs text-muted">Sources: crime_vehicles (under your role&apos;s row-level security) and map_anpr_reads.</p>
      </section>
    </div>
  );
}

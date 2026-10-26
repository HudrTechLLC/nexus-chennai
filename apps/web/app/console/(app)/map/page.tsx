import { requireOfficer } from "@/lib/auth";
import { PulseMapLoader } from "@/components/console/map/PulseMapLoader";
import { consoleCell, consoleCrimeId } from "@/lib/consoleArea";

export const dynamic = "force-dynamic";

/** ?cell=<h3 r8-r10> frames and highlights a tip's area; ?crime=<id> flies to a crime and opens its drawer
 * (WS3-24, from the tip detail page). Invalid values are ignored, and the map opens as usual. */
export default async function PulseMapPage({ searchParams }: { searchParams: { cell?: string | string[]; crime?: string | string[] } }) {
  const officer = await requireOfficer("all");
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  return (
    <PulseMapLoader stationId={officer.stationId} role={officer.role}
      focusCell={consoleCell(one(searchParams.cell))} focusCrime={consoleCrimeId(one(searchParams.crime))} />
  );
}

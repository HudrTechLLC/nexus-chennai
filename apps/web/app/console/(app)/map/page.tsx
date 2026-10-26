import { requireOfficer } from "@/lib/auth";
import { PulseMapLoader } from "@/components/console/map/PulseMapLoader";

export const dynamic = "force-dynamic";

export default async function PulseMapPage() {
  const officer = await requireOfficer("all");
  return <PulseMapLoader stationId={officer.stationId} role={officer.role} />;
}

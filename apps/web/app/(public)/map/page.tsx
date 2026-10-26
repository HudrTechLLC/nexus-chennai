import { PublicMapView } from "@/components/public/PublicMapView";
import { getPublicMap } from "@/lib/publicData";

export const revalidate = 300;
export const metadata = { title: "Crime map · Nexus Chennai" };

export default async function PublicMapPage({ searchParams }: { searchParams: { days?: string } }) {
  const days = [7, 30, 90].includes(Number(searchParams.days)) ? Number(searchParams.days) : 30;
  const { map, error } = await getPublicMap(days);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold">See what&apos;s happening near you</h1>
        <p className="mt-1 max-w-prose text-muted">Reported crime by area. Locations are grouped into hexagons, never exact.</p>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {map && <PublicMapView map={map} days={days} />}
    </div>
  );
}

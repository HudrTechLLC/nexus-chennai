import { PublicMapView } from "@/components/public/PublicMapView";
import { HexPanel } from "@/components/public/HexPanel";
import { getHexCrimes, getPublicMap } from "@/lib/publicData";
import { parseMapState } from "@/lib/publicCards";

export const revalidate = 300;
export const metadata = { title: "Crime map · Nexus Chennai" };

export default async function PublicMapPage({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  const state = parseMapState(searchParams);
  const [{ map, error }, hexRes] = await Promise.all([
    getPublicMap(state.days),
    state.hex ? getHexCrimes(state.hex, state.days, state.type) : Promise.resolve(null),
  ]);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold">See what&apos;s happening near you</h1>
        <p className="mt-1 max-w-prose text-muted">Reported crime by area. Locations are grouped into hexagons, never exact.</p>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {map && (
        <PublicMapView
          map={map}
          state={state}
          panel={hexRes && <HexPanel state={state} hex={hexRes.hex} error={hexRes.error} minCount={map.min_count} />}
        />
      )}
    </div>
  );
}

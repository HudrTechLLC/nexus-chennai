import city from "./city.generated.json";

/** City pack settings (cities/<CITY>/city.yaml via scripts/sync-city.mjs; D-004). */
export const CITY = city as {
  name: string;
  slug: string;
  timezone: string;
  map: { center: [number, number]; bounds: [number, number, number, number]; zoom: number };
  h3: { internal: number; public: number; publicMinCount: number };
  synthetic: boolean;
};

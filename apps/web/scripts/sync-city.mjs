// Build-time copy of the city pack settings the web app needs (DECISIONS D-004: nothing
// city-specific in code). Reads cities/<CITY>/city.yaml (CITY defaults to chennai) and writes
// lib/city.generated.json, which is gitignored and regenerated before dev, build, typecheck and test.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, "..");
const city = process.env.CITY || process.env.NEXT_PUBLIC_CITY || "chennai";
const src = path.resolve(web, "../../cities", city, "city.yaml");
if (!fs.existsSync(src)) {
  console.error(`sync-city: ${src} not found`);
  process.exit(1);
}
const y = parse(fs.readFileSync(src, "utf8"));
const out = {
  name: y.name,
  slug: y.slug,
  timezone: y.timezone,
  map: { center: y.map.center, bounds: y.map.bounds, zoom: y.map.default_zoom },
  h3: { internal: y.h3.internal_resolution, public: y.h3.public_resolution, publicMinCount: y.h3.public_min_count },
  synthetic: !!y.synthetic,
};
fs.writeFileSync(path.join(web, "lib", "city.generated.json"), JSON.stringify(out, null, 2) + "\n");
console.log(`sync-city: ${out.name} (${out.timezone})`);

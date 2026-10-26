import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { fetchGraph, suggestEntities } from "@/lib/memoryData";
import { ENTITY_TYPES, parseHops, parseTypes, sourcesOf, TYPE_COLOUR, TYPE_LABEL } from "@/lib/worldGraph";
import { GraphExplorer } from "@/components/console/graph/GraphExplorer";

export const dynamic = "force-dynamic";

export default async function GraphPage({ searchParams }: { searchParams: { seed?: string; hops?: string; types?: string | string[] } }) {
  await requireOfficer("analyst+");
  const seed = searchParams.seed?.trim() || null;
  const hops = parseHops(searchParams.hops);
  // The type checkboxes submit repeated `types=` params; links use one comma list. Accept both.
  const types = parseTypes(Array.isArray(searchParams.types) ? searchParams.types.join(",") : searchParams.types);
  const sb = consoleServerClient();
  const { graph, error } = await fetchGraph(sb, { seed, hops, types });
  const suggestions = seed && !graph.found ? await suggestEntities(sb, seed) : [];
  // Seed nodes: what the seed matched (the RPC puts them first; recover them by id/key match).
  const norm = (v: string) => v.replace(/\s/g, "").toUpperCase();
  const seedIds = seed
    ? graph.nodes.filter((n) => n.id === seed || n.key === seed || n.aliases.includes(seed) || norm(n.key) === norm(seed)).map((n) => n.id)
    : [];

  const keep = new URLSearchParams();
  if (hops !== 1) keep.set("hops", String(hops));
  if (types) keep.set("types", types.join(","));
  const sources = sourcesOf(graph.provenance);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Case graph</h1>
        <p className="max-w-prose text-sm text-muted">
          The World Model: one entity for each real-world thing (case, person, vehicle, place, phone, evidence, series) that every agent
          reads and writes, with the provenance of each fact. Start from a case id, a plate, a phone or a name, or browse the most-connected entities.
        </p>
      </div>

      <form method="get" className="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4 text-sm">
        <label className="flex min-w-[16rem] flex-1 flex-col gap-1">
          <span className="text-xs text-muted">Start from</span>
          <input name="seed" defaultValue={seed ?? ""} placeholder="CHN-AD-2026-001182, TN09AB4471, entity id…"
            className="rounded-md border border-line bg-bg px-3 py-1.5 font-mono text-sm" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Depth</span>
          <select name="hops" defaultValue={String(hops)} className="rounded-md border border-line bg-bg px-2 py-1.5">
            {[0, 1, 2, 3].map((h) => <option key={h} value={h}>{h === 0 ? "Only matches" : `${h} hop${h === 1 ? "" : "s"}`}</option>)}
          </select>
        </label>
        <fieldset className="flex flex-wrap gap-2">
          <legend className="mb-1 text-xs text-muted">Types (none = all)</legend>
          {ENTITY_TYPES.map((t) => (
            <label key={t} className="inline-flex items-center gap-1 text-xs">
              <input type="checkbox" name="types" value={t} defaultChecked={types?.includes(t) ?? false} />
              <span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLOUR[t] }} />{TYPE_LABEL[t]}
            </label>
          ))}
        </fieldset>
        <button className="rounded-md bg-signal px-3 py-1.5 font-medium text-white">Show</button>
        {(seed || types || hops !== 1) && <Link href="/console/graph" className="text-xs text-muted hover:text-ink">Reset</Link>}
      </form>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load the graph: {error}</p>}

      <p className="text-xs text-muted">
        {graph.totals.entities} entities and {graph.totals.edges} relations in the World Model
        {Object.keys(graph.totals.by_type).length > 0 && <> ({Object.entries(graph.totals.by_type).map(([t, n]) => `${n} ${TYPE_LABEL[t as keyof typeof TYPE_LABEL]?.toLowerCase() ?? t}`).join(", ")})</>}
        {" "}· showing {graph.nodes.length} entities, {graph.edges.length} relations
        {graph.truncated && <> · capped at {graph.limit}; narrow by type or depth</>}
        {sources.length > 0 && <> · sources: {sources.join(", ")}</>}
      </p>

      {seed && !graph.found ? (
        <div className="rounded-xl border border-dashed border-line p-6 text-sm">
          <p className="text-muted">No entity matches <span className="font-mono">{seed}</span>.</p>
          {suggestions.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <li key={s.id}>
                  <Link href={`/console/graph?seed=${encodeURIComponent(s.id)}${keep.toString() ? `&${keep}` : ""}`} className="rounded-md border border-line px-2 py-0.5 font-mono text-xs hover:border-signal">
                    {TYPE_LABEL[s.type]} · {s.key}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : graph.nodes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
          {graph.totals.entities === 0
            ? "The World Model is empty. Agents add entities as they extract and link cases; they appear here after the next pipeline run."
            : "No entities of the chosen types."}
        </p>
      ) : (
        <GraphExplorer nodes={graph.nodes} edges={graph.edges} provenance={graph.provenance} seedIds={seedIds} qs={keep.toString()} />
      )}
    </div>
  );
}


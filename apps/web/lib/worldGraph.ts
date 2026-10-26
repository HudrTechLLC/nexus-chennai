/**
 * World Model graph as the console reads it (spec E4, G2 /console/graph; tables from 0005, D-020).
 * Types for the wm_graph() payload (0004_06_02) plus pure helpers: labels, provenance lookup and a
 * small deterministic force layout (no extra dependency; same input → same picture).
 */

// =====================
// Types
// =====================

export const ENTITY_TYPES = ["crime", "person", "vehicle", "place", "phone", "evidence", "series"] as const;
export type EntityType = (typeof ENTITY_TYPES)[number];

export const EDGE_TYPES = ["involves", "used_vehicle", "seen_at", "described_as", "linked_to", "member_of"] as const;
export type EdgeType = (typeof EDGE_TYPES)[number];

export type GraphNode = {
  id: string;
  type: EntityType;
  key: string;
  attrs: Record<string, unknown>;
  aliases: string[];
  synthetic: boolean;
  created_at: string;
  updated_at: string;
  degree: number; // across the whole graph the officer may read, not just this view
};

export type GraphEdge = { id: string; from: string; to: string; type: EdgeType; crime_id: string | null; synthetic: boolean; created_at: string };

export type Provenance = { subject: string; source: string; n: number; first: string; last: string };

export type GraphPayload = {
  seed: string | null;
  found: boolean;
  hops: number;
  limit: number;
  truncated: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  provenance: Provenance[];
  totals: { entities: number; edges: number; by_type: Partial<Record<EntityType, number>> };
};

export const EMPTY_GRAPH: GraphPayload = {
  seed: null, found: true, hops: 1, limit: 200, truncated: false, nodes: [], edges: [], provenance: [],
  totals: { entities: 0, edges: 0, by_type: {} },
};

export const TYPE_LABEL: Record<EntityType, string> = {
  crime: "Case", person: "Person", vehicle: "Vehicle", place: "Place", phone: "Phone", evidence: "Evidence", series: "Series",
};

/** Node fill per type (CSS colours that read on both themes). */
export const TYPE_COLOUR: Record<EntityType, string> = {
  crime: "#0e7c86", person: "#b4533c", vehicle: "#8a6a2f", place: "#5b7c3a", phone: "#6b5fa8", evidence: "#4f6d8f", series: "#c0392b",
};

export const EDGE_LABEL: Record<EdgeType, string> = {
  involves: "involves", used_vehicle: "used vehicle", seen_at: "seen at", described_as: "described as", linked_to: "linked to", member_of: "member of",
};

export function isEntityType(v: unknown): v is EntityType {
  return typeof v === "string" && (ENTITY_TYPES as readonly string[]).includes(v);
}

// =====================
// Labels and lookups
// =====================

/** Short on-graph label: the canonical key, shortened per type. */
export function nodeLabel(n: Pick<GraphNode, "type" | "key">): string {
  const k = n.key ?? "";
  if (n.type === "crime") return k.replace(/^CHN-/, "");
  if (n.type === "place") return k.length > 10 ? `cell …${k.slice(-6)}` : k;
  if (n.type === "phone") return k.length > 4 ? `…${k.slice(-4)}` : k; // masked (spec J5)
  return k.length > 22 ? `${k.slice(0, 21)}…` : k;
}

/** Provenance rows for one subject (entity or edge id), most observations first. */
export function provenanceFor(rows: Provenance[], subject: string): Provenance[] {
  return rows.filter((p) => p.subject === subject).sort((a, b) => b.n - a.n || a.source.localeCompare(b.source));
}

/** Distinct sources across the view, for the legend and the source filter. */
export function sourcesOf(rows: Provenance[]): string[] {
  return Array.from(new Set(rows.map((p) => p.source))).sort();
}

/** Edges touching a node, with the node at the other end. */
export function neighbours(nodeId: string, edges: GraphEdge[]): { edge: GraphEdge; other: string; out: boolean }[] {
  const out: { edge: GraphEdge; other: string; out: boolean }[] = [];
  for (const e of edges) {
    if (e.from === nodeId) out.push({ edge: e, other: e.to, out: true });
    else if (e.to === nodeId) out.push({ edge: e, other: e.from, out: false });
  }
  return out;
}

/** Keeps only nodes whose type is selected (and edges between kept nodes). Seed nodes always stay. */
export function filterGraph(g: Pick<GraphPayload, "nodes" | "edges">, types: EntityType[] | null, keep: string[] = []): { nodes: GraphNode[]; edges: GraphEdge[] } {
  if (!types || types.length === 0) return { nodes: g.nodes, edges: g.edges };
  const nodes = g.nodes.filter((n) => types.includes(n.type) || keep.includes(n.id));
  const ids = new Set(nodes.map((n) => n.id));
  return { nodes, edges: g.edges.filter((e) => ids.has(e.from) && ids.has(e.to)) };
}

/** Parses ?types=crime,vehicle. Unknown values are dropped; empty → null (all types). */
export function parseTypes(raw: string | undefined): EntityType[] | null {
  if (!raw) return null;
  const t = raw.split(",").filter(isEntityType);
  return t.length ? t : null;
}

/** Clamps ?hops to 0..3 (default 1). */
export function parseHops(raw: string | undefined): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 && n <= 3 ? n : 1;
}

// =====================
// Layout
// =====================

export type Positioned = { id: string; x: number; y: number };

/** Mulberry32: tiny seeded PRNG so a layout is reproducible. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/**
 * Fruchterman–Reingold layout in a w×h box. Deterministic for the same nodes and edges
 * (start positions come from a hash of the node ids). O(n² · iterations); the RPC caps n at 600
 * and the page asks for ~200, so this stays well under a frame budget per iteration.
 */
export function forceLayout(
  nodeIds: string[], edges: { from: string; to: string }[],
  opts: { width?: number; height?: number; iterations?: number; pin?: string | null } = {},
): Positioned[] {
  const W = opts.width ?? 1000;
  const H = opts.height ?? 640;
  const n = nodeIds.length;
  if (n === 0) return [];
  if (n === 1) return [{ id: nodeIds[0], x: W / 2, y: H / 2 }];
  const ids = nodeIds.slice().sort();
  const index = new Map(ids.map((id, i) => [id, i]));
  const rand = rng(hash(ids.join("|")));
  const xs = ids.map(() => W * (0.1 + 0.8 * rand()));
  const ys = ids.map(() => H * (0.1 + 0.8 * rand()));
  const pin = opts.pin != null ? index.get(opts.pin) : undefined;
  if (pin != null) { xs[pin] = W / 2; ys[pin] = H / 2; }

  const links = edges.map((e) => [index.get(e.from), index.get(e.to)] as const)
    .filter((p): p is readonly [number, number] => p[0] != null && p[1] != null && p[0] !== p[1]);
  const k = Math.sqrt((W * H) / n) * 0.75;
  const iters = opts.iterations ?? Math.min(300, 60 + Math.round(30000 / n));
  let temp = Math.max(W, H) / 10;
  const cool = temp / (iters + 1);
  const dx = new Float64Array(n);
  const dy = new Float64Array(n);

  for (let it = 0; it < iters; it++) {
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ddx = xs[i] - xs[j];
        let ddy = ys[i] - ys[j];
        let d2 = ddx * ddx + ddy * ddy;
        if (d2 < 0.01) { ddx = (i - j) * 0.1; ddy = 0.1; d2 = ddx * ddx + ddy * ddy; }
        const f = (k * k) / d2; // repulsion k²/d, applied along the unit vector (ddx/d)
        dx[i] += ddx * f; dy[i] += ddy * f;
        dx[j] -= ddx * f; dy[j] -= ddy * f;
      }
    }
    for (const [a, b] of links) {
      const ddx = xs[a] - xs[b];
      const ddy = ys[a] - ys[b];
      const d = Math.sqrt(ddx * ddx + ddy * ddy) || 0.01;
      const f = d / k; // attraction d²/k along the unit vector
      dx[a] -= ddx * f; dy[a] -= ddy * f;
      dx[b] += ddx * f; dy[b] += ddy * f;
    }
    for (let i = 0; i < n; i++) {
      if (i === pin) continue;
      // gentle pull to the centre keeps disconnected pieces on screen
      dx[i] += (W / 2 - xs[i]) * 0.01 * k;
      dy[i] += (H / 2 - ys[i]) * 0.01 * k;
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const step = Math.min(d, temp);
      xs[i] = Math.min(W - 20, Math.max(20, xs[i] + (dx[i] / d) * step));
      ys[i] = Math.min(H - 20, Math.max(20, ys[i] + (dy[i] / d) * step));
    }
    temp = Math.max(1, temp - cool);
  }
  return ids.map((id, i) => ({ id, x: Math.round(xs[i] * 10) / 10, y: Math.round(ys[i] * 10) / 10 }));
}

/** Node radius from its degree (5..16 px). */
export function nodeRadius(degree: number): number {
  return Math.round(Math.min(16, 5 + Math.sqrt(Math.max(0, degree)) * 2.2) * 10) / 10;
}

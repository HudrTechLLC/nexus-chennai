import { describe, expect, it } from "vitest";
import {
  filterGraph, forceLayout, neighbours, nodeLabel, nodeRadius, parseHops, parseTypes, provenanceFor, sourcesOf,
  type GraphEdge, type GraphNode, type Provenance,
} from "../worldGraph";

const node = (id: string, type: GraphNode["type"], key: string): GraphNode => ({
  id, type, key, attrs: {}, aliases: [], synthetic: true, created_at: "t", updated_at: "t", degree: 1,
});
const edge = (id: string, from: string, to: string, type: GraphEdge["type"] = "involves"): GraphEdge => ({
  id, from, to, type, crime_id: null, synthetic: true, created_at: "t",
});

const nodes = [
  node("crime:fir:CHN-AD-1", "crime", "CHN-AD-1"),
  node("crime:fir:CHN-VL-2", "crime", "CHN-VL-2"),
  node("vehicle:plate:TN09AB4471", "vehicle", "TN09AB4471"),
  node("ent_p", "person", "Ravi K"),
];
const edges = [
  edge("rel_1", "crime:fir:CHN-AD-1", "vehicle:plate:TN09AB4471", "used_vehicle"),
  edge("rel_2", "crime:fir:CHN-VL-2", "vehicle:plate:TN09AB4471", "used_vehicle"),
  edge("rel_3", "crime:fir:CHN-VL-2", "ent_p"),
];

describe("labels", () => {
  it("shortens per type and masks phones", () => {
    expect(nodeLabel({ type: "crime", key: "CHN-AD-2026-001182" })).toBe("AD-2026-001182");
    expect(nodeLabel({ type: "phone", key: "9876543210" })).toBe("…3210");
    expect(nodeLabel({ type: "place", key: "88618c4f43fffff" })).toBe("cell …3fffff");
    expect(nodeLabel({ type: "person", key: "A very long person name indeed" })).toHaveLength(22);
  });
  it("sizes nodes by degree within bounds", () => {
    expect(nodeRadius(0)).toBe(5);
    expect(nodeRadius(1000)).toBe(16);
  });
});

describe("provenance and neighbours", () => {
  const prov: Provenance[] = [
    { subject: "vehicle:plate:TN09AB4471", source: "anpr_feed", n: 1, first: "a", last: "b" },
    { subject: "vehicle:plate:TN09AB4471", source: "Extractor", n: 3, first: "a", last: "b" },
    { subject: "rel_1", source: "Linker", n: 1, first: "a", last: "b" },
  ];
  it("lists who asserted a subject, most observations first", () => {
    expect(provenanceFor(prov, "vehicle:plate:TN09AB4471").map((p) => p.source)).toEqual(["Extractor", "anpr_feed"]);
    expect(provenanceFor(prov, "nobody")).toEqual([]);
    expect(sourcesOf(prov)).toEqual(["Extractor", "Linker", "anpr_feed"]);
  });
  it("finds both directions of edges", () => {
    const n = neighbours("vehicle:plate:TN09AB4471", edges);
    expect(n.map((x) => x.other).sort()).toEqual(["crime:fir:CHN-AD-1", "crime:fir:CHN-VL-2"]);
    expect(n.every((x) => !x.out)).toBe(true);
  });
});

describe("filters", () => {
  it("keeps selected types and the seed, and drops dangling edges", () => {
    const f = filterGraph({ nodes, edges }, ["crime"], ["vehicle:plate:TN09AB4471"]);
    expect(f.nodes).toHaveLength(3);
    expect(f.edges.map((e) => e.id)).toEqual(["rel_1", "rel_2"]);
    expect(filterGraph({ nodes, edges }, null).nodes).toHaveLength(4);
  });
  it("parses URL filters", () => {
    expect(parseTypes("crime,vehicle,bogus")).toEqual(["crime", "vehicle"]);
    expect(parseTypes("bogus")).toBeNull();
    expect(parseTypes(undefined)).toBeNull();
    expect(parseHops("2")).toBe(2);
    expect(parseHops("9")).toBe(1);
    expect(parseHops(undefined)).toBe(1);
  });
});

describe("forceLayout", () => {
  const ids = nodes.map((n) => n.id);
  it("is deterministic and keeps nodes inside the box", () => {
    const a = forceLayout(ids, edges, { width: 600, height: 400 });
    const b = forceLayout(ids.slice().reverse(), edges, { width: 600, height: 400 });
    expect(a).toEqual(b);
    for (const p of a) {
      expect(p.x).toBeGreaterThanOrEqual(20); expect(p.x).toBeLessThanOrEqual(580);
      expect(p.y).toBeGreaterThanOrEqual(20); expect(p.y).toBeLessThanOrEqual(380);
    }
  });
  it("places linked nodes closer than unlinked ones", () => {
    const pos = Object.fromEntries(forceLayout(ids, edges, { width: 800, height: 600 }).map((p) => [p.id, p]));
    const dist = (x: string, y: string) => Math.hypot(pos[x].x - pos[y].x, pos[x].y - pos[y].y);
    expect(dist("crime:fir:CHN-AD-1", "vehicle:plate:TN09AB4471")).toBeLessThan(dist("crime:fir:CHN-AD-1", "ent_p"));
  });
  it("pins the seed at the centre and handles tiny graphs", () => {
    const p = forceLayout(ids, edges, { width: 600, height: 400, pin: "ent_p" }).find((x) => x.id === "ent_p")!;
    expect(p).toMatchObject({ x: 300, y: 200 });
    expect(forceLayout([], [])).toEqual([]);
    expect(forceLayout(["a"], [], { width: 100, height: 50 })).toEqual([{ id: "a", x: 50, y: 25 }]);
  });
  it("lays out 200 nodes quickly", () => {
    const many = Array.from({ length: 200 }, (_, i) => `n${i}`);
    const es = many.slice(1).map((id, i) => ({ from: many[Math.floor(i / 3)], to: id }));
    const t = Date.now();
    expect(forceLayout(many, es)).toHaveLength(200);
    expect(Date.now() - t).toBeLessThan(3000);
  });
});

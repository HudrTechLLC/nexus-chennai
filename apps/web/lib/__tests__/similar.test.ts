/**
 * Unit tests for the look-alike ranking (lib/similar.ts).
 */
import { describe, expect, it } from "vitest";
import { rankSimilar, SIMILAR_WEIGHTS, tagVariants, type SimilarInput } from "../similar";

const c = (id: string, over: Partial<SimilarInput> = {}): SimilarInput => ({
  crime_id: id, station_id: "PS-A", category: "robbery", sub_type: "chain_snatching", cell: "88a", week: "2026-W43",
  mo_tags: [], visual_tags: [], ...over,
});

const self = c("SELF", { mo_tags: ["two_wheeler_from_behind", "gold_chain", "bus_stop"], visual_tags: ["red motorcycle", "black helmet red stripe"] });

describe("rankSimilar", () => {
  it("orders by shared MO first, then visual tags, sub-type and cell", () => {
    const out = rankSimilar(self, [
      c("SELF", { mo_tags: ["gold_chain"] }),
      c("VISUAL", { mo_tags: [], visual_tags: ["red_motorcycle"], sub_type: "street_robbery", cell: "x" }),
      c("MO", { mo_tags: ["two_wheeler_from_behind", "gold_chain", "bus_stop"], sub_type: "street_robbery", cell: "x" }),
      c("NONE", { mo_tags: ["on_foot"] }),
    ]);
    expect(out.map((h) => h.crime_id)).toEqual(["MO", "VISUAL"]);
    expect(out[0].score).toBeCloseTo(SIMILAR_WEIGHTS.mo);
    expect(out[0].sharedMo).toEqual(["two_wheeler_from_behind", "gold_chain", "bus_stop"]);
    expect(out[1].sharedVisual).toEqual(["red_motorcycle"]); // spaces and underscores compare equal
  });
  it("adds the sub-type and cell bonuses", () => {
    const [h] = rankSimilar(self, [c("X", { mo_tags: ["gold_chain"] })]);
    expect(h.score).toBeCloseTo(SIMILAR_WEIGHTS.mo * (1 / 3) + SIMILAR_WEIGHTS.subType + SIMILAR_WEIGHTS.cell, 3);
  });
  it("caps the list", () => {
    const many = Array.from({ length: 20 }, (_, i) => c(`C${i}`, { mo_tags: ["gold_chain"] }));
    expect(rankSimilar(self, many, 5)).toHaveLength(5);
  });
});

describe("tagVariants", () => {
  it("matches spaced, snake and dashed tags and drops wildcards", () => {
    expect(tagVariants(" Black  Helmet ")).toEqual(["black helmet", "black_helmet", "black-helmet"]);
    expect(tagVariants("red%_car")).toEqual(["red car", "red_car", "red-car"]);
    expect(tagVariants("ab")).toEqual([]);
  });
});

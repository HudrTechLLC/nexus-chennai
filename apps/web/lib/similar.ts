/**
 * "Similar MO" for the case file and search (spec G2 case file "similar cases", B4 SRCH-04).
 * A quick, explainable look-alike list over the city-wide summary every police role may read:
 * shared MO tags, shared visual tags, same sub-type, same area cell. It is a browsing aid, not
 * the linking score: link alerts come from the pipeline's F2 scoring and the Skeptic.
 */

export type SimilarInput = {
  crime_id: string;
  station_id: string;
  category: string;
  sub_type: string | null;
  cell: string | null;
  week: string | null;
  mo_tags: string[] | null;
  visual_tags: string[] | null;
};

export type SimilarHit = SimilarInput & { score: number; sharedMo: string[]; sharedVisual: string[] };

/** Weights for the look-alike score (sum 1). Shown in the UI so the number is explainable. */
export const SIMILAR_WEIGHTS = { mo: 0.6, visual: 0.25, subType: 0.1, cell: 0.05 } as const;

const norm = (t: string) => t.trim().toLowerCase().replace(/[\s-]+/g, "_");

function jaccard(a: string[], b: string[]): { j: number; shared: string[] } {
  const A = new Set(a.map(norm));
  const B = new Set(b.map(norm));
  const shared = Array.from(A).filter((x) => B.has(x));
  const union = new Set(Array.from(A).concat(Array.from(B))).size;
  return { j: union ? shared.length / union : 0, shared };
}

/** Ranks candidates against one case. Needs at least one shared MO or visual tag to be listed. */
export function rankSimilar(self: SimilarInput, candidates: SimilarInput[], limit = 8): SimilarHit[] {
  const w = SIMILAR_WEIGHTS;
  return candidates
    .filter((c) => c.crime_id !== self.crime_id)
    .map((c) => {
      const mo = jaccard(self.mo_tags ?? [], c.mo_tags ?? []);
      const vis = jaccard(self.visual_tags ?? [], c.visual_tags ?? []);
      const score = w.mo * mo.j + w.visual * vis.j
        + (self.sub_type && c.sub_type === self.sub_type ? w.subType : 0)
        + (self.cell && c.cell === self.cell ? w.cell : 0);
      return { ...c, score: Math.round(score * 1000) / 1000, sharedMo: mo.shared, sharedVisual: vis.shared };
    })
    .filter((h) => h.sharedMo.length + h.sharedVisual.length > 0)
    .sort((a, b) => b.score - a.score || (b.week ?? "").localeCompare(a.week ?? "") || a.crime_id.localeCompare(b.crime_id))
    .slice(0, limit);
}

/** Tag variants to match a typed phrase against stored tags ("black helmet" → black_helmet, black helmet). */
export function tagVariants(phrase: string): string[] {
  const p = phrase.trim().toLowerCase().replace(/[%_,()"'*\\]+/g, " ").replace(/\s+/g, " ").trim();
  if (p.length < 3) return [];
  return Array.from(new Set([p, p.replace(/ /g, "_"), p.replace(/ /g, "-")]));
}

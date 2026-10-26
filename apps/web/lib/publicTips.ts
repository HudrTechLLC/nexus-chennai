/**
 * "From the public" (WS3-28): the tips tied to an alert's crimes or a series' members, as an evidence feed
 * for linking. Three ties, the same ones the tip detail shows in reverse (#306, consoleArea.tipLinkedCrimes):
 *   appeal  - the tip answers a public appeal for the crime (tips.public_incident_id -> public_incidents.crime_id)
 *   tip     - the public sent it about the crime from a crime card (tips.about_crime_id, 0007_11)
 *   review  - an officer reviewing the tip linked it to the crime (tip_reviews.crime_id)
 * Pure functions: the loader in publicTipsData.ts reads the rows under the viewer's RLS.
 */

import type { TipCrimeSource } from "@/lib/consoleArea";
import type { TipStatus } from "@/lib/tips";

export const PUBLIC_TIPS_CAP = 50;

export type PublicTipRow = {
  tip_id: string;
  received_week: string;
  category: string;
  status: TipStatus;
  approx_cell: string | null;
  approx_cell_fine?: string | null;
  public_incident_id: string | null;
  about_crime_id: string | null;
};

export type PublicTipLink = { crimeId: string; source: TipCrimeSource };

export type PublicTip = PublicTipRow & { links: PublicTipLink[] };

export type PublicTipsFeed = {
  tips: PublicTip[];
  quarantined: number; // tied tips Tip Guard quarantined: counted, never listed (untrusted, not evidence)
  unreadableCrimes: number; // members the viewer cannot read in full (counted whether or not they have tips): not checked for tips
};

export const SOURCE_LABEL: Record<TipCrimeSource, string> = {
  appeal: "answered the appeal",
  tip: "sent about this case",
  review: "linked by an officer",
};

export const PUBLIC_TIPS_EMPTY =
  "No public tips yet. Tips sent from a public crime card or appeal appear here. Tips reach a case through its public appeal: an officer drafts one from the case file, " +
  "a supervisor approves it, and it then appears on the public site (appeals list and map), where anyone can " +
  "send a tip anonymously. The public can also send a tip from a crime card on the public map.";

const SOURCE_ORDER: Record<TipCrimeSource, number> = { appeal: 0, tip: 1, review: 2 };

/**
 * Join tips to the given (readable) crimes. Only ties to those crimes count; quarantined tips are counted
 * and dropped; newest week first, then tip id, capped at PUBLIC_TIPS_CAP.
 */
export function linkPublicTips(input: {
  crimeIds: string[];
  unreadableCrimes?: number;
  appeals: { public_incident_id: string; crime_id: string | null }[];
  reviews: { tip_id: string; crime_id: string | null }[];
  tips: PublicTipRow[];
}): PublicTipsFeed {
  const crimes = new Set(input.crimeIds);
  const appealCrime = new Map(
    input.appeals.filter((a) => a.crime_id && crimes.has(a.crime_id)).map((a) => [a.public_incident_id, a.crime_id as string]),
  );
  const reviewCrimes = new Map<string, Set<string>>();
  for (const r of input.reviews) {
    if (!r.crime_id || !crimes.has(r.crime_id)) continue;
    if (!reviewCrimes.has(r.tip_id)) reviewCrimes.set(r.tip_id, new Set());
    reviewCrimes.get(r.tip_id)!.add(r.crime_id);
  }

  const byId = new Map<string, PublicTip>();
  let quarantined = 0;
  const seenQuarantined = new Set<string>();
  for (const t of input.tips) {
    const links: PublicTipLink[] = [];
    const add = (crimeId: string | null | undefined, source: TipCrimeSource) => {
      if (crimeId && crimes.has(crimeId) && !links.some((l) => l.crimeId === crimeId && l.source === source)) {
        links.push({ crimeId, source });
      }
    };
    add(t.public_incident_id ? appealCrime.get(t.public_incident_id) : null, "appeal");
    add(t.about_crime_id, "tip");
    Array.from(reviewCrimes.get(t.tip_id) ?? []).forEach((c) => add(c, "review"));
    if (links.length === 0) continue;
    if (t.status === "quarantined") {
      if (!seenQuarantined.has(t.tip_id)) quarantined += 1;
      seenQuarantined.add(t.tip_id);
      continue;
    }
    const prev = byId.get(t.tip_id);
    const merged = prev ? [...prev.links, ...links.filter((l) => !prev.links.some((p) => p.crimeId === l.crimeId && p.source === l.source))] : links;
    byId.set(t.tip_id, { ...t, links: merged.sort((a, b) => SOURCE_ORDER[a.source] - SOURCE_ORDER[b.source] || a.crimeId.localeCompare(b.crimeId)) });
  }

  const tips = Array.from(byId.values())
    .sort((a, b) => b.received_week.localeCompare(a.received_week) || a.tip_id.localeCompare(b.tip_id))
    .slice(0, PUBLIC_TIPS_CAP);
  return { tips, quarantined, unreadableCrimes: input.unreadableCrimes ?? 0 };
}

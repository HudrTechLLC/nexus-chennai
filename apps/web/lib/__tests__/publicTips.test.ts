import { describe, expect, it } from "vitest";
import { linkPublicTips, PUBLIC_TIPS_CAP, PUBLIC_TIPS_EMPTY, type PublicTipRow } from "../publicTips";

const tip = (tip_id: string, extra: Partial<PublicTipRow> = {}): PublicTipRow => ({
  tip_id, received_week: "2026-W43", category: "vehicle_seen", status: "screened", approx_cell: "88618c4f41fffff",
  approx_cell_fine: null, public_incident_id: null, about_crime_id: null, ...extra,
});
const A = "CHN-AD-2026-000001";
const B = "CHN-VL-2026-000002";
const OTHER = "CHN-TI-2026-000003";

describe("linkPublicTips", () => {
  it("ties tips by appeal, by the crime card and by review, only to the given crimes", () => {
    const feed = linkPublicTips({
      crimeIds: [A, B],
      appeals: [{ public_incident_id: "PI-1", crime_id: A }, { public_incident_id: "PI-9", crime_id: OTHER }],
      reviews: [{ tip_id: "TIP-R", crime_id: B }, { tip_id: "TIP-R", crime_id: OTHER }],
      tips: [
        tip("TIP-APPEAL", { public_incident_id: "PI-1" }),
        tip("TIP-ABOUT", { about_crime_id: B }),
        tip("TIP-R"),
        tip("TIP-OTHER-APPEAL", { public_incident_id: "PI-9" }), // another case's appeal
        tip("TIP-UNTIED"),
      ],
    });
    expect(feed.tips.map((t) => t.tip_id)).toEqual(["TIP-ABOUT", "TIP-APPEAL", "TIP-R"]);
    expect(feed.tips.find((t) => t.tip_id === "TIP-APPEAL")!.links).toEqual([{ crimeId: A, source: "appeal" }]);
    expect(feed.tips.find((t) => t.tip_id === "TIP-R")!.links).toEqual([{ crimeId: B, source: "review" }]); // OTHER dropped
  });

  it("merges every tie of one tip, appeal first, and never repeats a tie", () => {
    const feed = linkPublicTips({
      crimeIds: [A, B],
      appeals: [{ public_incident_id: "PI-1", crime_id: A }],
      reviews: [{ tip_id: "TIP-1", crime_id: B }, { tip_id: "TIP-1", crime_id: B }],
      tips: [tip("TIP-1", { public_incident_id: "PI-1", about_crime_id: A }), tip("TIP-1", { public_incident_id: "PI-1" })],
    });
    expect(feed.tips).toHaveLength(1);
    expect(feed.tips[0].links).toEqual([{ crimeId: A, source: "appeal" }, { crimeId: A, source: "tip" }, { crimeId: B, source: "review" }]);
  });

  it("counts quarantined tips once and never lists them", () => {
    const feed = linkPublicTips({
      crimeIds: [A], appeals: [], reviews: [],
      tips: [tip("TIP-Q", { about_crime_id: A, status: "quarantined" }), tip("TIP-Q", { about_crime_id: A, status: "quarantined" }),
        tip("TIP-OK", { about_crime_id: A })],
    });
    expect(feed.tips.map((t) => t.tip_id)).toEqual(["TIP-OK"]);
    expect(feed.quarantined).toBe(1);
  });

  it("puts the newest week first and caps the list", () => {
    const tips = Array.from({ length: PUBLIC_TIPS_CAP + 5 }, (_, i) =>
      tip(`TIP-${String(i).padStart(3, "0")}`, { about_crime_id: A, received_week: i % 2 ? "2026-W44" : "2026-W40" }));
    const feed = linkPublicTips({ crimeIds: [A], appeals: [], reviews: [], tips });
    expect(feed.tips).toHaveLength(PUBLIC_TIPS_CAP);
    expect(feed.tips[0].received_week).toBe("2026-W44");
  });

  it("is empty with no readable crimes, and reports the unreadable count", () => {
    const feed = linkPublicTips({ crimeIds: [], unreadableCrimes: 2, appeals: [], reviews: [], tips: [tip("T", { about_crime_id: A })] });
    expect(feed).toEqual({ tips: [], quarantined: 0, unreadableCrimes: 2 });
  });

  it("explains how tips reach a case", () => {
    expect(PUBLIC_TIPS_EMPTY).toMatch(/^No public tips yet\./);
    expect(PUBLIC_TIPS_EMPTY).toMatch(/appeal/);
  });
});

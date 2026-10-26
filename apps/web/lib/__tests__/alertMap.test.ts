/**
 * Unit tests for the alert map helpers (lib/alertMap.ts): distance and time between the two scenes,
 * and the ANPR trail of the matched vehicle.
 */
import { describe, expect, it } from "vitest";
import { describeGap, haversineKm, sceneGap, trailOf, type Scene, type TrailRead } from "../alertMap";

const adyar: Scene = { id: "CHN-AD-2026-001182", p: [80.2565, 13.0012], exact: true, at: "2026-10-14T14:20:00Z", week: "2026-W42" };
const velachery: Scene = { id: "CHN-VL-2026-000877", p: [80.2209, 12.9791], exact: true, at: "2026-10-16T14:10:00Z", week: "2026-W42" };

describe("haversineKm", () => {
  it("measures great-circle distance in km", () => {
    expect(haversineKm([80.2565, 13.0012], [80.2565, 13.0012])).toBe(0);
    // One degree of latitude is about 111.2 km.
    expect(haversineKm([80, 13], [80, 14])).toBeCloseTo(111.2, 0);
    expect(haversineKm(adyar.p, velachery.p)).toBeCloseTo(4.5, 0);
  });
});

describe("sceneGap", () => {
  it("is exact when both scenes are readable", () => {
    const g = sceneGap(adyar, velachery)!;
    expect(g.approx).toBe(false);
    expect(g.hours).toBeCloseTo(47.8, 1);
    expect(g.weeks).toBeNull();
  });
  it("falls back to cell centres and ISO weeks when a scene is only a summary", () => {
    const g = sceneGap(adyar, { ...velachery, exact: false, at: null, week: "2026-W44" })!;
    expect(g.approx).toBe(true);
    expect(g.hours).toBeNull();
    expect(g.weeks).toBe(2);
  });
  it("needs two placed scenes", () => {
    expect(sceneGap(adyar, null)).toBeNull();
  });
});

describe("describeGap", () => {
  it("says distance and time in plain words, and marks approximations", () => {
    expect(describeGap(sceneGap(adyar, velachery)!)).toBe("4.6 km apart · 2 days apart");
    expect(describeGap({ km: 1, approx: false, hours: 29.2, weeks: null })).toBe("1.0 km apart · 1 day 5 h apart");
    expect(describeGap({ km: 1, approx: false, hours: 0.4, weeks: null })).toBe("1.0 km apart · under 1 h apart");
    expect(describeGap({ km: 0.42, approx: true, hours: null, weeks: 0 })).toBe("about 0.4 km apart (area cells) · same ISO week");
    expect(describeGap({ km: 12, approx: false, hours: 3.4, weeks: null })).toBe("12.0 km apart · 3 h apart");
    expect(describeGap({ km: 2, approx: true, hours: null, weeks: null })).toBe("about 2.0 km apart (area cells) · time not visible to you");
  });
});

describe("trailOf", () => {
  const reads: TrailRead[] = [
    { read_id: "R2", camera_id: "ANPR-VLY-03", read_at: "2026-10-16T14:16:12Z", plate_text: "TN09BX4471", crime_id: "CHN-VL-2026-000877", p: [80.2235, 12.9845] },
    { read_id: "R1", camera_id: "ANPR-OMR-12", read_at: "2026-10-14T14:28:41Z", plate_text: "TN09BX4471", crime_id: "CHN-AD-2026-001182", p: [80.251, 12.9921] },
    { read_id: "R3", camera_id: "ANPR-MAD-13", read_at: "2026-10-15T09:00:00Z", plate_text: "TN 09 BX 4471", crime_id: null, p: [80.24, 13.03] },
    { read_id: "R4", camera_id: "ANPR-X", read_at: "2026-10-15T10:00:00Z", plate_text: "TN14VL2488", crime_id: "CHN-XX-1", p: [80.2, 13.0] },
  ];
  it("keeps the plates seen near either scene, in time order, one path per plate", () => {
    const t = trailOf(reads, ["CHN-AD-2026-001182", "CHN-VL-2026-000877"]);
    expect(t.map((x) => x.plate)).toEqual(["TN09BX4471"]);
    expect(t[0].reads.map((r) => r.read_id)).toEqual(["R1", "R3", "R2"]);
  });
  it("is empty when no read is linked to either scene", () => {
    expect(trailOf(reads, ["NONE"])).toEqual([]);
  });
});

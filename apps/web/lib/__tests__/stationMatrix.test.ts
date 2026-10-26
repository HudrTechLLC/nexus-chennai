import { describe, expect, it } from "vitest";
import { buildMatrix, cellCounts, intensity, pairKey, parseStatuses, shortStation, type MatrixPayload } from "../stationMatrix";

const payload: MatrixPayload = {
  alerts: 5,
  stations: [
    { id: "PS-ADYAR", name: "PS-ADYAR-J2", zone: "South" },
    { id: "PS-VLY", name: "PS-VELACHERY-J7", zone: "South" },
    { id: "PS-TNG", name: "PS-T_NAGAR-R1", zone: "Central" },
    { id: "PS-IDLE", name: "PS-IDLE", zone: "North" },
  ],
  cells: [
    { a: "PS-ADYAR", b: "PS-VLY", status: "approved", kind: "pair", n: 2, alert_ids: ["LA-2", "LA-1"] },
    { a: "PS-ADYAR", b: "PS-VLY", status: "rejected", kind: "pair", n: 1, alert_ids: ["LA-3"] },
    // one series alert spanning three stations sits in three pair cells
    { a: "PS-ADYAR", b: "PS-VLY", status: "pending", kind: "series", n: 1, alert_ids: ["LA-9"] },
    { a: "PS-ADYAR", b: "PS-TNG", status: "pending", kind: "series", n: 1, alert_ids: ["LA-9"] },
    { a: "PS-TNG", b: "PS-VLY", status: "pending", kind: "series", n: 1, alert_ids: ["LA-9"] },
    { a: "PS-TNG", b: "PS-TNG", status: "approved", kind: "pair", n: 1, alert_ids: ["LA-5"] },
  ],
  per_station: [
    { station: "PS-ADYAR", status: "approved", n: 2 }, { station: "PS-ADYAR", status: "rejected", n: 1 }, { station: "PS-ADYAR", status: "pending", n: 1 },
    { station: "PS-VLY", status: "approved", n: 2 }, { station: "PS-VLY", status: "rejected", n: 1 }, { station: "PS-VLY", status: "pending", n: 1 },
    { station: "PS-TNG", status: "pending", n: 1 }, { station: "PS-TNG", status: "approved", n: 1 },
  ],
};

describe("pairKey", () => {
  it("is order independent", () => {
    expect(pairKey("B", "A")).toBe(pairKey("A", "B"));
    expect(pairKey("A", "A")).toBe("A|A");
  });
});

describe("buildMatrix", () => {
  const m = buildMatrix(payload);

  it("lists only stations with alerts, by zone then name", () => {
    expect(m.stations.map((s) => s.id)).toEqual(["PS-TNG", "PS-ADYAR", "PS-VLY"]);
  });

  it("splits a cell by status and keeps it symmetric", () => {
    const c = cellCounts(m, "PS-VLY", "PS-ADYAR");
    expect(c).toMatchObject({ approved: 2, rejected: 1, pending: 1, total: 4 });
    expect(c.alertIds).toEqual(["LA-2", "LA-1", "LA-3", "LA-9"]);
    expect(cellCounts(m, "PS-ADYAR", "PS-VLY")).toBe(c);
  });

  it("puts same-station alerts on the diagonal and leaves them out of cross-station totals", () => {
    expect(cellCounts(m, "PS-TNG", "PS-TNG").total).toBe(1);
    expect(m.crossTotal).toBe(6);
    expect(m.maxCross).toBe(4);
  });

  it("counts a multi-station alert once per station", () => {
    expect(m.perStation["PS-TNG"].total).toBe(2);
    expect(m.perStation["PS-ADYAR"].total).toBe(4);
  });

  it("ranks the most-linked cross-station pairs first", () => {
    expect(m.topPairs[0]).toMatchObject({ a: "PS-ADYAR", b: "PS-VLY" });
    expect(m.topPairs.every((p) => p.a !== p.b)).toBe(true);
  });

  it("filters by status", () => {
    const approved = buildMatrix(payload, ["approved"]);
    expect(cellCounts(approved, "PS-ADYAR", "PS-VLY").total).toBe(2);
    expect(cellCounts(approved, "PS-ADYAR", "PS-TNG").total).toBe(0);
    expect(approved.perStation["PS-TNG"].total).toBe(1);
  });

  it("returns an empty grid for an empty payload", () => {
    const e = buildMatrix({ cells: [], per_station: [], stations: [], alerts: 0 });
    expect(e.stations).toEqual([]);
    expect(e.topPairs).toEqual([]);
    expect(e.maxCross).toBe(0);
  });

  it("keeps a station the stations list does not know, by id", () => {
    const x = buildMatrix({ ...payload, stations: [] });
    expect(x.stations.map((s) => s.name)).toContain("PS-TNG");
  });
});

describe("intensity", () => {
  it("is 0 for empty cells and 1 at the maximum, square-root in between", () => {
    expect(intensity(0, 10)).toBe(0);
    expect(intensity(10, 10)).toBe(1);
    expect(intensity(1, 4)).toBeCloseTo(0.5);
    expect(intensity(3, 0)).toBe(0);
  });
});

describe("parseStatuses / shortStation", () => {
  it("defaults to every status and drops unknown values", () => {
    expect(parseStatuses(undefined)).toEqual(["approved", "pending", "rejected"]);
    expect(parseStatuses("approved,bogus")).toEqual(["approved"]);
    expect(parseStatuses("bogus")).toEqual(["approved", "pending", "rejected"]);
  });
  it("shortens station names", () => {
    expect(shortStation("PS-VELACHERY-J7")).toBe("VELACHERY");
    expect(shortStation("PS-T_NAGAR-R1")).toBe("T NAGAR");
    expect(shortStation("Adyar")).toBe("Adyar");
    expect(shortStation("Shastri Nagar (J5)")).toBe("Shastri Nagar");
  });
});

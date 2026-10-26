/**
 * Unit tests for lib/weights.ts, plus a guard that its copy of the F2 defaults matches weights.py.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_WEIGHTS, SCORING_RULES, WEIGHTS_VERSION, factorUsage, nonDefaultAlerts, versionCounts } from "../weights";

const PY = readFileSync(resolve(__dirname, "../../../../services/api/app/scoring/weights.py"), "utf8");
const pyNumber = (name: string) => Number(new RegExp(`^${name}\\s*=\\s*([0-9.]+)`, "m").exec(PY)?.[1]);

describe("weights.ts matches services/api/app/scoring/weights.py", () => {
  it("has the same version", () => {
    expect(/^WEIGHTS_VERSION\s*=\s*"([^"]+)"/m.exec(PY)?.[1]).toBe(WEIGHTS_VERSION);
  });
  it("has the same factors, order and weights", () => {
    const block = /DEFAULT_WEIGHTS[^{]*\{([^}]*)\}/.exec(PY)?.[1] ?? "";
    const py = Array.from(block.matchAll(/"(\w+)":\s*([0-9.]+)/g)).map((m) => [m[1], Number(m[2])]);
    expect(py.length).toBe(9);
    expect(Object.entries(DEFAULT_WEIGHTS)).toEqual(py);
  });
  it("has the same bands, floor, caps and coverage guard", () => {
    for (const [k, v] of Object.entries(SCORING_RULES)) expect([k, pyNumber(k)]).toEqual([k, v]);
  });
});

describe("factorUsage", () => {
  const rows = [
    { factor: "mo_similarity", weight: 0.25, alert_id: "A1", created_at: "2026-10-26T09:00:00Z" },
    { factor: "mo_similarity", weight: 0.25, alert_id: "A2", created_at: "2026-10-26T10:00:00Z" },
    { factor: "vehicle", weight: 0.15000000596, alert_id: "A1", created_at: "2026-10-26T09:00:00Z" }, // float4 read-back
    { factor: "vehicle", weight: 0.3, alert_id: "A3", created_at: "2026-10-27T08:00:00Z" },
  ];
  it("groups each factor's persisted weights, with counts and dates", () => {
    const u = factorUsage(rows);
    expect(u.map((f) => f.factor)).toEqual(Object.keys(DEFAULT_WEIGHTS));
    expect(u[0].used).toEqual([{ weight: 0.25, alerts: 2, first: "2026-10-26T09:00:00Z", last: "2026-10-26T10:00:00Z", isDefault: true }]);
    const v = u.find((f) => f.factor === "vehicle")!;
    expect(v.used.map((x) => [x.weight, x.isDefault])).toEqual([[0.15, true], [0.3, false]]);
  });
  it("leaves factors with no rows empty, not zero", () => {
    expect(factorUsage(rows).find((f) => f.factor === "forensic")!.used).toEqual([]);
  });
  it("flags alerts scored with non-default weights", () => {
    expect(nonDefaultAlerts(rows)).toEqual(["A3"]);
    expect(nonDefaultAlerts([{ factor: "new_factor", weight: 0.1, alert_id: "A9", created_at: null }])).toEqual(["A9"]);
  });
});

describe("versionCounts", () => {
  it("counts alerts per recorded version and shows unrecorded ones as pre-versioning", () => {
    expect(versionCounts([{ weights_version: null }, { weights_version: "f2-default-v1" }, { weights_version: null }, { weights_version: "custom" }, { weights_version: " " }])).toEqual([
      { version: "pre-versioning", alerts: 3, current: false },
      { version: "custom", alerts: 1, current: false },
      { version: "f2-default-v1", alerts: 1, current: true },
    ]);
  });
});

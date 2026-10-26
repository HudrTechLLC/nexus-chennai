import { describe, expect, it } from "vitest";
import { beatsText, deltaPts, NO_REPORT, parseEvalReport, pctOrDash } from "../evalReport";
import sample from "./fixtures/eval_report.sample.json";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- a deliberately loose copy to break the shape
const clone = () => JSON.parse(JSON.stringify(sample)) as Record<string, any>;

describe("parseEvalReport", () => {
  it("reads the app.eval report shape", () => {
    const r = parseEvalReport(sample)!;
    expect(r.agent.precision).toBe(0.8571);
    expect(r.baseline.recall).toBe(0.5);
    expect(r.baseline.rule).toMatch(/2 km/);
    expect(r.beats).toEqual({ precision: true, recall: true });
    expect(r.bands.map((b) => b.band)).toEqual(["high", "medium"]);
    expect(r.types[0].type).toBe("chain_snatching"); // busiest type first
    expect(r.modes.map((m) => m.mode)).toEqual(["off", "on"]);
    expect(r.duplicates).toEqual({ truth_pairs: 1, flagged_by_agent: 0, flagged_by_baseline: 1 });
    expect(r.provenance).toMatchObject({ synthetic: true, sampleMode: true, excludedNonGenerated: 2, runId: "eval-20261026-abcdef", withLiveModelFeatures: 3 });
    expect(r.agent.series).toEqual({ predicted_series: 2, mean_purity: 0.9 });
  });

  it("is null for the placeholder and for unknown shapes", () => {
    expect(parseEvalReport({ available: false })).toBeNull();
    expect(parseEvalReport(null)).toBeNull();
    expect(parseEvalReport([])).toBeNull();
    expect(parseEvalReport({ agent: {}, baseline_rules_only: {} })).toBeNull();
    expect(NO_REPORT).toMatch(/committed yet/);
  });

  it("tolerates nulls and missing optional blocks", () => {
    const raw = clone();
    raw.agent.precision = null;
    raw.agent.series.mean_purity = null;
    raw.agent.by_band.medium.precision = null;
    delete raw.mo_cosine_trial;
    delete raw.duplicates;
    delete raw.timing;
    raw.beats_baseline.precision = null;
    const r = parseEvalReport(raw)!;
    expect(r.agent.precision).toBeNull();
    expect(r.agent.series?.mean_purity).toBeNull();
    expect(r.bands[1].precision).toBeNull();
    expect(r.modes).toEqual([]);
    expect(r.duplicates).toBeNull();
    expect(r.medianSecondsPerCase).toBeNull();
    expect(r.beats.precision).toBeNull();
  });

  it("accepts a numeric weights version", () => {
    const raw = clone();
    raw.weights_version = 3;
    expect(parseEvalReport(raw)!.provenance.weightsVersion).toBe("3");
  });
});

describe("formatting", () => {
  it("formats percentages and point differences", () => {
    expect(pctOrDash(0.8571)).toBe("85.7%");
    expect(pctOrDash(1)).toBe("100.0%");
    expect(pctOrDash(null)).toBe("—");
    expect(deltaPts(0.8571, 0.4444)).toBe("+41.3 pts");
    expect(deltaPts(0.4, 0.5)).toBe("−10.0 pts");
    expect(deltaPts(0.5, 0.5)).toBe("±0.0 pts");
    expect(deltaPts(null, 0.5)).toBeNull();
  });

  it("says plainly when the agents do not beat the baseline", () => {
    expect(beatsText("recall", false)).toMatch(/do not beat/);
    expect(beatsText("precision", true)).toMatch(/beat the rules-only/);
    expect(beatsText("precision", null)).toMatch(/not comparable/);
  });
});

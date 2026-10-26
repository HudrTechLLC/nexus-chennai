import { describe, expect, it } from "vitest";
import {
  actionLabel, confidenceChange, decisionLabel, memoryStories, parseEffect, parseLedgerFilter, scoreBeforeMemory, summarise,
  type Effect, type LedgerRow, type MemoryRow,
} from "../memory";

const mem = (memory_id: string, extra: Partial<MemoryRow> = {}): MemoryRow => ({
  id: `nexus:${memory_id}`, store: "nexus", memory_id, content: "Shared: two riders, chain snatch.", tags: [], confidence: 0.6,
  layer: "working", decision: "reject", polarity: -1, reason_code: "different_offenders", alert_id: "LA-1", note: null,
  synthetic: true, created_at: "2026-10-26T08:00:00Z", updated_at: "2026-10-26T08:00:00Z", ...extra,
});
const led = (id: number, memory_id: string, action: string, at: string, before?: number, after?: number, store = "nexus"): LedgerRow => ({
  id, store, memory_id, action, actor: "worker", at, entry_hash: `h${id}`, synthetic: true,
  details: { ...(before != null ? { previousState: { confidence: before } } : {}), ...(after != null ? { newState: { confidence: after } } : {}) },
});
const eff = (alert_id: string, memory_id: string, effect: string, at: string, extra: Partial<Effect> = {}): Effect => ({
  alert_id, memory_id, effect, text: `${memory_id} applied`, score: 0.7, band: "medium", status: "pending", kind: "pair",
  crimes: ["C1", "C2"], stations: ["PS-A"], created_at: at, ...extra,
});

describe("parsing", () => {
  it("parses recorded effects", () => {
    expect(parseEffect("+0.03")).toBe(0.03);
    expect(parseEffect("-0.08")).toBe(-0.08);
    expect(parseEffect("")).toBeNull();
    expect(parseEffect(null)).toBeNull();
    expect(parseEffect("n/a")).toBeNull();
  });
  it("reads confidence before and after from the ledger states", () => {
    expect(confidenceChange(led(1, "mem-1", "feedback", "t", 0.6, 0.45))).toEqual({ before: 0.6, after: 0.45 });
    expect(confidenceChange({ details: null })).toEqual({ before: null, after: null });
  });
  it("labels decisions and actions", () => {
    expect(decisionLabel("approve")).toBe("Approved");
    expect(decisionLabel("rejected")).toBe("Rejected");
    expect(decisionLabel(null)).toBe("—");
    expect(actionLabel("create")).toBe("Memory created");
    expect(actionLabel("brand_new")).toBe("brand new");
  });
  it("defaults the ledger filter to decisions (hides reads)", () => {
    expect(parseLedgerFilter(undefined)).toBe("decisions");
    expect(parseLedgerFilter("all")).toBe("all");
    expect(parseLedgerFilter("feedback")).toBe("feedback");
    expect(parseLedgerFilter("drop table")).toBe("decisions");
  });
  it("recovers the pre-memory score", () => {
    expect(scoreBeforeMemory(0.78, -0.04)).toBe(0.82);
    expect(scoreBeforeMemory(0.05, 0.08)).toBe(0);
    expect(scoreBeforeMemory(0.7, null)).toBeNull();
  });
});

describe("memoryStories (the E4 three-session story)", () => {
  // Session 1: analyst rejects LA-1 → mem-1 (reject). Session 3: approval of LA-5 → mem-2 (approve).
  const memories = [
    mem("mem-1"),
    mem("mem-2", { decision: "approve", polarity: 1, reason_code: null, alert_id: "LA-5", confidence: 0.7, created_at: "2026-10-26T09:00:00Z", updated_at: "2026-10-26T09:00:00Z" }),
    mem("mem-1", { id: "other:mem-1", store: "other", alert_id: "LA-X" }), // same memory_id in another store
  ];
  const ledger = [
    led(1, "mem-1", "create", "2026-10-26T08:00:00Z", undefined, 0.6),
    led(2, "mem-1", "read", "2026-10-26T08:30:00Z"),
    led(3, "mem-1", "feedback", "2026-10-26T08:40:00Z", 0.6, 0.7),
    led(4, "mem-1", "feedback", "2026-10-26T08:41:00Z", 0.7, 0.7), // no change → not a new point
    led(5, "mem-1", "create", "2026-10-26T08:00:00Z", undefined, 0.2, "other"),
    led(6, "mem-2", "create", "2026-10-26T09:00:00Z", undefined, 0.7),
  ];
  const effects = [
    eff("LA-1", "mem-1", "-0.04", "2026-10-26T07:00:00Z"), // its own source alert: ignored
    eff("LA-2", "mem-1", "-0.04", "2026-10-26T08:30:00Z", { score: 0.62 }), // Session 2: similar pair drops
    eff("LA-6", "mem-2", "+0.03", "2026-10-26T09:30:00Z", { band: "high", score: 0.81 }), // the next red-Pulsar pair rises
    eff("LA-7", "mem-1", "+0.02", "2026-10-26T10:00:00Z"),
    eff("LA-7", "mem-2", "+0.02", "2026-10-26T10:00:00Z", { text: "mem-1 applied" }), // one adjustment, two memories
  ];
  const stories = memoryStories(memories, effects, ledger);

  it("keeps one story per memory_id, preferring the nexus store", () => {
    expect(stories.map((s) => s.memory.id).sort()).toEqual(["nexus:mem-1", "nexus:mem-2"]);
  });

  it("links a rejection to the later alert it lowered, never to its own source alert", () => {
    const s1 = stories.find((s) => s.memory.memory_id === "mem-1")!;
    expect(s1.applied.map((a) => a.alert_id)).toEqual(["LA-2", "LA-7"]);
    expect(s1.lowered).toBe(1);
    expect(s1.raised).toBe(1);
    expect(s1.applied[0].delta).toBe(-0.04);
  });

  it("links an approval to the later alert it raised", () => {
    const s2 = stories.find((s) => s.memory.memory_id === "mem-2")!;
    expect(s2.applied[0]).toMatchObject({ alert_id: "LA-6", delta: 0.03, shared: 1 });
  });

  it("marks an adjustment shared by two memories", () => {
    const s1 = stories.find((s) => s.memory.memory_id === "mem-1")!;
    expect(s1.applied.find((a) => a.alert_id === "LA-7")!.shared).toBe(2);
  });

  it("builds the confidence history from its own store's ledger, skipping no-op entries", () => {
    const s1 = stories.find((s) => s.memory.memory_id === "mem-1")!;
    expect(s1.history.map((h) => [h.action, h.confidence])).toEqual([["create", 0.6], ["feedback", 0.7]]);
  });

  it("orders memories by how many later alerts they changed, newest first on ties", () => {
    const lens = stories.map((s) => s.applied.length);
    expect(lens).toEqual(lens.slice().sort((a, b) => b - a));
    expect(stories[0].memory.memory_id).toBe("mem-2"); // both changed 2 alerts; mem-2 is newer
  });

  it("is empty when there are no memories yet", () => {
    expect(memoryStories([], effects, ledger)).toEqual([]);
  });
});

describe("summarise", () => {
  it("counts decisions, layers and alerts adjusted (once per alert)", () => {
    const s = summarise(
      [mem("mem-1"), mem("mem-2", { decision: "approve", layer: "long_term", confidence: 0.8 })],
      [eff("LA-2", "mem-1", "-0.04", "t"), eff("LA-7", "mem-1", "+0.02", "t"), eff("LA-7", "mem-2", "+0.02", "t")],
    );
    expect(s).toMatchObject({ memories: 2, approved: 1, rejected: 1, alertsAdjusted: 2, raised: 1, lowered: 1 });
    expect(s.byLayer).toEqual({ short_term: 0, working: 1, long_term: 1 });
    expect(s.meanConfidence).toBeCloseTo(0.7);
  });
  it("handles an empty store", () => {
    expect(summarise([], [])).toMatchObject({ memories: 0, meanConfidence: null, alertsAdjusted: 0 });
  });
});

/**
 * Unit tests for Ask Nexus helpers (WS3-30).
 */
import { describe, expect, it } from "vitest";
import {
  checkQuestion, crimeLabel, hitScenes, insertErrorText, isSettled, nextPoll, POLL_GIVE_UP_MS, QUESTION_MAX, SAMPLE_QUESTIONS, visibleResults,
  type AskCrime,
} from "../ask";

const crime = (id: string, extra: Partial<AskCrime> = {}): AskCrime => ({
  crime_id: id, category: "robbery", sub_type: "chain_snatching", station_id: "PS-ADYAR-J2",
  occurred_from: "2026-10-26T14:10:00Z", address: "LB Road", lat: 13.0, lon: 80.25, status: "under_investigation", ...extra,
});

describe("checkQuestion", () => {
  it("trims and collapses spaces", () => {
    expect(checkQuestion("  house   breaks  in Adyar ")).toEqual({ ok: true, question: "house breaks in Adyar" });
  });
  it("refuses empty and over-long questions", () => {
    expect(checkQuestion("  ").ok).toBe(false);
    expect(checkQuestion("ab").ok).toBe(false);
    expect(checkQuestion("x".repeat(QUESTION_MAX + 1)).ok).toBe(false);
  });
  it("accepts every sample chip", () => {
    for (const q of SAMPLE_QUESTIONS) expect(checkQuestion(q).ok).toBe(true);
  });
});

describe("polling", () => {
  it("stops on a settled status", () => {
    for (const s of ["answered", "unmappable", "failed"] as const) {
      expect(isSettled(s)).toBe(true);
      expect(nextPoll(s, 1000)).toBe("done");
    }
  });
  it("keeps polling while the worker is busy, and gives up after the limit", () => {
    expect(nextPoll("queued", 0)).toBe("poll");
    expect(nextPoll("running", POLL_GIVE_UP_MS - 1)).toBe("poll");
    expect(nextPoll("planning", POLL_GIVE_UP_MS)).toBe("gave_up");
  });
});

describe("visibleResults", () => {
  it("keeps the answer's order, joins display fields, and never shows an unreadable id", () => {
    const { rows, hidden } = visibleResults(
      [{ crime_id: "B", why: "19:40" }, { crime_id: "X", why: "other station" }, { crime_id: "A", why: "red Pulsar" }, { crime_id: "B", why: "dup" }],
      [crime("A"), crime("B")],
    );
    expect(rows.map((r) => [r.crime_id, r.why])).toEqual([["B", "19:40"], ["A", "red Pulsar"]]);
    expect(hidden).toBe(1);
    expect(rows.some((r) => r.crime_id === "X")).toBe(false);
  });
});

describe("hitScenes", () => {
  it("plots only rows with coordinates", () => {
    const { rows } = visibleResults([{ crime_id: "A", why: "" }, { crime_id: "B", why: "" }], [crime("A"), crime("B", { lat: null })]);
    expect(hitScenes(rows)).toEqual([{ id: "A", p: [80.25, 13.0], exact: true, at: "2026-10-26T14:10:00Z", week: null, label: "A" }]);
  });
});

describe("crimeLabel", () => {
  it("prefers the sub-type, then the category", () => {
    expect(crimeLabel({ category: "robbery", sub_type: "chain_snatching" })).toBe("Chain snatching");
    expect(crimeLabel({ category: "house_break", sub_type: null })).toBe("House break");
    expect(crimeLabel({ category: null, sub_type: null })).toBe("Crime");
  });
});

describe("insertErrorText", () => {
  it("shows the 3-waiting limit as is, and names a missing table plainly", () => {
    const limit = "you already have 3 questions waiting; wait for an answer first";
    expect(insertErrorText({ code: "23514", message: limit })).toBe(limit);
    expect(insertErrorText({ code: "42P01", message: 'relation "ask_questions" does not exist' })).toMatch(/not switched on/);
    expect(insertErrorText({ message: "network" })).toMatch(/try again/);
  });
});

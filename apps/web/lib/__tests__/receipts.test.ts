/**
 * Unit tests for receipt labels (chief, 2026-10-27): a chatcmpl completion id is never called a Nightshift receipt,
 * and one matched offline to a signed Nightshift receipt says so; an unmatched one is counted, never hidden.
 */

import { describe, expect, it } from "vitest";
import { isMatched, receiptCountLine, receiptKind, receiptLabel, receiptNote } from "../receipts";
import matches from "@/content/receipt_matches.json";

const M = new Set(["chatcmpl-a", "chatcmpl-b"]);

describe("receiptLabel / receiptNote", () => {
  it("labels Nightshift's own rcpt_ id as a Nightshift receipt", () => {
    expect(receiptKind("rcpt_01HXYZ")).toBe("nightshift");
    expect(receiptLabel("rcpt_01HXYZ", M)).toBe("Nightshift receipt");
    expect(receiptNote("rcpt_01HXYZ", M)).toBeNull();
  });

  it("labels a matched chatcmpl id as a completion id with a signed-receipt note", () => {
    expect(receiptLabel("chatcmpl-a", M)).toBe("completion id");
    expect(receiptNote("chatcmpl-a", M)).toBe("signed Nightshift receipt ✓");
  });

  it("says plainly when a chatcmpl id is not matched", () => {
    expect(receiptLabel("chatcmpl-zzz", M)).toBe("completion id (not yet matched to a Nightshift receipt)");
    expect(receiptNote("chatcmpl-zzz", M)).toBeNull();
  });

  it("gives any other id a neutral label and nothing for no id", () => {
    expect(receiptLabel("abc123", M)).toBe("model call id");
    expect(receiptLabel(null, M)).toBeNull();
  });
});

describe("receiptCountLine", () => {
  it("all matched (the hero run's case)", () => {
    expect(receiptCountLine(["chatcmpl-a", "chatcmpl-b", null], M)).toBe("2 completion ids · all 2 matched to signed Nightshift receipts (verified offline)");
  });

  it("counts the unmatched ones", () => {
    expect(receiptCountLine(["chatcmpl-a", "chatcmpl-x", "chatcmpl-y"], M)).toBe("3 completion ids · 1 matched to signed Nightshift receipts (verified offline), 2 not yet matched");
    expect(receiptCountLine(["chatcmpl-x"], M)).toBe("1 completion id · not yet matched to Nightshift receipts");
  });

  it("names receipts and completion ids together", () => {
    expect(receiptCountLine(["rcpt_1", "chatcmpl-a"], M)).toBe("1 Nightshift receipt · 1 completion id · matched to a signed Nightshift receipt (verified offline)");
  });

  it("says so when there is none", () => {
    expect(receiptCountLine([], M)).toBe("no model call ids");
  });
});

describe("committed matches file", () => {
  it("holds ids only, all completion ids, and its counts agree", () => {
    expect(matches.verified).toBe(matches.ids.length);
    expect(matches.ids.every((id) => /^chatcmpl-[0-9a-f-]+$/.test(id))).toBe(true);
    expect(isMatched(matches.ids[0])).toBe(true);
  });
});

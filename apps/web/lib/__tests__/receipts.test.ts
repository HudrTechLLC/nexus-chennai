/**
 * Unit tests for receipt labels (chief, 2026-10-27): a chatcmpl completion id is never called a Nightshift receipt.
 */

import { describe, expect, it } from "vitest";
import { receiptCountLine, receiptKind, receiptLabel } from "../receipts";

describe("receiptLabel", () => {
  it("labels Nightshift's own rcpt_ id as a Nightshift receipt", () => {
    expect(receiptKind("rcpt_01HXYZ")).toBe("nightshift");
    expect(receiptLabel("rcpt_01HXYZ")).toBe("Nightshift receipt");
  });

  it("labels a chatcmpl id as a completion id with no Nightshift receipt id", () => {
    expect(receiptKind("chatcmpl-b496ce3a")).toBe("completion");
    expect(receiptLabel("chatcmpl-b496ce3a")).toBe("completion id (no Nightshift receipt id)");
  });

  it("gives any other id a neutral label and nothing for no id", () => {
    expect(receiptLabel("abc123")).toBe("model call id");
    expect(receiptLabel(null)).toBeNull();
    expect(receiptLabel("")).toBeNull();
  });
});

describe("receiptCountLine", () => {
  it("counts only chatcmpl ids as completion ids, flagged as having no receipt", () => {
    expect(receiptCountLine(["chatcmpl-1", "chatcmpl-2", null])).toBe("2 completion ids (no Nightshift receipt id)");
  });

  it("names both when a run has both", () => {
    expect(receiptCountLine(["rcpt_1", "chatcmpl-1", "rcpt_2"])).toBe("2 Nightshift receipts · 1 completion id");
  });

  it("says so when there is none", () => {
    expect(receiptCountLine([])).toBe("no model call ids");
  });
});

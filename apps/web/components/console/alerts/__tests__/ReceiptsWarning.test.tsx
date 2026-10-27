/**
 * Unit tests for the #15 degraded-mode warning: shown only when skeptic.receipts_unverified is present (> 0).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ReceiptsWarning } from "../AlertBits";
import { receiptsUnverifiedLine, type Skeptic } from "@/lib/alerts";

const base: Skeptic = { rounds: 1, struck: [], verdict: "approved", model_critique: "applied" };

describe("receiptsUnverifiedLine", () => {
  it("is null when the key is absent (every receipt verified), so prod alerts are unchanged", () => {
    expect(receiptsUnverifiedLine(base)).toBeNull();
    expect(receiptsUnverifiedLine(null)).toBeNull();
    expect(receiptsUnverifiedLine(undefined)).toBeNull();
  });
  it("is null for 0 or a non-count value", () => {
    expect(receiptsUnverifiedLine({ ...base, receipts_unverified: 0 })).toBeNull();
    expect(receiptsUnverifiedLine({ ...base, receipts_unverified: 1.5 })).toBeNull();
    expect(receiptsUnverifiedLine({ receipts_unverified: "2" as unknown as number })).toBeNull();
  });
  it("counts the unverified receipts, singular and plural", () => {
    expect(receiptsUnverifiedLine({ ...base, receipts_unverified: 1 })).toBe("1 model receipt unverified");
    expect(receiptsUnverifiedLine({ ...base, receipts_unverified: 3 })).toBe("3 model receipts unverified");
  });
});

describe("ReceiptsWarning", () => {
  it("renders nothing when every receipt verified", () => {
    expect(renderToStaticMarkup(<ReceiptsWarning skeptic={base} />)).toBe("");
    expect(renderToStaticMarkup(<ReceiptsWarning skeptic={null} />)).toBe("");
  });
  it("renders the warning with an explaining title when the key is present", () => {
    const html = renderToStaticMarkup(<ReceiptsWarning skeptic={{ ...base, receipts_unverified: 2 }} />);
    expect(html).toContain("2 model receipts unverified");
    expect(html).toContain("text-warn");
    expect(html).toContain("without a valid signed receipt");
  });
});

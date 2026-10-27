/**
 * Unit tests for BandPill: copy only. High keeps its short HIGH tag; medium reads "Lead · analyst review".
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BandPill } from "../AlertBits";
import { bandLabel } from "@/lib/alerts";

describe("bandLabel", () => {
  it("labels the medium band as a lead for analyst review, and leaves high alone", () => {
    expect(bandLabel("medium")).toBe("Lead · analyst review");
    expect(bandLabel("high")).toBe("High");
  });
});

describe("BandPill", () => {
  it("renders high as the uppercase mono HIGH tag (unchanged)", () => {
    const html = renderToStaticMarkup(<BandPill band="high" />);
    expect(html).toContain(">High<");
    expect(html).toContain("uppercase");
    expect(html).toContain("font-mono");
  });
  it("renders medium in sentence case, not shouted, with an explaining title", () => {
    const html = renderToStaticMarkup(<BandPill band="medium" />);
    expect(html).toContain("Lead · analyst review");
    expect(html).not.toContain("uppercase");
    expect(html).not.toContain("Medium<");
    expect(html).toContain('title="Medium band: a lead for an analyst to review, not a confirmed link"');
  });
});

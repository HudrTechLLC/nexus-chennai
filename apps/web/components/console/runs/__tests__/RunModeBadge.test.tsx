/**
 * Unit tests for RunModeBadge: the three states it can show.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { RunModeBadge } from "../RunModeBadge";

describe("RunModeBadge", () => {
  it("shows Live data for a run with sample mode off", () => {
    const html = renderToStaticMarkup(<RunModeBadge mode="live" />);
    expect(html).toContain("Live data");
    expect(html).toContain("sample mode off");
  });
  it("shows Sample mode, and says fallback was allowed rather than claiming sample data was used", () => {
    const html = renderToStaticMarkup(<RunModeBadge mode="sample" />);
    expect(html).toContain("Sample mode");
    expect(html).toContain("allowed to fall back");
  });
  it("says Mode not recorded when the run did not record the flag", () => {
    expect(renderToStaticMarkup(<RunModeBadge mode="unknown" />)).toContain("Mode not recorded");
  });
});

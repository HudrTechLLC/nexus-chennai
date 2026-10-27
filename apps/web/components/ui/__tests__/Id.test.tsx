/**
 * Unit tests for <Id>: shortening, and the hidden full-value copy staying contained (no page-wide overflow).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Id, shortId } from "../Id";

const UUID = "dab6ec9c-b95a-4301-9bba-435cc594e1c3";

describe("shortId", () => {
  it("keeps the head and tail of a UUID", () => {
    expect(shortId(UUID)).toBe("dab6ec9c…e1c3");
  });

  it("leaves short values alone", () => {
    expect(shortId("CHN-AD-2026-001212")).toBe("CHN-AD-2026-001212");
  });
});

describe("Id", () => {
  it("wraps a shortened value in a positioned span, so the sr-only copy cannot widen the page", () => {
    const html = renderToStaticMarkup(<Id value={UUID} />);
    expect(html).toMatch(/^<span title="dab6ec9c-[^"]+" class="relative /);
    expect(html).toContain('<span class="sr-only">dab6ec9c-b95a-4301-9bba-435cc594e1c3</span>');
  });

  it("renders a short value as plain text, with no hidden copy", () => {
    const html = renderToStaticMarkup(<Id value="CHN-AD-2026-001212" />);
    expect(html).not.toContain("sr-only");
  });
});

/**
 * Unit tests for the public map's "Areas with crimes" keyboard list.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AreaList } from "../AreaList";

const rows = [
  { cell: "88618c4885fffff", area: "Adyar", cards: 7, appeal: true },
  { cell: "88618c4581fffff", area: "Guindy", cards: 1, appeal: false },
];

describe("AreaList", () => {
  it("renders nothing when no hexagon has cards", () => {
    expect(renderToStaticMarkup(createElement(AreaList, { rows: [], selected: null, onOpen: () => {} }))).toBe("");
  });
  it("is a collapsible list of real buttons, one per hexagon, named for screen readers", () => {
    const html = renderToStaticMarkup(createElement(AreaList, { rows, selected: "88618c4885fffff", onOpen: () => {} }));
    expect(html).toContain("<details open");
    expect(html).toContain("Areas with crimes");
    expect((html.match(/<button type="button"/g) ?? []).length).toBe(2);
    expect(html).toContain('data-cell="88618c4885fffff"');
    expect(html).toContain('aria-label="Open cards for Adyar: 7 crimes, open police appeal"');
    expect(html).toContain('aria-label="Open cards for Guindy: 1 crime"');
    expect(html).toContain('aria-current="true"');
    expect(html).toContain("Open cards");
  });
});

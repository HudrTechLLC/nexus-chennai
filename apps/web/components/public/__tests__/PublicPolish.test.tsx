/**
 * Unit tests for the public visual polish: appeal cards keep their accessible names, every new icon is hidden
 * from assistive technology, and the map legend uses the map's own density ramp.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppealCard } from "../AppealCard";
import { CategoryBadge, CategoryMark } from "../CategoryIcon";
import { MapLegend } from "../MapLegend";
import type { Appeal } from "@/lib/publicData";

const appeal: Appeal = {
  id: "PI-2026-CC4470", title: "Chain snatching near a bus stop", category: "robbery", area: "Adyar",
  cell: "88618c4885fffff", week: "2026-W38", time_window: "Evening", summary: "s", looking_for: ["A red motorcycle"],
  images: [], tip_count: 2, published_at: null,
};

const svgs = (html: string) => html.match(/<svg[^>]*>/g) ?? [];

describe("AppealCard (polished)", () => {
  const html = renderToStaticMarkup(createElement(AppealCard, { a: appeal }));
  it("keeps the links and their accessible names", () => {
    expect(html).toContain('aria-label="Add a tip about this appeal: Chain snatching near a bus stop"');
    expect(html).toContain('aria-label="View location of this appeal on the crime map: Chain snatching near a bus stop"');
    expect(html).toContain('href="/appeals/PI-2026-CC4470"');
    expect(html).toContain("2 tips so far");
  });
  it("shows the category with an icon that screen readers skip", () => {
    expect(html).toContain("Robbery");
    expect(svgs(html).length).toBeGreaterThan(0);
    for (const s of svgs(html)) expect(s).toContain('aria-hidden="true"');
    expect(html).toContain("--cat-fg:#5b21b6");
  });
});

describe("category marks", () => {
  it("fall back quietly for an unknown category", () => {
    const html = renderToStaticMarkup(createElement(CategoryMark, { category: "arson" }));
    expect(html).toContain("--cat-fg:#475569");
    expect(renderToStaticMarkup(createElement(CategoryBadge, { category: "theft", label: "Theft" }))).toContain(">Theft</span>");
  });
});

describe("MapLegend", () => {
  it("explains the ramp, the appeal outline, the selection and the hiding threshold", () => {
    const html = renderToStaticMarkup(createElement(MapLegend, { minCount: 3 }));
    expect(html).toContain("linear-gradient(90deg, #fde68a 0%, #f97316 50%, #b91c1c 100%)");
    expect(html).toContain("Open police appeal");
    expect(html).toContain("Selected area");
    expect(html).toContain("fewer than 3 reports");
    for (const s of svgs(html)) expect(s).toContain('aria-hidden="true"');
  });
});

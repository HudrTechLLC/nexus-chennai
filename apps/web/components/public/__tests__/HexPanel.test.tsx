/**
 * Unit tests for HexPanel's empty state: a hexagon with no public cards offers the longest window.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HexPanel } from "../HexPanel";
import type { MapState } from "@/lib/publicCards";

const HEX = "88618c489dfffff";
const state = (days: 7 | 30 | 90): MapState => ({ days, type: null, hex: HEX, at: null });
const empty = { cell: HEX, days: 30, area: null, cards: [] };

describe("HexPanel empty state", () => {
  it("explains the >=3 rule and offers the last 90 days when the window is shorter", () => {
    const html = renderToStaticMarkup(<HexPanel state={state(30)} hex={empty} error={null} minCount={3} />);
    expect(html).toContain("at least 3 of the same");
    expect(html).toContain(`href="/map?days=90&amp;hex=${HEX}"`);
    expect(html).toContain("Show the last 90 days");
  });
  it("does not offer a longer window at 90 days", () => {
    const html = renderToStaticMarkup(<HexPanel state={state(90)} hex={{ ...empty, days: 90 }} error={null} minCount={3} />);
    expect(html).not.toContain("Show the last 90 days");
  });
});

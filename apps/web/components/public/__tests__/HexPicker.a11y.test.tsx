/**
 * Accessibility attributes on the /tip/new area picker (nexus-5 prod check): a labelled place search,
 * pressed state on the Large/Medium/Small buttons, and polite live regions for the hint and status text.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("maplibre-gl", () => ({ default: { Map: vi.fn() } }));

import { HexPicker } from "../HexPicker";
import { AREA_SIZES, DEFAULT_AREA_RES } from "@/lib/tipArea";

const html = (cell: string | null = null) => renderToStaticMarkup(<HexPicker cell={cell} onChange={() => {}} />);

describe("HexPicker accessibility", () => {
  it("labels the place search combobox", () => {
    expect(html()).toMatch(/<input[^>]*type="search"[^>]*aria-label="Search for a place near where it happened"/);
  });

  it("marks exactly the chosen size as pressed, as plain toggle buttons in a labelled group", () => {
    const out = html();
    expect(out).toContain('role="group" aria-label="Area size"');
    expect(out).not.toContain('role="radio"');
    const pressed = out.match(/aria-pressed="(true|false)"/g) ?? [];
    expect(pressed).toHaveLength(AREA_SIZES.length);
    expect(pressed.filter((p) => p.includes("true"))).toHaveLength(1);
    const def = AREA_SIZES.find((s) => s.res === DEFAULT_AREA_RES)!;
    expect(out).toMatch(new RegExp(`<button type="button" aria-pressed="true"[^>]*>${def.label}`));
  });

  it("keeps the zoom hint region mounted and polite, and announces the status text", () => {
    const out = html();
    expect(out).toMatch(/<div aria-live="polite" data-testid="area-hint">/);
    expect(out).toMatch(/<p class="text-xs text-muted" aria-live="polite">Search a place or tap the map/);
  });
});

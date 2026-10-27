/**
 * Unit tests for the AlertMap caption: the gold ANPR legend appears only when a trail is drawn.
 */
import { describe, expect, it } from "vitest";
import { mapCaption } from "@/lib/alertMap";

describe("mapCaption", () => {
  it("names the gold ANPR trail when camera reads are drawn", () => {
    expect(mapCaption(null, true)).toBe(
      "Red: scenes (hollow = area cell only) · gold: ANPR camera reads of the matched plate, joined in time order",
    );
  });

  it("leaves the gold part out when there is no trail (Ask Nexus map)", () => {
    const c = mapCaption(null, false);
    expect(c).toBe("Red: scenes (hollow = area cell only)");
    expect(c).not.toMatch(/gold|ANPR/);
  });

  it("shows the hovered scene label, marking area-cell centres", () => {
    expect(mapCaption({ kind: "scene", label: "CHN-AD-2026-001212", exact: true }, false)).toBe("CHN-AD-2026-001212");
    expect(mapCaption({ kind: "scene", label: "CHN-AD-2026-001212", exact: false }, false)).toBe("CHN-AD-2026-001212 (area cell centre)");
  });
});

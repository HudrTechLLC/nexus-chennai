/**
 * Unit tests for public appeal image URLs (PUB-02).
 */
import { describe, expect, it } from "vitest";
import { appealImageUrl, isSafeImagePath } from "../appealImages";

const BASE = "https://ukrujnsjucwvytnokbtw.supabase.co";

describe("appealImageUrl", () => {
  it("builds the public bucket URL from a checked path", () => {
    expect(appealImageUrl(BASE, "PI-2026-7C1EF3/a1b2c3.jpg"))
      .toBe(`${BASE}/storage/v1/object/public/appeal-public/PI-2026-7C1EF3/a1b2c3.jpg`);
  });
  it("refuses traversal, absolute and foreign paths", () => {
    for (const p of ["../x.jpg", "/PI-1/x.jpg", "https://evil.example/x.jpg", "PI-1/x.gif", "PI-1/a/b.jpg", "PI-1/x.jpg?y=1", 42, null]) {
      expect(isSafeImagePath(p)).toBe(false);
      expect(appealImageUrl(BASE, p)).toBeNull();
    }
  });
  it("needs an https base URL", () => {
    expect(appealImageUrl(undefined, "PI-1/x.jpg")).toBeNull();
    expect(appealImageUrl("http://localhost:54321", "PI-1/x.jpg")).toBeNull();
  });
});

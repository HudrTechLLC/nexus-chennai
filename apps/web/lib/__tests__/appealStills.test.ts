import { describe, expect, it } from "vitest";
import {
  APPEAL_BUCKET, attachable, attachProblem, BLUR_LABEL, MAX_STILLS, parseImages, publicStillUrl, stillPath, withoutStill, withStill,
  type EvidenceRow, type StillEntry,
} from "../appealStills";

const entry = (path: string, evidence_id = "EV-1"): StillEntry => ({
  path, blurred: true, method: "whole_image_downscale_v1", evidence_id, width: 640, height: 360, added_at: "2026-10-26T10:00:00Z",
});
const ev = (extra: Partial<EvidenceRow> = {}): EvidenceRow => ({
  evidence_id: "EV-1", crime_id: "CHN-AD-2024-001252", kind: "photo", storage_path: "CHN-AD-2024-001252/0b9c.jpg",
  captured_at: null, created_at: "t", ...extra,
});

describe("paths and URLs", () => {
  it("keys copies by appeal id, never by crime id", () => {
    const p = stillPath("PI-2026-ab12", "123e4567-e89b-12d3-a456-426614174000");
    expect(p).toBe("PI-2026-ab12/123e4567-e89b-12d3-a456-426614174000.jpg");
    expect(p).not.toMatch(/CHN-/);
  });
  it("builds the public URL from bucket + path", () => {
    expect(publicStillUrl("https://x.supabase.co/", "PI-1/u.jpg")).toBe(`https://x.supabase.co/storage/v1/object/public/${APPEAL_BUCKET}/PI-1/u.jpg`);
  });
  it("says plainly that there is no face or plate detection", () => {
    expect(BLUR_LABEL).toMatch(/No face or plate detection/);
  });
});

describe("parseImages", () => {
  it("keeps only blurred entries with a path", () => {
    expect(parseImages([entry("PI-1/a.jpg"), { path: "x", blurred: false }, { blurred: true }, "junk", null])).toHaveLength(1);
    expect(parseImages(null)).toEqual([]);
    expect(parseImages({})).toEqual([]);
  });
});

describe("attachable", () => {
  it("accepts JPEG/PNG stills and photos of this case only", () => {
    expect(attachable(ev(), "CHN-AD-2024-001252")).toBe(true);
    expect(attachable(ev({ kind: "cctv_still", storage_path: "C/x.PNG" }), "CHN-AD-2024-001252")).toBe(true);
    expect(attachable(ev({ crime_id: "CHN-VL-2026-000877" }), "CHN-AD-2024-001252")).toBe(false);
    expect(attachable(ev({ kind: "document" }), "CHN-AD-2024-001252")).toBe(false);
    expect(attachable(ev({ storage_path: "C/x.webp" }), "CHN-AD-2024-001252")).toBe(false);
    expect(attachable(ev(), null)).toBe(false);
  });
});

describe("attachProblem / list edits", () => {
  it("blocks withdrawn appeals, duplicates and more than the cap", () => {
    expect(attachProblem([], "EV-1", "withdrawn")).toMatch(/withdrawn/);
    expect(attachProblem([entry("PI-1/a.jpg", "EV-1")], "EV-1", "draft")).toMatch(/already/);
    const full = Array.from({ length: MAX_STILLS }, (_, i) => entry(`PI-1/${i}.jpg`, `EV-${i + 10}`));
    expect(attachProblem(full, "EV-1", "published")).toMatch(/at most/);
    expect(attachProblem([], "EV-1", "draft")).toBeNull();
  });
  it("adds and removes by path", () => {
    const a = entry("PI-1/a.jpg");
    const b = entry("PI-1/b.jpg", "EV-2");
    expect(withStill([a], b).map((x) => x.path)).toEqual(["PI-1/a.jpg", "PI-1/b.jpg"]);
    expect(withStill([a], a)).toHaveLength(1);
    expect(withoutStill([a, b], "PI-1/a.jpg").map((x) => x.path)).toEqual(["PI-1/b.jpg"]);
  });
});

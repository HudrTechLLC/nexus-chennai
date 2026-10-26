/**
 * Unit tests for evidence upload checks (lib/evidence.ts).
 */
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { checkEvidence, evidencePath, exifDateTime, MAX_EVIDENCE_BYTES, sha256Hex, sniffEvidence } from "../evidence";

const bytes = (...parts: (string | number[])[]) =>
  new Uint8Array(parts.flatMap((p) => (typeof p === "string" ? Array.from(p).map((c) => c.charCodeAt(0)) : p)));

/** A minimal JPEG whose EXIF holds DateTimeOriginal (big- or little-endian TIFF). */
function jpegWithExif(date: string, littleEndian = false): Uint8Array {
  const u16 = (n: number) => (littleEndian ? [n & 255, n >> 8] : [n >> 8, n & 255]);
  const u32 = (n: number) => (littleEndian ? [n & 255, (n >> 8) & 255, (n >> 16) & 255, n >>> 24] : [n >>> 24, (n >> 16) & 255, (n >> 8) & 255, n & 255]);
  // TIFF: header(8) | IFD0 at 8: 1 entry (ExifIFD ptr -> 26) | Exif IFD at 26: 1 entry (0x9003 -> 44) | date at 44
  const tiff = [
    ...(littleEndian ? [0x49, 0x49] : [0x4d, 0x4d]), ...u16(42), ...u32(8),
    ...u16(1), ...u16(0x8769), ...u16(4), ...u32(1), ...u32(26), ...u32(0),
    ...u16(1), ...u16(0x9003), ...u16(2), ...u32(20), ...u32(44), ...u32(0),
    ...Array.from(date + "\0").map((c) => c.charCodeAt(0)),
  ];
  const app1 = [...Array.from("Exif\0\0").map((c) => c.charCodeAt(0)), ...tiff];
  const len = app1.length + 2;
  return new Uint8Array([0xff, 0xd8, 0xff, 0xe1, len >> 8, len & 255, ...app1, 0xff, 0xda, 0, 2, 0xff, 0xd9]);
}

describe("sniffEvidence", () => {
  it("detects types from bytes", () => {
    expect(sniffEvidence(bytes([0xff, 0xd8, 0xff, 0xe0]))).toBe("image/jpeg");
    expect(sniffEvidence(bytes("%PDF-1.7"))).toBe("application/pdf");
    expect(sniffEvidence(bytes("RIFF", [0, 0, 0, 0], "WAVE"))).toBe("audio/wav");
    expect(sniffEvidence(bytes([0, 0, 0, 24], "ftyp", "isom"))).toBe("video/mp4");
    expect(sniffEvidence(bytes([0, 0, 0, 24], "ftyp", "M4A "))).toBe("audio/mp4");
    expect(sniffEvidence(bytes("hello"))).toBeNull();
  });
});

describe("checkEvidence", () => {
  const jpg = bytes([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3]);
  it("accepts a file that fits its kind", () => {
    expect(checkEvidence(jpg, "cctv_still")).toEqual({ mime: "image/jpeg", ext: "jpg" });
  });
  it("rejects a mismatched kind, unknown bytes, empty and oversize files", () => {
    expect(checkEvidence(jpg, "audio")).toHaveProperty("error");
    expect(checkEvidence(bytes("MZ executable"), "document")).toHaveProperty("error");
    expect(checkEvidence(new Uint8Array(0), "photo")).toHaveProperty("error");
    expect(checkEvidence(new Uint8Array(MAX_EVIDENCE_BYTES + 1).fill(0xff), "photo")).toHaveProperty("error");
    expect(checkEvidence(jpg, "selfie")).toHaveProperty("error");
  });
});

describe("integrity", () => {
  it("sha256Hex equals Node's sha256 of the same original bytes", async () => {
    const b = jpegWithExif("2026:10:25 18:20:05");
    expect(await sha256Hex(b)).toBe(createHash("sha256").update(b).digest("hex"));
  });
  it("builds the bucket key from the crime id", () => {
    expect(evidencePath("CHN-AD-2026-001231", "3f2a", "jpg")).toBe("CHN-AD-2026-001231/3f2a.jpg");
  });
});

describe("exifDateTime", () => {
  it("reads DateTimeOriginal in both byte orders", () => {
    expect(exifDateTime(jpegWithExif("2026:10:25 18:20:05"))).toBe("2026-10-25T18:20:05");
    expect(exifDateTime(jpegWithExif("2026:10:25 18:20:05", true))).toBe("2026-10-25T18:20:05");
  });
  it("returns null without EXIF or for non-JPEG files", () => {
    expect(exifDateTime(bytes([0xff, 0xd8, 0xff, 0xda, 0, 2]))).toBeNull();
    expect(exifDateTime(bytes("%PDF-1.7"))).toBeNull();
  });
});

describe("EXIF capture time to captured_at", () => {
  it("passes the full EXIF time, seconds included, to the city-time conversion", async () => {
    const { cityLocalToIso } = await import("../fir");
    const local = exifDateTime(jpegWithExif("2026:10:20 19:44:12"));
    expect(local).toBe("2026-10-20T19:44:12");
    expect(cityLocalToIso(local as string, "Asia/Kolkata")).toBe("2026-10-20T14:14:12.000Z");
  });
});

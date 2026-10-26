import { describe, expect, it } from "vitest";
import {
  CODE_ALPHABET, formatTipCode, generateTipCode, imageHasMetadata, leadingZeroBits, normaliseTipCode, sniffType,
  solvePow, validateTip, verifyPow, type TipInput,
} from "../tip";

const base: TipInput = { category: "vehicle_seen", text: "Red bike near the tea shop", cell: null, followUp: false, code: null, passphrase: null, appeal: null };

describe("tip code", () => {
  it("is 8 symbols from the readable alphabet", () => {
    for (let i = 0; i < 50; i++) {
      const c = generateTipCode();
      expect(c).toMatch(/^[A-HJ-NP-Z2-9]{8}$/);
      expect(Array.from(c).every((ch) => CODE_ALPHABET.includes(ch))).toBe(true);
    }
  });
  it("formats and normalises", () => {
    expect(formatTipCode("8F3K2QWA")).toBe("8F3K·2QWA");
    expect(normaliseTipCode("8f3k·2qwa")).toBe("8F3K2QWA");
    expect(normaliseTipCode("8f3k 2qwa")).toBe("8F3K2QWA");
    expect(normaliseTipCode("0O1I2345")).toBeNull();
    expect(normaliseTipCode("short")).toBeNull();
  });
});

describe("validateTip", () => {
  it("accepts a minimal anonymous tip", () => expect(validateTip(base)).toBeNull());
  it("rejects unknown categories and tiny text", () => {
    expect(validateTip({ ...base, category: "hack" })).toMatch(/Choose/);
    expect(validateTip({ ...base, text: " a " })).toMatch(/more/);
  });
  it("only accepts H3 r8 cells", () => {
    expect(validateTip({ ...base, cell: "88618c4d9dfffff" })).toBeNull();
    expect(validateTip({ ...base, cell: "89618c4d9dfffff" })).toMatch(/area/);
  });
  it("needs code and passphrase for follow-up", () => {
    expect(validateTip({ ...base, followUp: true, code: "ABCD2345", passphrase: "short" })).toMatch(/passphrase/);
    expect(validateTip({ ...base, followUp: true, code: "ABCD2345", passphrase: "long enough pass" })).toBeNull();
  });
});

// Minimal byte fixtures
const jpegWithExif = new Uint8Array([0xff, 0xd8, 0xff, 0xe1, 0x00, 0x10, ...Array.from("Exif\0\0").map((c) => c.charCodeAt(0)), 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xda]);
const jpegClean = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, ...Array.from("JFIF\0").map((c) => c.charCodeAt(0)), 1, 1, 0, 0, 1, 0, 1, 0, 0, 0xff, 0xda]);
const pngChunk = (type: string, data: number[] = []) => [0, 0, 0, data.length, ...Array.from(type).map((c) => c.charCodeAt(0)), ...data, 0, 0, 0, 0];
const png = (chunks: number[][]) => new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, ...chunks.flat()]);

describe("imageHasMetadata", () => {
  it("finds EXIF in JPEG and passes a clean JFIF", () => {
    expect(imageHasMetadata(jpegWithExif)).toBe(true);
    expect(imageHasMetadata(jpegClean)).toBe(false);
  });
  it("finds eXIf/tEXt in PNG", () => {
    expect(imageHasMetadata(png([pngChunk("IHDR", Array(13).fill(0)), pngChunk("eXIf", [1, 2]), pngChunk("IEND")]))).toBe(true);
    expect(imageHasMetadata(png([pngChunk("IHDR", Array(13).fill(0)), pngChunk("IDAT", [1]), pngChunk("IEND")]))).toBe(false);
  });
  it("treats unknown bytes as unsafe", () => expect(imageHasMetadata(new Uint8Array([1, 2, 3, 4]))).toBe(true));
});

describe("sniffType", () => {
  it("recognises the allowed types", () => {
    expect(sniffType(jpegClean)).toBe("image/jpeg");
    expect(sniffType(png([pngChunk("IEND")]))).toBe("image/png");
    expect(sniffType(new Uint8Array([0x4f, 0x67, 0x67, 0x53]))).toBe("audio/ogg");
    expect(sniffType(new Uint8Array([0x3c, 0x73, 0x76, 0x67]))).toBeNull(); // "<svg"
  });
});

describe("proof of work", () => {
  it("counts leading zero bits", () => {
    expect(leadingZeroBits(new Uint8Array([0, 0x0f]))).toBe(12);
    expect(leadingZeroBits(new Uint8Array([0x80]))).toBe(0);
  });
  it("solves and verifies, and rejects stale or forged tokens", async () => {
    const now = Date.now();
    const token = await solvePow(now, "abcdefgh", 8);
    expect(await verifyPow(token, now, 8)).toBe(true);
    expect(await verifyPow(token, now + 11 * 60_000, 8)).toBe(false);
    expect(await verifyPow(`${now}:abcdefgh:999999999`, now, 24)).toBe(false);
    expect(await verifyPow("garbage", now, 8)).toBe(false);
  });
});

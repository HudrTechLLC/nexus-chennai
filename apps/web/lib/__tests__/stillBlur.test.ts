import { describe, expect, it } from "vitest";
import jpeg from "jpeg-js";
import { PNG } from "pngjs";
import { BLUR_METHOD, blurStill, boxBlur, decode, hasMetadata, shrink, sniff, StillError } from "../stillBlur";

/** A high-detail test card: 1-px black/white checkerboard plus a white "plate" box with black bars. */
function card(w: number, h: number): Uint8Array {
  const d = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    let v = (x + y) % 2 ? 255 : 0;
    if (x > w * 0.3 && x < w * 0.7 && y > h * 0.4 && y < h * 0.6) v = x % 6 < 3 ? 0 : 255; // "plate" characters
    d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255;
  }
  return d;
}

/** A JPEG with a fake EXIF APP1 segment (GPS-like text) spliced in after SOI. */
function jpegWithExif(w = 400, h = 300): Buffer {
  const base = Buffer.from(jpeg.encode({ width: w, height: h, data: card(w, h) }, 95).data);
  const payload = Buffer.from("Exif\0\0GPSLatitude 13.0067 GPSLongitude 80.2206 Make SECRETCAM", "latin1");
  const len = payload.length + 2;
  const app1 = Buffer.concat([Buffer.from([0xff, 0xe1, len >> 8, len & 0xff]), payload]);
  return Buffer.concat([base.subarray(0, 2), app1, base.subarray(2)]);
}

/** Mean absolute difference between horizontally adjacent pixels (sharpness proxy). */
function edgeEnergy(img: { width: number; height: number; data: Uint8Array }): number {
  let s = 0, n = 0;
  for (let y = 0; y < img.height; y++) for (let x = 1; x < img.width; x++) {
    const i = (y * img.width + x) * 4;
    s += Math.abs(img.data[i] - img.data[i - 4]); n++;
  }
  return s / n;
}

describe("sniff", () => {
  it("reads the real type from the bytes", () => {
    expect(sniff(jpegWithExif(16, 16))).toBe("jpeg");
    expect(sniff(PNG.sync.write(Object.assign(new PNG({ width: 2, height: 2 }), {})))).toBe("png");
    expect(sniff(Buffer.from("RIFF0000WEBPVP8 ", "latin1"))).toBe("webp");
    expect(sniff(Buffer.from("%PDF-1.7"))).toBeNull();
  });
});

describe("blurStill", () => {
  const original = jpegWithExif();

  it("the test fixture really carries EXIF", () => {
    expect(hasMetadata(original)).toBe(true);
  });

  it("strips all metadata and re-encodes", () => {
    const out = blurStill(original);
    expect(out.method).toBe(BLUR_METHOD);
    expect(hasMetadata(out.jpeg)).toBe(false);
    expect(out.jpeg.includes("GPSLatitude")).toBe(false);
    expect(out.jpeg.includes("SECRETCAM")).toBe(false);
    expect(sniff(out.jpeg)).toBe("jpeg");
  });

  it("destroys fine detail (checkerboard and plate bars become near-uniform)", () => {
    const before = decode(original);
    const after = decode(blurStill(original).jpeg);
    expect(edgeEnergy(before)).toBeGreaterThan(100);
    expect(edgeEnergy(after)).toBeLessThan(3);
  });

  it("keeps the aspect ratio, caps the size, and stays small", () => {
    const out = blurStill(jpegWithExif(1600, 900));
    expect(out.width).toBe(640);
    expect(out.height).toBe(360);
    expect(out.jpeg.length).toBeLessThan(300 * 1024);
    const tall = blurStill(jpegWithExif(300, 600));
    expect(tall.height).toBe(600);
    expect(tall.width).toBe(300);
  });

  it("accepts PNG and blurs it the same way", () => {
    const png = new PNG({ width: 200, height: 120 });
    png.data = Buffer.from(card(200, 120));
    const out = blurStill(PNG.sync.write(png));
    expect(hasMetadata(out.jpeg)).toBe(false);
    expect(edgeEnergy(decode(out.jpeg))).toBeLessThan(3);
  });

  it("refuses WebP, unknown types, tiny and oversized inputs with a clear message", () => {
    expect(() => blurStill(Buffer.from("RIFF0000WEBPVP8 xxxxxxxx", "latin1"))).toThrow(/WebP/);
    expect(() => blurStill(Buffer.from("%PDF-1.7 not an image"))).toThrow(StillError);
    expect(() => blurStill(jpegWithExif(4, 4))).toThrow(/too small/);
    expect(() => blurStill(Buffer.alloc(4 * 1024 * 1024 + 1))).toThrow(/4 MB/);
  });
});

describe("building blocks", () => {
  it("shrink averages every source pixel", () => {
    // plain 4×2 checkerboard: four black and four white pixels average to 127.5
    const data = new Uint8Array(4 * 2 * 4);
    for (let p = 0; p < 8; p++) { const v = (p + Math.floor(p / 4)) % 2 ? 255 : 0; data.set([v, v, v, 255], p * 4); }
    const s = shrink({ width: 4, height: 2, data }, 1);
    expect([s.width, s.height]).toEqual([1, 1]);
    expect(s.data[0]).toBe(127);
  });
  it("boxBlur with radius 0 is the identity", () => {
    const img = { width: 3, height: 3, data: card(3, 3) };
    expect(boxBlur(img, 0)).toBe(img);
  });
});

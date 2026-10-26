/**
 * Whole-image anonymising blur for public appeal stills (spec PUB-02, J1; WS4-09).
 *
 * Method `whole_image_downscale_v1`: decode → shrink hard (long side 48 px, area-averaged) →
 * enlarge back to at most 640 px (bilinear) → smooth → re-encode as a fresh baseline JPEG.
 * Shrinking throws the detail away, so faces and plates cannot be recovered; this is NOT face or
 * plate detection, and the UI says so. Because the output is re-encoded from pixels, no EXIF, GPS,
 * XMP or other metadata from the original can survive.
 *
 * Pure (Buffer in, Buffer out). Imported only by the appeal stills server action, never by client code.
 */

import jpeg from "jpeg-js";
import { PNG } from "pngjs";

export const BLUR_METHOD = "whole_image_downscale_v1";
export const SMALL_SIDE = 48; // long side of the shrunk image: the information that survives
export const OUT_MAX = 640; // long side of the published image
export const MAX_INPUT_BYTES = 4 * 1024 * 1024; // the evidence bucket's own limit
export const MAX_MEGAPIXELS = 40;

export type Rgba = { width: number; height: number; data: Uint8Array };
export type BlurResult = { jpeg: Buffer; width: number; height: number; method: typeof BLUR_METHOD };

export class StillError extends Error {}

/** Sniffs the real file type from its bytes (never trust the extension). */
export function sniff(buf: Uint8Array): "jpeg" | "png" | "webp" | null {
  if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return "jpeg";
  if (buf.length > 8 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return "png";
  if (buf.length > 12 && String.fromCharCode(...Array.from(buf.subarray(0, 4))) === "RIFF" && String.fromCharCode(...Array.from(buf.subarray(8, 12))) === "WEBP") return "webp";
  return null;
}

/** Decodes a JPEG or PNG to RGBA with memory and size caps. */
export function decode(buf: Buffer): Rgba {
  if (buf.length > MAX_INPUT_BYTES) throw new StillError("The still is larger than 4 MB.");
  const kind = sniff(buf);
  if (kind === "webp") throw new StillError("WebP stills are not supported yet. Upload the still as JPEG or PNG.");
  if (kind === "jpeg") {
    const img = jpeg.decode(buf, { useTArray: true, formatAsRGBA: true, maxResolutionInMP: MAX_MEGAPIXELS, maxMemoryUsageInMB: 512 });
    return { width: img.width, height: img.height, data: img.data };
  }
  if (kind === "png") {
    const img = PNG.sync.read(buf);
    if ((img.width * img.height) / 1e6 > MAX_MEGAPIXELS) throw new StillError("The still is too large.");
    return { width: img.width, height: img.height, data: new Uint8Array(img.data.buffer, img.data.byteOffset, img.data.length) };
  }
  throw new StillError("Only JPEG and PNG stills can be attached.");
}

/** Area-average downscale so every source pixel contributes (no aliasing that could keep a sharp edge). */
export function shrink(src: Rgba, targetLong = SMALL_SIDE): Rgba {
  const scale = Math.min(1, targetLong / Math.max(src.width, src.height));
  const w = Math.max(1, Math.round(src.width * scale));
  const h = Math.max(1, Math.round(src.height * scale));
  const out = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) {
    const y0 = Math.floor((y * src.height) / h);
    const y1 = Math.max(y0 + 1, Math.floor(((y + 1) * src.height) / h));
    for (let x = 0; x < w; x++) {
      const x0 = Math.floor((x * src.width) / w);
      const x1 = Math.max(x0 + 1, Math.floor(((x + 1) * src.width) / w));
      let r = 0, g = 0, b = 0, n = 0;
      for (let sy = y0; sy < y1; sy++) {
        let i = (sy * src.width + x0) * 4;
        for (let sx = x0; sx < x1; sx++, i += 4) {
          r += src.data[i]; g += src.data[i + 1]; b += src.data[i + 2]; n++;
        }
      }
      const o = (y * w + x) * 4;
      out[o] = r / n; out[o + 1] = g / n; out[o + 2] = b / n; out[o + 3] = 255;
    }
  }
  return { width: w, height: h, data: out };
}

/** Bilinear enlarge (smooth, so the shrunk image does not show as blocks that read as pixelation). */
export function enlarge(src: Rgba, targetLong: number, aspect: number): Rgba {
  const w = aspect >= 1 ? targetLong : Math.max(1, Math.round(targetLong * aspect));
  const h = aspect >= 1 ? Math.max(1, Math.round(targetLong / aspect)) : targetLong;
  const out = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) {
    const fy = Math.max(0, Math.min(src.height - 1, ((y + 0.5) * src.height) / h - 0.5));
    const y0 = Math.floor(fy), y1 = Math.min(src.height - 1, y0 + 1), ty = fy - y0;
    for (let x = 0; x < w; x++) {
      const fx = Math.max(0, Math.min(src.width - 1, ((x + 0.5) * src.width) / w - 0.5));
      const x0 = Math.floor(fx), x1 = Math.min(src.width - 1, x0 + 1), tx = fx - x0;
      const o = (y * w + x) * 4;
      for (let c = 0; c < 3; c++) {
        const a = src.data[(y0 * src.width + x0) * 4 + c] * (1 - tx) + src.data[(y0 * src.width + x1) * 4 + c] * tx;
        const b = src.data[(y1 * src.width + x0) * 4 + c] * (1 - tx) + src.data[(y1 * src.width + x1) * 4 + c] * tx;
        out[o + c] = a * (1 - ty) + b * ty;
      }
      out[o + 3] = 255;
    }
  }
  return { width: w, height: h, data: out };
}

/** Separable box blur (radius in px), applied after enlarging to soften any remaining edges. */
export function boxBlur(src: Rgba, radius: number): Rgba {
  if (radius < 1) return src;
  const { width: w, height: h } = src;
  const tmp = new Uint8Array(src.data.length);
  const out = new Uint8Array(src.data.length);
  const pass = (from: Uint8Array, to: Uint8Array, horizontal: boolean) => {
    const lines = horizontal ? h : w, len = horizontal ? w : h;
    for (let l = 0; l < lines; l++) {
      for (let c = 0; c < 3; c++) {
        let sum = 0;
        const at = (k: number) => {
          const kk = Math.max(0, Math.min(len - 1, k));
          return from[(horizontal ? l * w + kk : kk * w + l) * 4 + c];
        };
        for (let k = -radius; k <= radius; k++) sum += at(k);
        for (let k = 0; k < len; k++) {
          to[(horizontal ? l * w + k : k * w + l) * 4 + c] = sum / (2 * radius + 1);
          sum += at(k + radius + 1) - at(k - radius);
        }
      }
      for (let k = 0; k < len; k++) to[(horizontal ? l * w + k : k * w + l) * 4 + 3] = 255;
    }
  };
  pass(src.data, tmp, true);
  pass(tmp, out, false);
  return { width: w, height: h, data: out };
}

/** The whole pipeline: original bytes → anonymised JPEG with no metadata. */
export function blurStill(original: Buffer): BlurResult {
  const img = decode(original);
  if (img.width < 8 || img.height < 8) throw new StillError("The still is too small to use.");
  const aspect = img.width / img.height;
  const small = shrink(img, SMALL_SIDE);
  const longOut = Math.min(OUT_MAX, Math.max(img.width, img.height));
  const big = enlarge(small, longOut, aspect);
  const soft = boxBlur(big, Math.max(2, Math.round(longOut / SMALL_SIDE / 2)));
  const enc = jpeg.encode({ width: soft.width, height: soft.height, data: soft.data }, 72);
  return { jpeg: Buffer.from(enc.data), width: soft.width, height: soft.height, method: BLUR_METHOD };
}

/** True if the bytes contain an APP1 (EXIF/XMP) segment or an "Exif" marker; used by tests and as a final guard. */
export function hasMetadata(buf: Uint8Array): boolean {
  for (let i = 2; i + 4 < buf.length; i++) {
    if (buf[i] === 0xff && buf[i + 1] === 0xe1) return true; // APP1
    if (buf[i] === 0xff && buf[i + 1] === 0xda) break; // start of scan: headers are over
  }
  return Buffer.from(buf).includes("Exif");
}

/**
 * Police evidence upload (spec G4 "Evidence upload", D3.4; chief's decision 26 Oct): the ORIGINAL bytes
 * are kept (no re-encoding, no EXIF stripping), hashed with sha256 on the server, and the capture
 * time is read from EXIF when present. Public appeal images strip metadata on a separate path.
 */
import { sniffType } from "@/lib/tip";

// =====================
// Limits and kinds
// =====================

/** Vercel caps a function request body at about 4.5 MB; 4 MB leaves room for the form fields. */
export const MAX_EVIDENCE_BYTES = 4 * 1024 * 1024;

export const EVIDENCE_KINDS = ["cctv_still", "cctv_clip", "photo", "scan", "audio", "document"] as const;
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

/** Media types the `evidence` bucket accepts (0007_02 allowed_mime_types) and their file extension. */
export const EVIDENCE_TYPES: Record<string, { ext: string; kinds: EvidenceKind[] }> = {
  "image/jpeg": { ext: "jpg", kinds: ["cctv_still", "photo", "scan"] },
  "image/png": { ext: "png", kinds: ["cctv_still", "photo", "scan"] },
  "image/webp": { ext: "webp", kinds: ["cctv_still", "photo", "scan"] },
  "application/pdf": { ext: "pdf", kinds: ["scan", "document"] },
  "video/mp4": { ext: "mp4", kinds: ["cctv_clip"] },
  "audio/mpeg": { ext: "mp3", kinds: ["audio"] },
  "audio/mp4": { ext: "m4a", kinds: ["audio"] },
  "audio/ogg": { ext: "ogg", kinds: ["audio"] },
  "audio/webm": { ext: "webm", kinds: ["audio"] },
  "audio/wav": { ext: "wav", kinds: ["audio"] },
};

const ascii = (b: Uint8Array, at: number, len: number) => String.fromCharCode.apply(null, Array.from(b.subarray(at, at + len)));

/** Media type from the file's own bytes (never the browser's claim). */
export function sniffEvidence(b: Uint8Array): string | null {
  if (ascii(b, 0, 5) === "%PDF-") return "application/pdf";
  if (ascii(b, 0, 4) === "RIFF" && ascii(b, 8, 4) === "WAVE") return "audio/wav";
  if (ascii(b, 4, 4) === "ftyp") {
    const brand = ascii(b, 8, 4);
    return brand === "M4A " || brand === "M4B " ? "audio/mp4" : "video/mp4";
  }
  return sniffType(b);
}

/** Null when the bytes fit the chosen kind, else the reason. */
export function checkEvidence(b: Uint8Array, kind: string): { mime: string; ext: string } | { error: string } {
  if (b.length === 0) return { error: "The file is empty." };
  if (b.length > MAX_EVIDENCE_BYTES) return { error: "Files must be 4 MB or smaller." };
  if (!(EVIDENCE_KINDS as readonly string[]).includes(kind)) return { error: "Choose what kind of evidence this is." };
  const mime = sniffEvidence(b);
  if (!mime || !EVIDENCE_TYPES[mime]) return { error: "Use a JPEG, PNG, WebP, PDF, MP4 or audio file." };
  if (!EVIDENCE_TYPES[mime].kinds.includes(kind as EvidenceKind)) return { error: `A ${mime} file cannot be filed as ${kind.replace(/_/g, " ")}.` };
  return { mime, ext: EVIDENCE_TYPES[mime].ext };
}

// =====================
// Integrity
// =====================

export async function sha256Hex(b: Uint8Array): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", b as Uint8Array<ArrayBuffer>));
  return Array.from(d).map((x) => x.toString(16).padStart(2, "0")).join("");
}

/** Object key in the bucket: <crime_id>/<uuid>.<ext>. Storage policies read the crime id from it. */
export function evidencePath(crimeId: string, id: string, ext: string): string {
  return `${crimeId}/${id}.${ext}`;
}

export type CustodyStep = { at: string; by: string; action: "uploaded"; sha256: string; bytes: number; mime: string };

// =====================
// EXIF capture time (JPEG)
// =====================

/**
 * DateTimeOriginal (or DateTime) from a JPEG's EXIF block, as "YYYY-MM-DDTHH:mm:ss" camera-local time,
 * or null. Read-only: the file is stored unchanged.
 */
export function exifDateTime(b: Uint8Array): string | null {
  if (b[0] !== 0xff || b[1] !== 0xd8) return null;
  let p = 2;
  while (p + 4 < b.length && b[p] === 0xff) {
    const marker = b[p + 1];
    const len = (b[p + 2] << 8) | b[p + 3];
    if (marker === 0xe1 && ascii(b, p + 4, 4) === "Exif") return readTiffDate(b, p + 10);
    if (marker === 0xda) break; // start of scan: no more metadata
    p += 2 + len;
  }
  return null;
}

function readTiffDate(b: Uint8Array, t: number): string | null {
  const le = ascii(b, t, 2) === "II";
  const u16 = (o: number) => (le ? b[t + o] | (b[t + o + 1] << 8) : (b[t + o] << 8) | b[t + o + 1]);
  const u32 = (o: number) => (le ? (b[t + o] | (b[t + o + 1] << 8) | (b[t + o + 2] << 16)) + b[t + o + 3] * 2 ** 24 : b[t + o] * 2 ** 24 + ((b[t + o + 1] << 16) | (b[t + o + 2] << 8) | b[t + o + 3]));
  const readIfd = (off: number): Record<number, number> => {
    const out: Record<number, number> = {};
    if (t + off + 2 > b.length) return out;
    const n = u16(off);
    for (let i = 0; i < n && t + off + 2 + i * 12 + 12 <= b.length; i++) {
      const e = off + 2 + i * 12;
      out[u16(e)] = u32(e + 8);
    }
    return out;
  };
  const str = (off: number) => ascii(b, t + off, 19);
  const ifd0 = readIfd(u32(4));
  const exif = ifd0[0x8769] ? readIfd(ifd0[0x8769]) : {};
  const off = exif[0x9003] ?? ifd0[0x0132];
  if (!off || t + off + 19 > b.length) return null;
  const m = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(str(off));
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}` : null;
}

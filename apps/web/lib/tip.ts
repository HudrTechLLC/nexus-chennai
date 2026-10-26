/**
 * Tip intake helpers shared by the browser form and the route handler (spec G1, J1, D3.6).
 * Pure functions plus WebCrypto (available in browsers and Node 20), so they are unit-tested.
 */

// =====================
// Categories
// =====================

export const TIP_CATEGORIES = ["vehicle_seen", "person_seen", "have_cctv", "item_for_sale", "something_else"] as const;
export type TipCategory = (typeof TIP_CATEGORIES)[number];
export const TIP_CATEGORY_LABEL: Record<TipCategory, string> = {
  vehicle_seen: "Vehicle seen",
  person_seen: "Person seen",
  have_cctv: "I have CCTV",
  item_for_sale: "Stolen item offered for sale",
  something_else: "Something else",
};

// =====================
// Tip code (shown once; it becomes the tip id)
// =====================

/** No 0/O/1/I, so codes are easy to read back. Must match the submit_tip check. */
export const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export function generateTipCode(rand: (n: number) => Uint8Array = (n) => crypto.getRandomValues(new Uint8Array(n))): string {
  // rejection sampling keeps the distribution uniform (32 symbols divide 256 evenly, but stay general)
  const out: string[] = [];
  while (out.length < 8) {
    for (const b of Array.from(rand(16))) {
      if (b < 256 - (256 % CODE_ALPHABET.length)) out.push(CODE_ALPHABET[b % CODE_ALPHABET.length]);
      if (out.length === 8) break;
    }
  }
  return out.join("");
}

/** "8F3K2QWA" → "8F3K·2QWA". */
export function formatTipCode(code: string): string {
  return code.length === 8 ? `${code.slice(0, 4)}·${code.slice(4)}` : code;
}

/** Accepts what a person types back ("8f3k 2qwa", "8F3K·2QWA") and returns the bare code, or null. */
export function normaliseTipCode(input: string): string | null {
  const c = input.toUpperCase().replace(/[\s·.\-]/g, "");
  return /^[A-HJ-NP-Z2-9]{8}$/.test(c) ? c : null;
}

// =====================
// Validation (mirrors submit_tip)
// =====================

export type TipInput = {
  category: string;
  text: string;
  cell: string | null;
  followUp: boolean;
  code: string | null;
  passphrase: string | null;
  appeal: string | null;
  /** Public crime-card id (WS4-12 ?about=, 0007_11); optional so older callers stay valid. */
  about?: string | null;
};

/** Public crime-card id: "PC-" + 12 hex digits (0007_11 crime_public_id). */
export const PUBLIC_CRIME_ID_RE = /^PC-[0-9A-F]{12}$/;

export function validateTip(t: TipInput): string | null {
  if (!(TIP_CATEGORIES as readonly string[]).includes(t.category)) return "Choose what you saw.";
  const len = t.text.trim().length;
  if (len < 3) return "Tell us a little more (at least a few words).";
  if (t.text.length > 4000) return "Keep it under 4000 characters.";
  if (t.cell !== null && !/^88[0-9a-f]{13}$/.test(t.cell)) return "Pick the area again.";
  if (t.appeal !== null && !/^[A-Za-z0-9-]{1,40}$/.test(t.appeal)) return "Unknown appeal.";
  if (t.about != null && !PUBLIC_CRIME_ID_RE.test(t.about)) return "Unknown crime.";
  if (t.followUp) {
    if (!t.code || !/^[A-HJ-NP-Z2-9]{8}$/.test(t.code)) return "Tip code missing.";
    if (!t.passphrase || t.passphrase.length < 8) return "Choose a passphrase of at least 8 characters.";
    if (t.passphrase.length > 128) return "Passphrase is too long.";
  }
  return null;
}

// =====================
// Files: allowed types and a server-side metadata double-check (J1)
// =====================

export const MAX_FILES = 5;
export const MAX_FILE_BYTES = 15 * 1024 * 1024;

export const FILE_TYPES: Record<string, { ext: string; kind: "image" | "audio" }> = {
  "image/jpeg": { ext: "jpg", kind: "image" },
  "image/png": { ext: "png", kind: "image" },
  "image/webp": { ext: "webp", kind: "image" },
  "audio/mpeg": { ext: "mp3", kind: "audio" },
  "audio/mp4": { ext: "m4a", kind: "audio" },
  "audio/ogg": { ext: "ogg", kind: "audio" },
  "audio/webm": { ext: "webm", kind: "audio" },
};

const ascii = (b: Uint8Array, at: number, len: number) => String.fromCharCode(...Array.from(b.subarray(at, at + len)));

/**
 * True when an image still carries EXIF/XMP metadata (which can hold GPS): JPEG APP1 "Exif"/XMP,
 * PNG eXIf/tEXt/iTXt/zTXt chunks, WebP EXIF/XMP chunks. The browser re-encodes images through a
 * canvas, which drops all of these; the server rejects any file where they survive.
 */
export function imageHasMetadata(b: Uint8Array): boolean {
  if (b.length >= 4 && b[0] === 0xff && b[1] === 0xd8) {
    let i = 2;
    while (i + 4 <= b.length && b[i] === 0xff) {
      const marker = b[i + 1];
      if (marker === 0xda || marker === 0xd9) break; // start of scan / end
      const len = (b[i + 2] << 8) | b[i + 3];
      if (marker === 0xe1) {
        const tag = ascii(b, i + 4, 29);
        if (tag.startsWith("Exif") || tag.startsWith("http://ns.adobe.com/xap")) return true;
      }
      i += 2 + len;
    }
    return false;
  }
  if (b.length >= 8 && b[0] === 0x89 && ascii(b, 1, 3) === "PNG") {
    let i = 8;
    while (i + 8 <= b.length) {
      const len = ((b[i] << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3]) >>> 0;
      const type = ascii(b, i + 4, 4);
      if (["eXIf", "tEXt", "iTXt", "zTXt"].includes(type)) return true;
      if (type === "IEND") break;
      i += 12 + len;
    }
    return false;
  }
  if (b.length >= 12 && ascii(b, 0, 4) === "RIFF" && ascii(b, 8, 4) === "WEBP") {
    let i = 12;
    while (i + 8 <= b.length) {
      const type = ascii(b, i, 4);
      const len = (b[i + 4] | (b[i + 5] << 8) | (b[i + 6] << 16) | (b[i + 7] << 24)) >>> 0;
      if (type === "EXIF" || type === "XMP ") return true;
      i += 8 + len + (len & 1);
    }
    return false;
  }
  return true; // not a recognised image: treat as unsafe
}

/** Sniff the real type from the first bytes (never trust the declared MIME type alone). */
export function sniffType(b: Uint8Array): string | null {
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b[0] === 0x89 && ascii(b, 1, 3) === "PNG") return "image/png";
  if (ascii(b, 0, 4) === "RIFF" && ascii(b, 8, 4) === "WEBP") return "image/webp";
  if (ascii(b, 0, 3) === "ID3" || (b[0] === 0xff && (b[1] & 0xe0) === 0xe0)) return "audio/mpeg";
  if (ascii(b, 4, 4) === "ftyp") return "audio/mp4";
  if (ascii(b, 0, 4) === "OggS") return "audio/ogg";
  if (b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3) return "audio/webm";
  return null;
}

// =====================
// Proof of work (throttling without identity, J1)
// =====================

export const POW_BITS = 16;
export const POW_MAX_AGE_MS = 10 * 60_000;

async function sha256(s: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
}

export function leadingZeroBits(h: Uint8Array): number {
  let n = 0;
  for (const byte of Array.from(h)) {
    if (byte === 0) { n += 8; continue; }
    return n + Math.clz32(byte) - 24;
  }
  return n;
}

/** Find a nonce so that sha256(`${stamp}:${salt}:${nonce}`) starts with `bits` zero bits. */
export async function solvePow(stamp: number, salt: string, bits = POW_BITS): Promise<string> {
  for (let nonce = 0; ; nonce++) {
    if (leadingZeroBits(await sha256(`${stamp}:${salt}:${nonce}`)) >= bits) return `${stamp}:${salt}:${nonce}`;
  }
}

/** Server check: fresh stamp, well-formed, enough work. Replays are caught by the caller's seen-set. */
export async function verifyPow(token: string, now = Date.now(), bits = POW_BITS): Promise<boolean> {
  const m = /^(\d{13}):([A-Za-z0-9]{8,32}):(\d{1,10})$/.exec(token ?? "");
  if (!m) return false;
  const stamp = Number(m[1]);
  if (stamp > now + 60_000 || now - stamp > POW_MAX_AGE_MS) return false;
  return leadingZeroBits(await sha256(token)) >= bits;
}

/**
 * Blurred appeal stills on public pages (spec PUB-02; 0004_11 public_appeals images).
 * The URL is always built from the public bucket + a checked path, never taken from a stored URL.
 */

export const APPEAL_BUCKET = "appeal-public";

/** Matches 0004_11: '<id>/<name>.jpg|jpeg|png|webp', no '..', no leading '/', no scheme. */
const SAFE_PATH = /^[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp)$/;

export type AppealImage = { path: string; width: number | null; height: number | null };

export function isSafeImagePath(path: unknown): path is string {
  return typeof path === "string" && SAFE_PATH.test(path);
}

/** Public storage URL for a still, or null when the base URL or the path is unusable. */
export function appealImageUrl(supabaseUrl: string | undefined, path: unknown): string | null {
  if (!supabaseUrl || !isSafeImagePath(path)) return null;
  let base: URL;
  try { base = new URL(supabaseUrl); } catch { return null; }
  if (base.protocol !== "https:") return null;
  return `${base.origin}/storage/v1/object/public/${APPEAL_BUCKET}/${path}`;
}

export const APPEAL_IMAGE_ALT = "Blurred still from the scene (whole image blurred to protect identities)";

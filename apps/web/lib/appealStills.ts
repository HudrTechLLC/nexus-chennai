/**
 * Blurred stills on public appeals (spec PUB-02, J1; 0004_06_05; WS4-09).
 * Pure helpers for public_incidents.images entries. The database trigger is the real guard;
 * these keep the editor and the server action consistent with it.
 */

import type { BLUR_METHOD } from "@/lib/stillBlur"; // type only: no runtime dependency on the image libraries

export const APPEAL_BUCKET = "appeal-public";
export const MAX_STILLS = 8; // same cap as public_incidents_images_guard
export const ATTACHABLE_KINDS = ["cctv_still", "photo"] as const;
export const BLUR_LABEL = "Whole image heavily blurred. No face or plate detection; nothing in the picture is identifiable.";
export const STILL_ALT = "Blurred still from the scene (whole image blurred to protect identities)";

/** One entry of public_incidents.images. evidence_id stays internal: nexus-4's public RPCs drop it. */
export type StillEntry = {
  path: string; // <public_incident_id>/<uuid>.jpg in appeal-public
  blurred: true;
  method: typeof BLUR_METHOD;
  evidence_id: string;
  width: number;
  height: number;
  added_at: string;
};

export type EvidenceRow = { evidence_id: string; crime_id: string; kind: string; storage_path: string; captured_at: string | null; created_at: string };

/** Reads images defensively (older rows may hold anything). */
export function parseImages(raw: unknown): StillEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((x): x is StillEntry => !!x && typeof x === "object" && typeof (x as StillEntry).path === "string" && (x as StillEntry).blurred === true);
}

/** Object key for a new blurred copy. Never contains the crime id (the bucket is public). */
export function stillPath(appealId: string, uuid: string): string {
  return `${appealId}/${uuid}.jpg`;
}

/** Evidence that can be attached: a still or photo of this appeal's case, stored as JPEG or PNG. */
export function attachable(e: EvidenceRow, crimeId: string | null): boolean {
  return !!crimeId && e.crime_id === crimeId && (ATTACHABLE_KINDS as readonly string[]).includes(e.kind) && /\.(jpe?g|png)$/i.test(e.storage_path);
}

/** Why a still cannot be attached right now, or null. */
export function attachProblem(images: StillEntry[], evidenceId: string, status: string): string | null {
  if (status === "withdrawn") return "This appeal is withdrawn. Stills cannot be added.";
  if (images.length >= MAX_STILLS) return `An appeal can show at most ${MAX_STILLS} stills.`;
  if (images.some((i) => i.evidence_id === evidenceId)) return "This still is already attached.";
  return null;
}

export function withStill(images: StillEntry[], entry: StillEntry): StillEntry[] {
  return [...images.filter((i) => i.path !== entry.path), entry];
}

export function withoutStill(images: StillEntry[], path: string): StillEntry[] {
  return images.filter((i) => i.path !== path);
}

/** Public URL of a blurred copy, built from bucket + path only (never a stored URL). */
export function publicStillUrl(supabaseUrl: string, path: string): string {
  return `${supabaseUrl.replace(/\/+$/, "")}/storage/v1/object/public/${APPEAL_BUCKET}/${path.split("/").map(encodeURIComponent).join("/")}`;
}

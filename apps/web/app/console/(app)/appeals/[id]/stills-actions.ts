"use server";
import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { audit } from "@/lib/alertsData";
import { consoleServerClient } from "@/lib/supabase/server";
import { blurStill, hasMetadata, StillError } from "@/lib/stillBlur";
import { APPEAL_BUCKET, attachable, attachProblem, parseImages, stillPath, withoutStill, withStill, type EvidenceRow, type StillEntry } from "@/lib/appealStills";

/**
 * Attach / detach blurred stills on a public appeal (PUB-02; 0004_06_05).
 * Everything runs as the signed-in officer: the original is read from the PRIVATE `evidence` bucket
 * under storage RLS (can_read_crime), blurred and re-encoded here, and only the copy is written to the
 * PUBLIC `appeal-public` bucket (RLS: appeal_can_write). The images trigger re-checks every entry.
 */

export type StillResult = { ok: true } | { ok: false; error: string };

const WRITERS = new Set(["station_officer", "supervisor", "admin"]);

function revalidate(appealId: string) {
  revalidatePath(`/console/appeals/${encodeURIComponent(appealId)}`);
  revalidatePath(`/appeals/${encodeURIComponent(appealId)}`);
  revalidatePath("/appeals");
}

export async function attachStill(appealId: string, evidenceId: string): Promise<StillResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  if (!WRITERS.has(officer.role)) return { ok: false, error: "Your role cannot change appeals." };
  const sb = consoleServerClient();

  const { data: appeal } = await sb.from("public_incidents").select("public_incident_id, crime_id, status, images").eq("public_incident_id", appealId).maybeSingle();
  if (!appeal) return { ok: false, error: "Appeal not found." };
  const images = parseImages(appeal.images);
  const problem = attachProblem(images, evidenceId, appeal.status);
  if (problem) return { ok: false, error: problem };

  const { data: ev } = await sb.from("evidence_media").select("evidence_id, crime_id, kind, storage_path, captured_at, created_at").eq("evidence_id", evidenceId).maybeSingle();
  if (!ev || !attachable(ev as EvidenceRow, appeal.crime_id)) return { ok: false, error: "That still does not belong to this appeal's case, or is not a JPEG/PNG photo." };

  const { data: blob, error: dlErr } = await sb.storage.from("evidence").download((ev as EvidenceRow).storage_path);
  if (dlErr || !blob) return { ok: false, error: "Could not read the original still (you need access to this case's evidence)." };

  let out;
  try {
    out = blurStill(Buffer.from(await blob.arrayBuffer()));
  } catch (e) {
    return { ok: false, error: e instanceof StillError ? e.message : "The still could not be processed." };
  }
  if (hasMetadata(out.jpeg)) return { ok: false, error: "Metadata check failed; nothing was published." }; // belt and braces

  const path = stillPath(appealId, randomUUID());
  const { error: upErr } = await sb.storage.from(APPEAL_BUCKET).upload(path, out.jpeg, { contentType: "image/jpeg", upsert: false, cacheControl: "300" });
  if (upErr) return { ok: false, error: `Could not store the blurred copy: ${upErr.message}` };

  const entry: StillEntry = {
    path, blurred: true, method: out.method, evidence_id: evidenceId, width: out.width, height: out.height, added_at: new Date().toISOString(),
  };
  const { data: saved, error: saveErr } = await sb.from("public_incidents").update({ images: withStill(images, entry) })
    .eq("public_incident_id", appealId).select("public_incident_id");
  if (saveErr || !saved || saved.length === 0) {
    await sb.storage.from(APPEAL_BUCKET).remove([path]); // do not leave an orphaned public copy
    return { ok: false, error: saveErr?.message ?? "You can only change appeals for your own station's cases." };
  }
  await audit(sb, "attach_still", "public_incident", appealId, { evidence_id: evidenceId, path, method: out.method });
  revalidate(appealId);
  return { ok: true };
}

export async function detachStill(appealId: string, path: string): Promise<StillResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const sb = consoleServerClient();
  const { data: appeal } = await sb.from("public_incidents").select("images").eq("public_incident_id", appealId).maybeSingle();
  if (!appeal) return { ok: false, error: "Appeal not found." };
  const images = parseImages(appeal.images);
  if (!images.some((i) => i.path === path)) return { ok: false, error: "That still is not on this appeal." };
  const { data: saved, error } = await sb.from("public_incidents").update({ images: withoutStill(images, path) })
    .eq("public_incident_id", appealId).select("public_incident_id");
  if (error || !saved || saved.length === 0) return { ok: false, error: error?.message ?? "You can only change appeals for your own station's cases." };
  await sb.storage.from(APPEAL_BUCKET).remove([path]); // the public copy goes with it (chief, Flag B)
  await audit(sb, "detach_still", "public_incident", appealId, { path });
  revalidate(appealId);
  return { ok: true };
}

/**
 * Withdraw hook (chief, Flag B): deletes every public blurred copy of an appeal and clears images.
 * Call it from the withdraw path after the status update. Safe to call when there are none.
 */
export async function removeAllStills(appealId: string): Promise<StillResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const sb = consoleServerClient();
  const { data: appeal } = await sb.from("public_incidents").select("images").eq("public_incident_id", appealId).maybeSingle();
  if (!appeal) return { ok: false, error: "Appeal not found." };
  const paths = parseImages(appeal.images).map((i) => i.path);
  if (paths.length === 0) return { ok: true };
  const { error } = await sb.from("public_incidents").update({ images: [] }).eq("public_incident_id", appealId);
  if (error) return { ok: false, error: error.message };
  await sb.storage.from(APPEAL_BUCKET).remove(paths);
  await audit(sb, "remove_stills", "public_incident", appealId, { count: paths.length });
  revalidate(appealId);
  return { ok: true };
}

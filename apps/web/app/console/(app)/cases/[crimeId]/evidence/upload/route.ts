import { NextResponse } from "next/server";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { canWriteCase } from "@/lib/cases";
import { CITY } from "@/lib/city";
import { cityLocalToIso } from "@/lib/fir";
import { checkEvidence, evidencePath, exifDateTime, MAX_EVIDENCE_BYTES, sha256Hex } from "@/lib/evidence";

export const dynamic = "force-dynamic";

const bad = (status: number, error: string) => NextResponse.json({ ok: false, error }, { status });

/**
 * POST multipart (file, kind, camera_id?, captured_at?, target=evidence|statement).
 * Uploads the ORIGINAL bytes to the private `evidence` bucket as the signed-in officer (storage
 * policies: can_write_crime from the key, 0007_02), hashes them here so the client cannot choose
 * the hash, and records the evidence_media row or audio statement through record_evidence (0007_06).
 */
export async function POST(req: Request, { params }: { params: { crimeId: string } }) {
  const officer = await getOfficer();
  if (!officer) return bad(401, "Sign in again.");
  const crimeId = decodeURIComponent(params.crimeId);
  const sb = consoleServerClient();

  const { data: crime } = await sb.from("crimes").select("crime_id, station_id").eq("crime_id", crimeId).maybeSingle();
  if (!crime) return bad(404, "Case not found, or not one you can open.");
  if (!canWriteCase(officer.role, officer.stationId, crime.station_id)) return bad(403, "Only the case's station (or a supervisor) can add evidence.");

  const len = Number(req.headers.get("content-length") ?? 0);
  if (len > MAX_EVIDENCE_BYTES + 64 * 1024) return bad(413, "Files must be 4 MB or smaller.");
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return bad(400, "Send the file as a form upload.");
  }
  const file = form.get("file");
  if (!(file instanceof Blob)) return bad(400, "Choose a file.");
  const target = form.get("target") === "statement" ? "statement" : "evidence";
  const kind = target === "statement" ? "audio" : String(form.get("kind") ?? "");
  const bytes = new Uint8Array(await file.arrayBuffer());
  const check = checkEvidence(bytes, kind);
  if ("error" in check) return bad(400, check.error);

  const sha256 = await sha256Hex(bytes);
  const id = crypto.randomUUID();
  const path = evidencePath(crimeId, id, check.ext);
  const { error: upErr } = await sb.storage.from("evidence").upload(path, bytes, { contentType: check.mime, upsert: false });
  if (upErr) return bad(upErr.message.includes("row-level security") ? 403 : 500, `Upload failed: ${upErr.message}`);

  // 0007_06: the database records the row. It checks this officer owns the stored object, takes size
  // and type from storage, and sets uploaded_by, custody, the witness ref and the audit_log entry.
  const typed = String(form.get("captured_at") ?? "");
  const exif = target === "evidence" && check.mime === "image/jpeg" ? exifDateTime(bytes) : null;
  const capturedAt = (typed && cityLocalToIso(typed, CITY.timezone)) || (exif && cityLocalToIso(exif, CITY.timezone)) || null;
  const camera = String(form.get("camera_id") ?? "").trim().slice(0, 40) || null;
  const { data: recordedId, error } = await sb.rpc("record_evidence", {
    p: {
      crime_id: crimeId, path, sha256, target, kind, bytes: bytes.length, captured_at: capturedAt, camera_id: camera,
      captured_from: capturedAt ? (typed && cityLocalToIso(typed, CITY.timezone) ? "officer" : "exif") : null,
    },
  });
  if (error) return bad(500, `Saved the file but not the ${target === "statement" ? "statement" : "evidence record"}: ${error.message}`);
  if (target === "statement") return NextResponse.json({ ok: true, path, sha256 });
  return NextResponse.json({ ok: true, evidenceId: recordedId as string, path, sha256, capturedAt });
}

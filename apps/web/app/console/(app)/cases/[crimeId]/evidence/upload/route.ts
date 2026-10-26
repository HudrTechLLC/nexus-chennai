import { NextResponse } from "next/server";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit } from "@/lib/alertsData";
import { canWriteCase } from "@/lib/cases";
import { CITY } from "@/lib/city";
import { cityLocalToIso } from "@/lib/fir";
import { checkEvidence, evidencePath, exifDateTime, MAX_EVIDENCE_BYTES, sha256Hex, type CustodyStep } from "@/lib/evidence";

export const dynamic = "force-dynamic";

const bad = (status: number, error: string) => NextResponse.json({ ok: false, error }, { status });

/**
 * POST multipart (file, kind, camera_id?, captured_at?, target=evidence|statement).
 * Uploads the ORIGINAL bytes to the private `evidence` bucket as the signed-in officer (storage
 * policies: can_write_crime from the key, 0007_02), hashes them here so the client cannot choose
 * the hash, and records an evidence_media row (custody: uploaded) or an audio statement.
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

  const now = new Date().toISOString();
  if (target === "statement") {
    const { count } = await sb.from("statements").select("statement_id", { count: "exact", head: true }).eq("crime_id", crimeId);
    const n = (count ?? 0) + 1;
    const { error } = await sb.from("statements").insert({
      statement_id: `ST-${crimeId}-A${id.slice(0, 8)}`, crime_id: crimeId, witness_ref: `W-${n} (masked)`, mode: "audio",
      audio_path: path, recorded_at: now, synthetic: CITY.synthetic,
    });
    if (error) return bad(500, `Saved the file but not the statement: ${error.message}`);
    await audit(sb, "add_audio_statement", "crime", crimeId, { path, sha256 });
    return NextResponse.json({ ok: true, path, sha256 });
  }

  const typed = String(form.get("captured_at") ?? "");
  const exif = check.mime === "image/jpeg" ? exifDateTime(bytes) : null;
  const capturedAt = (typed && cityLocalToIso(typed, CITY.timezone)) || (exif && cityLocalToIso(exif.slice(0, 16), CITY.timezone)) || null;
  const camera = String(form.get("camera_id") ?? "").trim().slice(0, 40) || null;
  const custody: CustodyStep[] = [{ at: now, by: officer.userId, action: "uploaded", sha256, bytes: bytes.length, mime: check.mime }];
  const evidenceId = `EV-${id}`;
  const { error } = await sb.from("evidence_media").insert({
    evidence_id: evidenceId, crime_id: crimeId, kind, storage_path: path, sha256, captured_at: capturedAt, camera_id: camera,
    uploaded_by: officer.userId, custody, synthetic: CITY.synthetic,
  });
  if (error) return bad(500, `Saved the file but not the evidence record: ${error.message}`);
  await audit(sb, "add_evidence", "crime", crimeId, { evidence_id: evidenceId, sha256, captured_from: typed ? "officer" : exif ? "exif" : null });
  return NextResponse.json({ ok: true, evidenceId, path, sha256, capturedAt });
}

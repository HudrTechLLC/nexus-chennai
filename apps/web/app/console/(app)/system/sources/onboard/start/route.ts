import { NextResponse } from "next/server";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { isMissingTable, looksLikeText, MAX_UPLOAD_BYTES, rpcMessage, uploadPath, validateStart } from "@/lib/onboarding";

export const dynamic = "force-dynamic";

const bad = (status: number, error: string, extra: Record<string, unknown> = {}) =>
  NextResponse.json({ ok: false, error, ...extra }, { status });

/**
 * POST multipart (source_key, label, use_sample, file?) — start onboarding a new source (WS1-23).
 * Admin only. Checks everything BEFORE uploading (admins cannot delete from the bucket), uploads the CSV to the
 * private `onboarding` bucket as the signed-in admin, then calls onboarding_start (0007_15), which checks the
 * object exists. The sample export needs no upload: the worker reads it from the repo.
 */
export async function POST(req: Request) {
  const officer = await getOfficer();
  if (!officer) return bad(401, "Sign in again.");
  if (officer.role !== "admin") return bad(403, "Only an admin can onboard a source.");

  const len = Number(req.headers.get("content-length") ?? 0);
  if (len > MAX_UPLOAD_BYTES + 64 * 1024) return bad(413, "The file must be 2 MB or smaller.");
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return bad(400, "Send the form as an upload.");
  }
  const sourceKey = String(form.get("source_key") ?? "").trim();
  const label = String(form.get("label") ?? "").trim();
  const useSample = form.get("use_sample") === "true";
  const file = form.get("file");
  const blob = !useSample && file instanceof Blob ? (file as File) : null;
  const fields = validateStart({ sourceKey, label, useSample, file: blob ? { name: blob.name || "", size: blob.size } : null });
  if (Object.keys(fields).length) return bad(400, "Check the highlighted fields.", { fields });

  const sb = consoleServerClient();
  const { data: existing, error: lookErr } = await sb.from("onboarding_runs").select("run_id").eq("source_key", sourceKey).maybeSingle();
  if (lookErr) return bad(isMissingTable(lookErr) ? 503 : 500, rpcMessage(lookErr));
  if (existing) {
    return bad(409, "A source with this key is already onboarded.", { runId: (existing as { run_id: string }).run_id, fields: { source_key: "Already used." } });
  }

  let path: string | null = null;
  if (blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (!looksLikeText(bytes)) return bad(400, "That file is not a CSV (it contains binary data).", { fields: { file: "Not a text CSV." } });
    path = uploadPath(crypto.randomUUID());
    // text/csv whatever the browser said: Windows often sends .csv as application/octet-stream, which the bucket refuses.
    const { error: upErr } = await sb.storage.from("onboarding").upload(path, bytes, { contentType: "text/csv", upsert: false });
    if (upErr) return bad(upErr.message.includes("row-level security") ? 403 : 500, `Upload failed: ${upErr.message}`);
  }

  const { data: runId, error } = await sb.rpc("onboarding_start", {
    p_source_key: sourceKey, p_label: label, p_file_path: path, p_use_sample: useSample,
  });
  if (error) return bad(error.code === "42501" ? 403 : error.code === "23505" ? 409 : 400, rpcMessage(error));
  return NextResponse.json({ ok: true, runId });
}

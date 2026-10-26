import { CITY } from "@/lib/city";
import { clientAddr, powSeen, publicClient, rateLimited, reply } from "@/lib/publicApi";
import {
  FILE_TYPES, imageHasMetadata, MAX_FILE_BYTES, MAX_FILES, sniffType, validateTip, verifyPow, type TipInput,
} from "@/lib/tip";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Anonymous tip intake (spec G1 /tip/new, J1; DECISIONS D-003, D-023).
 * Deterministic steps only: throttle, proof of work, size/type limits, metadata double-check,
 * upload to the write-only bucket, then the submit_tip RPC (status 'new'). Tip Guard screening
 * runs later in the local worker. Nothing about the sender (address, agent, cookies) is logged or stored.
 */
export async function POST(req: Request) {
  if (await rateLimited(clientAddr(req.headers), "tip", 5, 10 * 60_000)) {
    return reply({ ok: false, error: "Too many tips from here just now. Please try again in a few minutes." }, 429);
  }

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return reply({ ok: false, error: "Could not read the form." }, 400);
  }
  const pow = String(form.get("pow") ?? "");
  if (!(await verifyPow(pow)) || powSeen(pow)) {
    return reply({ ok: false, error: "Security check expired. Please press Send again." }, 400);
  }

  const str = (k: string) => {
    const v = form.get(k);
    return typeof v === "string" && v.length ? v : null;
  };
  const input: TipInput = {
    category: str("category") ?? "",
    text: str("text") ?? "",
    cell: str("cell"),
    followUp: str("follow_up") === "1",
    code: str("code"),
    passphrase: str("passphrase"),
    appeal: str("appeal"),
    about: str("about"),
  };
  const problem = validateTip(input);
  if (problem) return reply({ ok: false, error: problem }, 400);
  if (input.appeal && input.about) return reply({ ok: false, error: "A tip can be about one appeal or one crime, not both." }, 400);

  const files = form.getAll("files").filter((f): f is File => typeof f !== "string");
  const blurred = form.getAll("blurred").map(String);
  if (files.length > MAX_FILES) return reply({ ok: false, error: `At most ${MAX_FILES} files.` }, 400);

  const sb = publicClient();
  const media: { path: string; kind: "image" | "audio"; faces_blurred: boolean }[] = [];
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    if (f.size > MAX_FILE_BYTES) return reply({ ok: false, error: `${f.name || "A file"} is larger than 15 MB.` }, 400);
    const bytes = new Uint8Array(await f.arrayBuffer());
    const type = sniffType(bytes);
    const spec = type ? FILE_TYPES[type] : undefined;
    if (!type || !spec) return reply({ ok: false, error: "Only photos (JPEG, PNG, WebP) and audio files are accepted." }, 400);
    // J1: the browser strips metadata; the server rejects anything where it survived.
    if (spec.kind === "image" && imageHasMetadata(bytes)) {
      return reply({ ok: false, error: "A photo still had location or camera details. Please add it again so it can be cleaned." }, 400);
    }
    const path = `tips/${crypto.randomUUID()}.${spec.ext}`;
    const { error } = await sb.storage.from("tip-media").upload(path, bytes, { contentType: type, upsert: false });
    if (error) return reply({ ok: false, error: "Could not store a file. Please try again." }, 502);
    media.push({ path, kind: spec.kind, faces_blurred: blurred[i] === "1" });
  }

  const { data, error } = await sb.rpc("submit_tip", {
    p_appeal: input.appeal, p_category: input.category, p_text: input.text, p_cell: input.cell,
    p_follow_up: input.followUp, p_code: input.followUp ? input.code : null, p_passphrase: input.followUp ? input.passphrase : null,
    p_media: media, p_tz: CITY.timezone,
    // Crime-card link (0007_11). Sent only when present; submit_tip re-checks that the crime is public.
    ...(input.about ? { p_about: input.about } : {}),
  });
  if (error) {
    const known = /already used|too many tips|invalid|must be|unknown appeal|unknown crime|at most/i.test(error.message);
    return reply({ ok: false, error: known ? error.message : "Could not send the tip. Please try again." }, known ? 400 : 502);
  }
  return reply({ ok: true, tip_id: (data as { tip_id: string }).tip_id, received_week: (data as { received_week: string }).received_week });
}

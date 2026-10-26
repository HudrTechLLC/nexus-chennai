#!/usr/bin/env node
/**
 * Live evidence-store check (WS3-10, migration 0007_02). Signs in as demo users with the PUBLISHABLE
 * key (what the console does) and asserts:
 *   1. the case's own station officer can upload to the private `evidence` bucket;
 *   2. the stored object's sha256 equals the sha256 recorded in evidence_media and its custody step;
 *   3. an officer of another station can neither upload to nor read that case's evidence;
 *   4. anon cannot read it; the bucket is not public; nothing can overwrite the object.
 *
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY="$(tr -d '\r\n' < <publishable key file>)" \
 *     node apps/web/scripts/evidence-check.mjs <crime_id of an Adyar case>
 *
 * It writes one small synthetic PNG (a valid, viewable 8x8 image) + one evidence_media row to the given case.
 * Uploaded evidence cannot be deleted through the API (custody), so point it at a test case. Passwords are never printed.
 */
import { createHash, randomUUID } from "node:crypto";
import { crc32, deflateSync } from "node:zlib";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://ukrujnsjucwvytnokbtw.supabase.co";
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const crimeId = process.argv[2];
if (!key || !crimeId) {
  console.error("usage: NEXT_PUBLIC_SUPABASE_ANON_KEY=... node evidence-check.mjs <crime_id>");
  process.exit(2);
}
const { users } = JSON.parse(readFileSync(`${homedir()}/.secrets/nexus-demo-users.json`, "utf8"));
const client = () => createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
async function as(email) {
  const u = users.find((x) => x.email === email);
  const sb = client();
  const { error } = await sb.auth.signInWithPassword({ email: u.email, password: u.password });
  if (error) throw new Error(`sign-in ${email}: ${error.message}`);
  return { sb, user: (await sb.auth.getUser()).data.user };
}
let fails = 0;
const report = (ok, label, detail = "") => { if (!ok) fails++; console.log(`${ok ? "PASS" : "FAIL"} ${label} ${detail}`); };

// A valid 8x8 grey PNG with a random tEXt chunk, so every run hashes differently and the gallery can show it.
const chunk = (type, data) => {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body) >>> 0);
  return Buffer.concat([len, body, crc]);
};
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(8, 0);
ihdr.writeUInt32BE(8, 4);
ihdr[8] = 8; // 8-bit greyscale (colour type 0)
const pixels = Buffer.alloc(8 * 9, 0x80);
for (let r = 0; r < 8; r++) pixels[r * 9] = 0; // filter byte per row
const bytes = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk("IHDR", ihdr),
  chunk("tEXt", Buffer.from(`Comment\0nexus evidence-check ${randomUUID()}`)),
  chunk("IDAT", deflateSync(pixels)),
  chunk("IEND", Buffer.alloc(0)),
]);
const sha = createHash("sha256").update(bytes).digest("hex");
const id = randomUUID();
const path = `${crimeId}/${id}.png`;

const own = await as("officer.adyar@nexus.demo");
const up = await own.sb.storage.from("evidence").upload(path, bytes, { contentType: "image/png", upsert: false });
report(!up.error, "own-station officer uploads", up.error?.message ?? "");
const evidenceId = `EV-${id}`;
// 0007_06: rows are recorded only through record_evidence, which checks this officer owns the object.
const direct = await own.sb.from("evidence_media").insert({
  evidence_id: `EV-${randomUUID()}`, crime_id: crimeId, kind: "photo", storage_path: path, sha256: sha, uploaded_by: own.user.id, synthetic: true,
});
report(!!direct.error, "direct evidence_media insert refused (0007_06)", direct.error?.message ?? "INSERTED");
const ins = await own.sb.rpc("record_evidence", { p: { crime_id: crimeId, path, sha256: sha, kind: "photo", bytes: bytes.length } });
report(!ins.error && ins.data === evidenceId, "evidence_media row recorded via record_evidence", ins.error?.message ?? "");

const dl = await own.sb.storage.from("evidence").download(path);
const stored = dl.data ? createHash("sha256").update(Buffer.from(await dl.data.arrayBuffer())).digest("hex") : null;
const { data: row } = await own.sb.from("evidence_media").select("sha256, custody").eq("evidence_id", evidenceId).maybeSingle();
report(stored === sha && row?.sha256 === sha && row?.custody?.[0]?.sha256 === sha, "stored object sha256 = recorded sha256 = custody sha256", stored ? stored.slice(0, 16) : "no download");

const over = await own.sb.storage.from("evidence").upload(path, Buffer.from("tampered"), { contentType: "image/png", upsert: true });
report(!!over.error, "object cannot be overwritten", over.error ? "" : "(overwrite succeeded!)");

const other = await as("officer.velachery@nexus.demo");
const r2 = await other.sb.storage.from("evidence").download(path);
report(!!r2.error || !r2.data, "other-station officer cannot read it");
const u2 = await other.sb.storage.from("evidence").upload(`${crimeId}/${randomUUID()}.png`, bytes, { contentType: "image/png" });
report(!!u2.error, "other-station officer cannot upload to it");

const anon = client();
const r3 = await anon.storage.from("evidence").download(path);
report(!!r3.error || !r3.data, "anon cannot read it");
const pub = anon.storage.from("evidence").getPublicUrl(path).data.publicUrl;
const res = await fetch(pub);
report(res.status >= 400, "public URL is refused (private bucket)", `HTTP ${res.status}`);

console.log(fails ? `${fails} FAILED` : "ALL PASS");
process.exit(fails ? 1 : 0);

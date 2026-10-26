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
 * It writes one small synthetic JPEG + one evidence_media row to the given case. Passwords are never printed.
 */
import { createHash, randomUUID } from "node:crypto";
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

// A tiny valid JPEG (SOI, APP0, EOI) plus random bytes so every run hashes differently.
const bytes = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]), Buffer.from("JFIF\0"), Buffer.from(randomUUID()), Buffer.from([0xff, 0xd9])]);
const sha = createHash("sha256").update(bytes).digest("hex");
const id = randomUUID();
const path = `${crimeId}/${id}.jpg`;

const own = await as("officer.adyar@nexus.demo");
const up = await own.sb.storage.from("evidence").upload(path, bytes, { contentType: "image/jpeg", upsert: false });
report(!up.error, "own-station officer uploads", up.error?.message ?? "");
const evidenceId = `EV-${id}`;
const ins = await own.sb.from("evidence_media").insert({
  evidence_id: evidenceId, crime_id: crimeId, kind: "photo", storage_path: path, sha256: sha, uploaded_by: own.user.id,
  custody: [{ at: new Date().toISOString(), by: own.user.id, action: "uploaded", sha256: sha, bytes: bytes.length, mime: "image/jpeg" }], synthetic: true,
});
report(!ins.error, "evidence_media row recorded", ins.error?.message ?? "");

const dl = await own.sb.storage.from("evidence").download(path);
const stored = dl.data ? createHash("sha256").update(Buffer.from(await dl.data.arrayBuffer())).digest("hex") : null;
const { data: row } = await own.sb.from("evidence_media").select("sha256, custody").eq("evidence_id", evidenceId).maybeSingle();
report(stored === sha && row?.sha256 === sha && row?.custody?.[0]?.sha256 === sha, "stored object sha256 = recorded sha256 = custody sha256", stored ? stored.slice(0, 16) : "no download");

const over = await own.sb.storage.from("evidence").upload(path, Buffer.from("tampered"), { contentType: "image/jpeg", upsert: true });
report(!!over.error, "object cannot be overwritten", over.error ? "" : "(overwrite succeeded!)");

const other = await as("officer.velachery@nexus.demo");
const r2 = await other.sb.storage.from("evidence").download(path);
report(!!r2.error || !r2.data, "other-station officer cannot read it");
const u2 = await other.sb.storage.from("evidence").upload(`${crimeId}/${randomUUID()}.jpg`, bytes, { contentType: "image/jpeg" });
report(!!u2.error, "other-station officer cannot upload to it");

const anon = client();
const r3 = await anon.storage.from("evidence").download(path);
report(!!r3.error || !r3.data, "anon cannot read it");
const pub = anon.storage.from("evidence").getPublicUrl(path).data.publicUrl;
const res = await fetch(pub);
report(res.status >= 400, "public URL is refused (private bucket)", `HTTP ${res.status}`);

console.log(fails ? `${fails} FAILED` : "ALL PASS");
process.exit(fails ? 1 : 0);

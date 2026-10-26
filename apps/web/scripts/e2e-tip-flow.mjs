#!/usr/bin/env node
/**
 * End-to-end check of the anonymous tip loop against a running web app + Supabase
 * (spec G1 tip flow, G2 /console/tips; WS4-05, WS4-06, WS4-08). It creates ONE test tip,
 * exercises every step, and always deletes the tip and its file at the end.
 *
 *   BASE_URL=http://localhost:3041 \
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY="$(tr -d '\r\n' < <publishable key file>)" \
 *   SUPABASE_SERVICE_ROLE_KEY="$(tr -d '\r\n' < ~/.secrets/nexus-service-role.key)" \
 *     node apps/web/scripts/e2e-tip-flow.mjs
 *
 * The service key is used only for cleanup. Demo users come from ~/.secrets/nexus-demo-users.json.
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { webcrypto as crypto } from "node:crypto";
import { createClient } from "@supabase/supabase-js";

const BASE = process.env.BASE_URL || "http://localhost:3041";
const URL_ = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://ukrujnsjucwvytnokbtw.supabase.co";
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!ANON || !SERVICE) {
  console.error("Set NEXT_PUBLIC_SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY for this command only.");
  process.exit(2);
}
const users = JSON.parse(readFileSync(`${homedir()}/.secrets/nexus-demo-users.json`, "utf8")).users;
const opts = { auth: { persistSession: false, autoRefreshToken: false } };
const service = createClient(URL_, SERVICE, opts);

let fails = 0;
const check = (ok, label, detail = "") => { if (!ok) fails++; console.log(`${ok ? "PASS" : "FAIL"} ${label} ${detail}`); };

const ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const code = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => ALPHA[b % 32]).join("");
const pass = Buffer.from(crypto.getRandomValues(new Uint8Array(12))).toString("base64url");
const tipId = `TIP-${code}`;

const lz = (h) => { let n = 0; for (const b of h) { if (b === 0) { n += 8; continue; } return n + Math.clz32(b) - 24; } return n; };
async function pow() {
  const st = Date.now(), salt = "e2e" + Buffer.from(crypto.getRandomValues(new Uint8Array(6))).toString("hex");
  for (let i = 0; ; i++) {
    const t = `${st}:${salt}:${i}`;
    if (lz(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t)))) >= 16) return t;
  }
}
// 1x1 PNG with no metadata chunks
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function signIn(role) {
  const u = users.find((x) => x.role === role);
  const sb = createClient(URL_, ANON, opts);
  const { error } = await sb.auth.signInWithPassword({ email: u.email, password: u.password });
  if (error) throw error;
  return sb;
}

try {
  // ---- tipster submits (with a file) ----
  const fd = new FormData();
  fd.set("pow", await pow());
  fd.set("category", "vehicle_seen");
  fd.set("text", "[e2e test, deleted automatically] Red motorcycle, two riders, near the tea shop.");
  fd.set("follow_up", "1"); fd.set("code", code); fd.set("passphrase", pass);
  fd.append("files", new Blob([PNG], { type: "image/png" }), "x.png"); fd.append("blurred", "0");
  let r = await fetch(`${BASE}/api/public/tip`, { method: "POST", body: fd });
  let j = await r.json();
  check(r.ok && j.ok && j.tip_id === tipId, "submit tip", `(${r.status} ${j.error ?? j.tip_id})`);
  check(!r.headers.get("set-cookie"), "submit sets no cookie");

  // ---- tipster checks status ----
  const status = async (extra = {}) => (await fetch(`${BASE}/api/public/tip-status`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, passphrase: pass, ...extra }),
  })).json();
  j = await status();
  check(j.ok && j.status === "received", "tipster sees status", `(${j.status ?? j.error})`);
  j = await (await fetch(`${BASE}/api/public/tip-status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, passphrase: "wrong-passphrase" }) })).json();
  check(!j.ok && /do not match/.test(j.error), "wrong passphrase gives the generic answer");

  // ---- officer triages ----
  const officer = await signIn("analyst");
  const { data: seen } = await officer.from("tips").select("tip_id, approx_cell, received_week, tip_code_hash").eq("tip_id", tipId).maybeSingle();
  check(!!seen, "analyst sees the tip");
  check(!!seen && seen.tip_code_hash?.startsWith("$2"), "passphrase stored only as bcrypt");
  const { data: near, error: nErr } = await officer.rpc("tip_nearby_crimes", { p_tip_id: tipId });
  check(!nErr && Array.isArray(near), "suggested cases RPC", `(${nErr?.message ?? near.length + " cases"})`);
  const { error: rvErr } = await officer.rpc("review_tip", { p_tip_id: tipId, p_useful: true, p_crime_id: null, p_note: "e2e" });
  check(!rvErr, "review_tip records a verdict", rvErr ? `(${rvErr.message})` : "");
  const { data: after } = await officer.from("tips").select("status").eq("tip_id", tipId).maybeSingle();
  check(after?.status === "reviewed", "tip marked reviewed", `(${after?.status})`);
  const me = (await officer.auth.getUser()).data.user.id;
  const { error: rpErr } = await officer.from("tip_messages").insert({ tip_id: tipId, sender: "police", text: "Thanks. What time was this?", author: me });
  check(!rpErr, "police reply inserted", rpErr ? `(${rpErr.message})` : "");
  const { error: direct } = await officer.from("tip_reviews").insert({ tip_id: tipId, useful: false });
  check(!!direct, "direct insert into tip_reviews is denied (only via review_tip)");

  // ---- tipster sees the reply and answers ----
  j = await status({ reply: "Around 7:45 pm." });
  const senders = (j.messages ?? []).map((m) => m.sender).join(",");
  check(j.ok && senders === "police,tipster", "tipster sees police reply and answers", `(${senders})`);
  check(j.status === "reviewed", "tipster sees 'reviewed'", `(${j.status})`);

  // ---- anon cannot read anything directly ----
  const anon = createClient(URL_, ANON, opts);
  for (const t of ["tips", "tip_messages", "tip_reviews", "tip_attempts"]) {
    const { data, error } = await anon.from(t).select("*").limit(1);
    check(!!error || (data ?? []).length === 0, `anon reads nothing from ${t}`);
  }
} catch (e) {
  fails++;
  console.error("ERROR", e.message ?? e);
} finally {
  // ---- always clean up ----
  const { data: media } = await service.from("tip_media").select("path").eq("tip_id", tipId);
  if (media?.length) await service.storage.from("tip-media").remove(media.map((m) => m.path));
  await service.from("tips").delete().eq("tip_id", tipId);
  await service.from("tip_attempts").delete().eq("tip_id", tipId);
  await service.from("audit_log").delete().eq("object_type", "tip").eq("object_id", tipId);
  const { count } = await service.from("tips").select("tip_id", { count: "exact", head: true }).eq("tip_id", tipId);
  console.log(count === 0 ? "cleanup: test tip, file and audit rows removed" : "cleanup: FAILED, remove " + tipId + " by hand");
}
console.log(fails ? `\n${fails} check(s) FAILED` : "\nall checks passed");
process.exit(fails ? 1 : 0);

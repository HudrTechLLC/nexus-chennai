#!/usr/bin/env node
/**
 * Two-user RLS check for the police console (tracker WS3-03).
 * Signs in as each demo user with the PUBLISHABLE key (exactly what the browser does)
 * and asserts what each role can and cannot see. Also asserts anon sees nothing.
 *
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY="$(tr -d '\r\n' < C:/Apps/healgrid-app/.secrets/nexus-publish.txt)" \
 *     node apps/web/scripts/rls-check.mjs [--users ~/.secrets/nexus-demo-users.json]
 *
 * Checks on tables that do not exist yet (e.g. before 0002_core) are reported as SKIP.
 * Exit code 1 when any check fails. Passwords are never printed.
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { createClient } from "@supabase/supabase-js";

const i = process.argv.indexOf("--users");
const usersPath = (i > -1 ? process.argv[i + 1] : `${homedir()}/.secrets/nexus-demo-users.json`).replace(/^~/, homedir());
const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://ukrujnsjucwvytnokbtw.supabase.co";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
if (!anonKey) {
  console.error("NEXT_PUBLIC_SUPABASE_ANON_KEY is not set (read it from the key file for this command only)");
  process.exit(2);
}
const { users } = JSON.parse(readFileSync(usersPath, "utf8"));

let fails = 0;
const report = (ok, label, detail = "") => {
  if (ok === null) console.log(`SKIP ${label} ${detail}`);
  else {
    if (!ok) fails++;
    console.log(`${ok ? "PASS" : "FAIL"} ${label} ${detail}`);
  }
};
const missing = (e) => e && (e.code === "42P01" || e.code === "PGRST205" || /does not exist|schema cache/i.test(e.message));

function client() {
  return createClient(url, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
}

// ---------- anon: no table access at all (spec Part I, DECISIONS D-003) ----------
{
  const sb = client();
  for (const t of ["profiles", "stations", "wards", "runs", "crimes", "link_alerts", "alert_decisions", "tips", "tip_reviews", "tip_attempts", "trace_events", "system_status"]) {
    const { data, error } = await sb.from(t).select("*").limit(1);
    if (missing(error)) report(null, `anon ${t}`, "(table not created yet)");
    else report(!!error || (data ?? []).length === 0, `anon reads nothing from ${t}`, error ? `(${error.code})` : `(${data.length} rows)`);
  }
}

// ---------- each police user ----------
const byRole = {};
for (const u of users) {
  const sb = client();
  const { data: auth, error } = await sb.auth.signInWithPassword({ email: u.email, password: u.password });
  if (error) {
    report(false, `${u.email} signs in`, `(${error.message})`);
    continue;
  }
  const uid = auth.user.id;
  const tag = `${u.role}<${u.email}>`;

  const { data: me } = await sb.from("profiles").select("role, station_id").eq("user_id", uid).maybeSingle();
  report(me?.role === u.role, `${tag} reads own profile with role`, `(${me?.role ?? "none"})`);

  const { data: all } = await sb.from("profiles").select("user_id");
  const seesOthers = (all ?? []).some((r) => r.user_id !== uid);
  const shouldSeeOthers = u.role === "supervisor" || u.role === "admin";
  report(seesOthers === shouldSeeOthers, `${tag} ${shouldSeeOthers ? "reads" : "cannot read"} other profiles`, `(${(all ?? []).length} visible)`);

  if (u.role !== "admin") {
    const { data: upd } = await sb.from("profiles").update({ role: "admin" }).eq("user_id", uid).select();
    report((upd ?? []).length === 0, `${tag} cannot promote itself to admin`);
  }

  const { data: st, error: stErr } = await sb.from("stations").select("station_id").limit(5);
  report(!stErr && (st ?? []).length > 0, `${tag} reads stations`, `(${(st ?? []).length})`);

  // Crimes (after 0002): station officers see only their own station's full rows.
  const { data: crimes, error: cErr } = await sb.from("crimes").select("station_id").limit(500);
  if (missing(cErr)) report(null, `${tag} crimes scope`, "(table not created yet)");
  else if (u.role === "station_officer") {
    const foreign = (crimes ?? []).filter((c) => c.station_id !== u.station_id).length;
    report(!cErr && foreign === 0, `${tag} reads only own-station crimes`, `(${(crimes ?? []).length} rows, ${foreign} foreign)`);
  } else report(!cErr, `${tag} reads crimes`, `(${(crimes ?? []).length} rows)`);

  // Link alerts incl. rejected are visible to every police role (spec Part I).
  const { error: aErr } = await sb.from("link_alerts").select("alert_id").limit(1);
  if (missing(aErr)) report(null, `${tag} link_alerts`, "(table not created yet)");
  else report(!aErr, `${tag} reads link_alerts`);

  // Traces and system status (0006_01): analyst, supervisor, admin only; station officers see none.
  for (const t of ["trace_events", "system_status"]) {
    const { data: rows, error: tErr } = await sb.from(t).select("*").limit(5);
    if (missing(tErr)) { report(null, `${tag} ${t}`, "(table not created yet)"); continue; }
    if (u.role === "station_officer") report(!!tErr || (rows ?? []).length === 0, `${tag} cannot read ${t}`);
    else report(!tErr, `${tag} reads ${t}`, `(${(rows ?? []).length})`);
  }

  byRole[u.role] ??= [];
  byRole[u.role].push(uid);
  await sb.auth.signOut();
}

console.log(fails ? `\n${fails} check(s) FAILED` : "\nall checks passed");
process.exit(fails ? 1 : 0);

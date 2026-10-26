#!/usr/bin/env node
/**
 * Seed the police console demo users (spec G2, tracker WS3-03).
 *
 * - Creates (or re-syncs the password of) each user through the Supabase Admin API.
 * - Upserts its row in public.profiles (role + station).
 * - Inserts a placeholder station row when an officer's station is not seeded yet
 *   (`on conflict do nothing`; the WS1 reference seed later upserts the real data).
 *
 * Nothing secret lives in this file or on the command line:
 *   SUPABASE_SERVICE_ROLE_KEY="$(tr -d '\r\n' < ~/.secrets/nexus-service-role.key)" \
 *     node apps/web/scripts/seed-demo-users.mjs [--users ~/.secrets/nexus-demo-users.json]
 *
 * The users file is JSON: { "users": [{ "email", "name", "role", "password", "station_id"? }] }.
 * Passwords are never printed.
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { createClient } from "@supabase/supabase-js";

const ROLES = new Set(["station_officer", "analyst", "supervisor", "admin"]);

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : fallback;
}

const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "https://ukrujnsjucwvytnokbtw.supabase.co";
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!serviceKey) {
  console.error("SUPABASE_SERVICE_ROLE_KEY is not set (read it from the key file for this command only)");
  process.exit(2);
}
const usersPath = arg("--users", `${homedir()}/.secrets/nexus-demo-users.json`).replace(/^~/, homedir());
const { users } = JSON.parse(readFileSync(usersPath, "utf8"));

const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

/** Find an auth user by email (the Admin API has no direct lookup). */
async function findUser(email) {
  for (let page = 1; page < 50; page++) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 200 });
    if (error) throw error;
    const hit = data.users.find((u) => u.email?.toLowerCase() === email.toLowerCase());
    if (hit) return hit;
    if (data.users.length < 200) return null;
  }
  return null;
}

/** Make sure a station row exists so the profiles FK holds. */
async function ensureStation(stationId) {
  const { data, error } = await admin.from("stations").select("station_id").eq("station_id", stationId).maybeSingle();
  if (error) throw error;
  if (data) return "exists";
  const { error: insErr } = await admin.from("stations").upsert(
    { station_id: stationId, name: stationId, type: "law_and_order", synthetic: true },
    { onConflict: "station_id", ignoreDuplicates: true },
  );
  if (insErr) throw insErr;
  return "placeholder";
}

let failed = 0;
for (const u of users) {
  try {
    if (!ROLES.has(u.role)) throw new Error(`unknown role ${u.role}`);
    if (u.role === "station_officer" && !u.station_id) throw new Error("station_officer needs station_id");
    if (!u.password || u.password.length < 12) throw new Error("password missing or shorter than 12");

    let user = await findUser(u.email);
    if (user) {
      const { error } = await admin.auth.admin.updateUserById(user.id, { password: u.password, email_confirm: true });
      if (error) throw error;
    } else {
      const { data, error } = await admin.auth.admin.createUser({ email: u.email, password: u.password, email_confirm: true });
      if (error) throw error;
      user = data.user;
    }

    let station = "-";
    if (u.station_id) station = `${u.station_id} (${await ensureStation(u.station_id)})`;

    const { error: pErr } = await admin.from("profiles").upsert(
      { user_id: user.id, name: u.name, role: u.role, station_id: u.station_id ?? null },
      { onConflict: "user_id" },
    );
    if (pErr) throw pErr;
    console.log(`ok   ${u.email.padEnd(32)} ${u.role.padEnd(16)} station ${station}`);
  } catch (e) {
    failed++;
    console.error(`FAIL ${u.email}: ${e.message ?? e}`);
  }
}
process.exit(failed ? 1 : 0);

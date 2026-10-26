import "server-only";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Server-side anon client for the public portal. It has no session and sets no cookies, and
 * the visitor's browser never talks to Supabase directly (spec J1). anon has no table access;
 * only the 0004_03 RPCs and the write-only tip-media bucket are reachable (D-003).
 */
export function publicClient(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Supabase is not configured");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } });
}

// =====================
// Throttling without identity (J1, DECISIONS D-010)
// =====================

/**
 * Per-instance sliding window keyed by a salted hash of the client address. The salt is random
 * per process and rotates daily, the hash never leaves memory, and nothing is logged or stored.
 */
const buckets = new Map<string, number[]>();
let salt = crypto.randomUUID();
let saltDay = new Date().toISOString().slice(0, 10);

async function anonKey(addr: string): Promise<string> {
  const today = new Date().toISOString().slice(0, 10);
  if (today !== saltDay) {
    salt = crypto.randomUUID();
    saltDay = today;
    buckets.clear();
  }
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${salt}:${addr}`));
  return Buffer.from(h).toString("base64url").slice(0, 16);
}

export async function rateLimited(addr: string, scope: string, limit: number, windowMs: number): Promise<boolean> {
  const k = `${scope}:${await anonKey(addr)}`;
  const now = Date.now();
  const hits = (buckets.get(k) ?? []).filter((t) => now - t < windowMs);
  hits.push(now);
  buckets.set(k, hits);
  if (buckets.size > 50_000) buckets.clear(); // memory guard
  return hits.length > limit;
}

/** Proof-of-work tokens already used on this instance (replay guard). */
const seenPow = new Map<string, number>();
export function powSeen(token: string): boolean {
  const now = Date.now();
  if (seenPow.size > 20_000) seenPow.forEach((t, k) => { if (now - t > 15 * 60_000) seenPow.delete(k); });
  if (seenPow.has(token)) return true;
  seenPow.set(token, now);
  return false;
}

/** Best-effort client address for throttling only. Never logged, never stored. */
export function clientAddr(headers: Headers): string {
  return headers.get("x-real-ip") ?? headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
}

/** JSON reply with no caching and no cookies. */
export function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" },
  });
}

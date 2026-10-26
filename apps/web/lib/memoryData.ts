import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { AlertDecision } from "@/lib/alerts";
import { chunk } from "@/lib/series";
import type { Effect, LedgerFilter, LedgerRow, MemoryRow } from "@/lib/memory";
import { EMPTY_GRAPH, type EntityType, type GraphPayload } from "@/lib/worldGraph";

/** Server fetchers for /console/memory and /console/graph. All reads run as the officer, under RLS. */

const PAGE = 1000; // PostgREST max-rows

async function pageAll<T>(fetchPage: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>, max = 10_000) {
  const rows: T[] = [];
  for (let from = 0; from < max; from += PAGE) {
    const { data, error } = await fetchPage(from, from + PAGE - 1);
    if (error) return { rows, error: error.message };
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE) break;
  }
  return { rows, error: null as string | null };
}

export async function fetchMemories(sb: SupabaseClient) {
  return pageAll<MemoryRow>((from, to) => sb.from("hmem_memories").select("*").order("updated_at", { ascending: false }).range(from, to));
}

/** Ledger entries that change state (everything except the high-volume "read"), for confidence histories. */
export async function fetchStateLedger(sb: SupabaseClient) {
  return pageAll<LedgerRow>((from, to) => sb.from("hmem_ledger").select("*").neq("action", "read").order("at").order("id").range(from, to));
}

/** One page of the ledger, newest first, with the exact total for the pager. */
export async function fetchLedgerPage(sb: SupabaseClient, filter: LedgerFilter, page: number, size = 50) {
  let q = sb.from("hmem_ledger").select("*", { count: "exact" }).order("at", { ascending: false }).order("id", { ascending: false });
  if (filter === "decisions") q = q.neq("action", "read");
  else if (filter !== "all") q = q.eq("action", filter);
  const from = Math.max(0, page) * size;
  const { data, count, error } = await q.range(from, from + size - 1);
  return { rows: (data ?? []) as LedgerRow[], total: count ?? 0, error: error?.message ?? null };
}

/** Every (alert, memory) application (one RPC, no row cap). */
export async function fetchEffects(sb: SupabaseClient): Promise<{ rows: Effect[]; error: string | null }> {
  const { data, error } = await sb.rpc("hmem_effects");
  return { rows: (data ?? []) as Effect[], error: error?.message ?? null };
}

/** The analyst decisions behind the memories (who decided, when, the note). Latest per alert. */
export async function decisionsFor(sb: SupabaseClient, alertIds: string[]): Promise<Record<string, AlertDecision>> {
  const ids = Array.from(new Set(alertIds.filter(Boolean)));
  const parts = await Promise.all(chunk(ids, 100).map(async (c) => {
    const { data } = await sb.from("alert_decisions").select("*").in("alert_id", c).order("at", { ascending: false });
    return (data ?? []) as AlertDecision[];
  }));
  const out: Record<string, AlertDecision> = {};
  for (const d of parts.flat()) if (!out[d.alert_id]) out[d.alert_id] = d;
  return out;
}

/** A World Model neighbourhood (wm_graph, 0004_06_02). */
export async function fetchGraph(sb: SupabaseClient, opts: { seed: string | null; hops: number; types: EntityType[] | null; limit?: number }):
  Promise<{ graph: GraphPayload; error: string | null }> {
  const { data, error } = await sb.rpc("wm_graph", { p_seed: opts.seed, p_hops: opts.hops, p_types: opts.types, p_limit: opts.limit ?? 200 });
  return { graph: (data as GraphPayload | null) ?? EMPTY_GRAPH, error: error?.message ?? null };
}

/** Entity suggestions for the search box: keys that contain the text (case-insensitive). */
export async function suggestEntities(sb: SupabaseClient, text: string, limit = 12): Promise<{ id: string; type: EntityType; key: string }[]> {
  const t = text.trim();
  if (t.length < 2) return [];
  const safe = t.replace(/[%_,()]/g, " ");
  const { data } = await sb.from("wm_entities").select("id, type, key").ilike("key", `%${safe}%`).order("key").limit(limit);
  return (data ?? []) as { id: string; type: EntityType; key: string }[];
}

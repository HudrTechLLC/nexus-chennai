import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Taskforce, TfCase, TfMember, TfNote } from "@/lib/taskforces";

/** Server reads for /console/taskforces. All run as the officer, under RLS (every police role reads). */

export async function fetchTaskforces(sb: SupabaseClient): Promise<{ rows: Taskforce[]; error: string | null }> {
  const { data, error } = await sb.from("taskforces").select("*").order("created_at", { ascending: false }).limit(500);
  return { rows: (data ?? []) as Taskforce[], error: error?.message ?? null };
}

/** Member and linked-case counts per task force, for the list. */
export async function taskforceCounts(sb: SupabaseClient, ids: string[]): Promise<Record<string, { members: number; cases: number }>> {
  const out: Record<string, { members: number; cases: number }> = {};
  if (ids.length === 0) return out;
  const [{ data: m }, { data: c }] = await Promise.all([
    sb.from("taskforce_members").select("taskforce_id").in("taskforce_id", ids),
    sb.from("taskforce_cases").select("taskforce_id").in("taskforce_id", ids),
  ]);
  for (const id of ids) out[id] = { members: 0, cases: 0 };
  for (const r of m ?? []) out[r.taskforce_id].members++;
  for (const r of c ?? []) out[r.taskforce_id].cases++;
  return out;
}

export async function fetchTaskforce(sb: SupabaseClient, id: string) {
  const [tf, members, cases, notes] = await Promise.all([
    sb.from("taskforces").select("*").eq("taskforce_id", id).maybeSingle(),
    sb.from("taskforce_members").select("*").eq("taskforce_id", id),
    sb.from("taskforce_cases").select("*").eq("taskforce_id", id).order("added_at"),
    sb.from("taskforce_notes").select("*").eq("taskforce_id", id).order("at"),
  ]);
  return {
    taskforce: (tf.data as Taskforce | null) ?? null,
    members: (members.data ?? []) as TfMember[],
    cases: (cases.data ?? []) as TfCase[],
    notes: (notes.data ?? []) as TfNote[],
  };
}

/** Officers a supervisor can add (profiles are readable by supervisor and admin only, 0001). */
export async function officerDirectory(sb: SupabaseClient): Promise<{ user_id: string; name: string; role: string; station_id: string | null }[]> {
  const { data } = await sb.from("profiles").select("user_id, name, role, station_id").order("name").limit(1000);
  return (data ?? []) as { user_id: string; name: string; role: string; station_id: string | null }[];
}

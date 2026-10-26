"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { canPropose, parseCrimeIds, validateNote, validateProposal } from "@/lib/taskforces";

/**
 * Task force writes. Each calls one SECURITY DEFINER RPC from 0004_06_03 as the signed-in officer;
 * the RPC checks the role, takes the actor from auth.uid() and writes audit_log. The checks here
 * only give a friendlier message first.
 */

export type TfResult = { ok: true; id?: string; status?: string } | { ok: false; error: string };

function friendly(message: string): string {
  if (/not allowed|only members|only leads/i.test(message)) return "Your role cannot do that on this task force.";
  return message;
}

export async function proposeTaskforce(input: { name: string; purpose?: string; series_id?: string | null; alert_id?: string | null; crime_ids?: string }): Promise<TfResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  if (!canPropose(officer.role)) return { ok: false, error: "Analysts, supervisors and admins propose joint task forces." };
  const problem = validateProposal(input);
  if (problem) return { ok: false, error: problem };
  const sb = consoleServerClient();
  const { data, error } = await sb.rpc("taskforce_propose", {
    p_name: input.name.trim(), p_purpose: input.purpose?.trim() || null,
    p_series_id: input.series_id || null, p_alert_id: input.alert_id || null,
    p_crime_ids: input.crime_ids ? parseCrimeIds(input.crime_ids) : null,
  });
  if (error) return { ok: false, error: friendly(error.message) };
  revalidatePath("/console/taskforces");
  return { ok: true, id: data as string };
}

export async function decideTaskforce(id: string, decision: "approve" | "decline" | "close", note?: string): Promise<TfResult> {
  const sb = consoleServerClient();
  const { data, error } = await sb.rpc("taskforce_decide", { p_id: id, p_decision: decision, p_note: note?.trim() || null });
  if (error) return { ok: false, error: friendly(error.message) };
  revalidatePath(`/console/taskforces/${id}`);
  revalidatePath("/console/taskforces");
  return { ok: true, status: data as string };
}

export async function setMember(id: string, userId: string, role: "lead" | "member" | null): Promise<TfResult> {
  const sb = consoleServerClient();
  const { error } = await sb.rpc("taskforce_set_member", { p_id: id, p_user: userId, p_role: role });
  if (error) return { ok: false, error: friendly(error.message) };
  revalidatePath(`/console/taskforces/${id}`);
  return { ok: true };
}

export async function addNote(id: string, text: string): Promise<TfResult> {
  const problem = validateNote(text);
  if (problem) return { ok: false, error: problem };
  const sb = consoleServerClient();
  const { error } = await sb.rpc("taskforce_add_note", { p_id: id, p_text: text.trim() });
  if (error) return { ok: false, error: friendly(error.message) };
  revalidatePath(`/console/taskforces/${id}`);
  return { ok: true };
}

export async function linkCases(id: string, raw: string): Promise<TfResult> {
  const ids = parseCrimeIds(raw);
  if (ids.length === 0) return { ok: false, error: "Enter one or more case ids, e.g. CHN-AD-2026-001182." };
  const sb = consoleServerClient();
  const { data, error } = await sb.rpc("taskforce_link_cases", { p_id: id, p_crime_ids: ids });
  if (error) return { ok: false, error: friendly(error.message) };
  revalidatePath(`/console/taskforces/${id}`);
  return { ok: true, status: `${data as number} of ${ids.length} linked (unknown or already linked ids are skipped)` };
}

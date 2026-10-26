"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { rpcMessage, TRANSFORMS, type MappingEdit } from "@/lib/onboarding";

export type ActionResult = { ok: true; status?: string } | { ok: false; error: string };

const notAdmin = async (): Promise<ActionResult | null> => {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  if (officer.role !== "admin") return { ok: false, error: "Only an admin can do this." };
  return null;
};

const clean = (edits: MappingEdit[]): MappingEdit[] =>
  edits.slice(0, 200).map((e) => ({
    source_col: String(e.source_col).slice(0, 80),
    unified_field: e.unified_field ? String(e.unified_field).slice(0, 40) : null,
    transform: (TRANSFORMS as readonly string[]).includes(e.transform) ? e.transform : "none",
  }));

async function save(runId: string, edits: MappingEdit[]): Promise<ActionResult> {
  if (!edits.length) return { ok: true };
  const { data, error } = await consoleServerClient().rpc("onboarding_save_mapping", { p_run_id: runId, p_edits: clean(edits) });
  if (error) return { ok: false, error: rpcMessage(error) };
  if (Number(data) !== edits.length) return { ok: false, error: `Saved ${Number(data)} of ${edits.length} changes; reload and try again.` };
  return { ok: true };
}

/** Save the changed mapping rows only (onboarding_save_mapping marks every row it is sent as edited). */
export async function saveMapping(runId: string, edits: MappingEdit[]): Promise<ActionResult> {
  const denied = await notAdmin();
  if (denied) return denied;
  return save(runId, edits);
}

/**
 * Approve: save any unsaved changes FIRST, then decide, so what is approved is what the admin sees.
 * onboarding_decide refuses unless every required field is mapped exactly once; the worker then registers the view.
 */
export async function approveRun(runId: string, edits: MappingEdit[]): Promise<ActionResult> {
  const denied = await notAdmin();
  if (denied) return denied;
  const saved = await save(runId, edits);
  if (!saved.ok) return saved;
  const { data, error } = await consoleServerClient().rpc("onboarding_decide", { p_run_id: runId, p_decision: "approve" });
  if (error) return { ok: false, error: rpcMessage(error) };
  revalidatePath("/console/system/sources");
  return { ok: true, status: String(data) };
}

export async function rejectRun(runId: string, reason: string): Promise<ActionResult> {
  const denied = await notAdmin();
  if (denied) return denied;
  const { data, error } = await consoleServerClient().rpc("onboarding_decide", {
    p_run_id: runId, p_decision: "reject", p_reason: reason.trim().slice(0, 300) || null,
  });
  if (error) return { ok: false, error: rpcMessage(error) };
  revalidatePath("/console/system/sources");
  return { ok: true, status: String(data) };
}

"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { canDecideAlerts } from "@/lib/roles";
import { validateDecision } from "@/lib/alerts";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit } from "@/lib/alertsData";

export type DecideResult = { ok: true } | { ok: false; error: string };

/**
 * Writes one row to alert_decisions as the signed-in officer (RLS: analyst/supervisor/admin, by = auth.uid()).
 * The worker then feeds H-MEM and flips link_alerts.status (LANES "Web ↔ backend").
 */
export async function decideAlert(alertId: string, input: { decision: "approve" | "reject"; reason_code?: string; note?: string }): Promise<DecideResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  if (!canDecideAlerts(officer.role)) return { ok: false, error: "Your role can read alerts but not decide them." };
  const problem = validateDecision(input);
  if (problem) return { ok: false, error: problem };

  const sb = consoleServerClient();
  const { error } = await sb.from("alert_decisions").insert({
    alert_id: alertId,
    decision: input.decision,
    reason_code: input.decision === "reject" ? input.reason_code : null,
    note: input.note?.trim() || null,
  });
  if (error) return { ok: false, error: error.message };
  await audit(sb, "decide_alert", "link_alert", alertId, { decision: input.decision, reason_code: input.reason_code ?? null });
  revalidatePath(`/console/alerts/${alertId}`);
  revalidatePath("/console/alerts");
  return { ok: true };
}

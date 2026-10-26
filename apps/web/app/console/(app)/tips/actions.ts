"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { validatePoliceReply, validateReview } from "@/lib/tips";

export type ActionResult = { ok: true } | { ok: false; error: string };

/** Useful / not useful (+ optional linked case) through review_tip(), as the signed-in officer. */
export async function reviewTip(tipId: string, useful: boolean, crimeId: string | null, note: string): Promise<ActionResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const problem = validateReview({ useful, note });
  if (problem) return { ok: false, error: problem };
  const { error } = await consoleServerClient().rpc("review_tip", {
    p_tip_id: tipId, p_useful: useful, p_crime_id: crimeId, p_note: note.trim() || null,
  });
  if (error) return { ok: false, error: error.message };
  revalidatePath(`/console/tips/${tipId}`);
  revalidatePath("/console/tips");
  return { ok: true };
}

/** Police reply via tip code (spec G2). Only possible when the tipster chose a tip code. */
export async function replyToTip(tipId: string, followUp: boolean, text: string): Promise<ActionResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const problem = validatePoliceReply(text, followUp);
  if (problem) return { ok: false, error: problem };
  const sb = consoleServerClient();
  // tip_messages.at is coarsened to the day so the thread never shows exact times (J1)
  const today = new Date().toISOString().slice(0, 10) + "T00:00:00Z";
  const { error } = await sb.from("tip_messages").insert({ tip_id: tipId, sender: "police", text: text.trim(), author: officer.userId, at: today });
  if (error) return { ok: false, error: error.message };
  await sb.from("audit_log").insert({ what: "reply_tip", object_type: "tip", object_id: tipId });
  revalidatePath(`/console/tips/${tipId}`);
  return { ok: true };
}

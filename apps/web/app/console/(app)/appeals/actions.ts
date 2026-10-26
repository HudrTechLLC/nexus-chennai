"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { allows } from "@/lib/roles";
import { isCrimeId, parseLookingFor, validateAppeal } from "@/lib/appeals";
import { consoleServerClient } from "@/lib/supabase/server";

export type ActionResult = { ok: true } | { ok: false; error: string };

const WRITERS = ["station_officer", "supervisor", "admin"] as const;

async function writer() {
  const officer = await getOfficer();
  if (!officer) return { error: "Sign in again." } as const;
  if (!allows(officer.role, [...WRITERS])) return { error: "Your role can read appeals but not draft or publish them." } as const;
  return { officer } as const;
}

/** Ask the worker for a Sanitiser draft (appeal_requests; RLS: can_write_crime, requested_by = auth.uid()). */
export async function requestDraft(crimeId: string): Promise<ActionResult> {
  const w = await writer();
  if ("error" in w) return { ok: false, error: w.error as string };
  const id = crimeId.trim();
  if (!isCrimeId(id)) return { ok: false, error: "Enter a case id like CHN-AD-2026-001182." };
  const sb = consoleServerClient();
  const { error } = await sb.from("appeal_requests").insert({ crime_id: id, requested_by: w.officer.userId });
  if (error) return { ok: false, error: error.code === "42501" ? "You can only request appeals for your own station's cases." : error.message };
  revalidatePath("/console/appeals");
  return { ok: true };
}

/**
 * Save edits, publish or withdraw. Updates public_incidents as the officer (RLS: can_write_crime); the 0006_02
 * trigger blocks leaky published text and stamps approved_by from the officer's profile.
 */
export async function saveAppeal(
  id: string,
  input: { title: string; summary: string; looking_for: string; action: "save" | "publish" | "withdraw" },
): Promise<ActionResult> {
  const w = await writer();
  if ("error" in w) return { ok: false, error: w.error as string };
  const edit = { title: input.title.trim(), summary: input.summary.trim(), looking_for: parseLookingFor(input.looking_for) };
  if (input.action !== "withdraw") {
    const problem = validateAppeal(edit);
    if (problem) return { ok: false, error: problem };
  }
  const values =
    input.action === "withdraw"
      ? { status: "withdrawn" }
      : { ...edit, ...(input.action === "publish" ? { status: "published" } : {}) };
  const sb = consoleServerClient();
  const { data, error } = await sb.from("public_incidents").update(values).eq("public_incident_id", id).select("public_incident_id");
  if (error) return { ok: false, error: error.message };
  if (!data || data.length === 0) return { ok: false, error: "You can only edit appeals for your own station's cases." };
  revalidatePath(`/console/appeals/${encodeURIComponent(id)}`);
  revalidatePath("/console/appeals");
  return { ok: true };
}
